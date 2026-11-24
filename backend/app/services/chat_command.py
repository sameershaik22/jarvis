from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AgentMessage
from app.services.ai_planner import ai_planner
from app.services.export_service import generate_csv_export, generate_excel_export
from app.services.research_query import compute_dashboard_statistics
from app.services.research_workflow import workflow_manager


async def handle_jarvis_command(db: Session, command: str, agency_id: str = "default") -> dict[str, Any]:
    """Process conversational Jarvis command, persist chat history, and execute real actions."""
    user_msg = AgentMessage(agency_id=agency_id, role="user", content=command)
    db.add(user_msg)
    db.commit()

    parsed = await ai_planner.parse_command_intent(command)
    intent = parsed.get("intent", "start_research")

    if intent == "out_of_scope":
        reply = (
            "I cannot run guest prospecting, marketing employee discovery, or automated cold messaging. "
            "YoursBuddy AI v1 is strictly scoped to real estate podcast discovery, host identification, "
            "host company research, host contact discovery, and Excel/CSV reporting."
        )
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent}))
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "rejected_out_of_scope"}

    if intent == "pause_research":
        paused = await workflow_manager.pause_task()
        reply = "Active research task paused." if paused else "There is no currently running task to pause."
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent}))
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "paused" if paused else "noop"}

    if intent == "resume_research":
        resumed = await workflow_manager.resume_task()
        reply = "Resumed the paused research task." if resumed else "There is no paused task to resume."
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent}))
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "resumed" if resumed else "noop"}

    if intent == "stop_research":
        stopped = await workflow_manager.stop_task()
        reply = "Stopped the active research task." if stopped else "There is no active research task running."
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent}))
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "stopped" if stopped else "noop"}

    if intent == "show_research_summary":
        stats = compute_dashboard_statistics(db, agency_id=agency_id)
        reply = (
            f"Current database summary: {stats['linkedin_videos_discovered']} LinkedIn videos discovered, "
            f"{stats['qualified_podcasts']} qualified podcasts, {stats['hosts_identified']} hosts identified, "
            f"{stats['emails_discovered']} emails discovered ({stats['verified_contacts']} verified), "
            f"and {stats['pending_manual_reviews']} pending manual review(s)."
        )
        db.add(
            AgentMessage(
                agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent, "stats": stats}
            )
        )
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "summary_queried", "data": stats}

    if intent == "export_leads":
        fmt = parsed.get("format", "xlsx")
        preset = parsed.get("preset", "all")
        last_days = parsed.get("last_days")
        target_kw = parsed.get("keyword")
        filters: dict[str, Any] = {"preset": preset}
        if target_kw and target_kw.lower() not in ("all", "default", "none"):
            filters["search"] = target_kw
            filters["keyword"] = target_kw
        if last_days:
            dt_from = (datetime.now(timezone.utc) - timedelta(days=int(last_days))).strftime("%Y-%m-%d")
            filters["date_from"] = dt_from

        log = (
            generate_csv_export(db, filters, agency_id=agency_id)
            if fmt == "csv"
            else generate_excel_export(db, filters, agency_id=agency_id)
        )
        dl_url = f"/api/v1/export/download/{log.id}"
        reply = (
            f"Generated {fmt.upper()} export '{log.filename}' with {log.record_count} lead record(s) "
            f"(preset: {preset}{f', keyword: {target_kw}' if target_kw else ''}). Ready for download."
        )
        db.add(
            AgentMessage(
                agency_id=agency_id,
                role="assistant",
                content=reply,
                metadata_json={"intent": intent, "export_id": log.id, "download_url": dl_url},
            )
        )
        db.commit()
        return {
            "reply": reply,
            "intent": intent,
            "action_taken": "export_generated",
            "export_download_url": dl_url,
            "data": {"export_id": log.id, "filename": log.filename, "record_count": log.record_count},
        }

    if intent == "conversational_help":
        reply = (
            "Hello! I am YoursBuddy AI, your autonomous real estate podcast host research agent. "
            "To begin research, click 'Start Research' above or send an instruction like: "
            "'Find real estate podcasts on LinkedIn and YouTube, identify hosts, and locate business emails'."
        )
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": intent}))
        db.commit()
        return {"reply": reply, "intent": intent, "action_taken": "guidance_provided"}

    # Guard: Only start research if intent is explicitly start_research or has clear research keywords
    lower_cmd = command.lower()
    has_research_keywords = any(w in lower_cmd for w in ("find", "search", "podcast", "host", "video", "research", "scrape", "discover", "look for", "show"))
    if intent != "start_research" and not has_research_keywords:
        reply = (
            "I didn't recognize that as an automation command. "
            "To begin autonomous research, click 'Start Research' above or enter a search prompt."
        )
        db.add(AgentMessage(agency_id=agency_id, role="assistant", content=reply, metadata_json={"intent": "unrecognized"}))
        db.commit()
        return {"reply": reply, "intent": "unrecognized", "action_taken": "noop"}

    keyword = parsed.get("keyword")
    # If keyword fell back to default Real Estate Podcast but user didn't ask for real estate, dynamically extract topic
    if not keyword or (keyword.lower() in ("real estate podcast", "real estate", "podcast") and "real estate" not in command.lower()):
        from app.services.ai_planner import extract_keyword_from_text
        extracted = extract_keyword_from_text(command)
        if extracted and extracted.lower() not in ("podcast", "real estate podcast"):
            keyword = extracted
    if not keyword:
        keyword = "Real Estate Podcast"
    max_posts = int(parsed.get("max_posts") or 10)
    task = await workflow_manager.start_task(
        instruction=command,
        search_keyword=keyword,
        max_posts=max_posts,
        use_browser=True,
        agency_id=agency_id,
    )
    from app.api.v1.agent import invalidate_agent_cache
    invalidate_agent_cache(agency_id)
    reply = (
        f"Started research task #{task.id} for '{task.search_keyword}'. "
        f"I will navigate YouTube & LinkedIn for '{task.search_keyword}', evaluate video quality, locate original podcast channels, "
        f"research podcast hosts and companies, and search LinkedIn -> YouTube About -> Apollo for verified business emails."
    )
    db.add(
        AgentMessage(
            agency_id=agency_id,
            research_task_id=task.id,
            role="assistant",
            content=reply,
            metadata_json={"intent": intent, "task_id": task.id},
        )
    )
    db.commit()
    return {
        "reply": reply,
        "intent": intent,
        "action_taken": "task_started",
        "task": {
            "id": task.id,
            "user_instruction": task.user_instruction,
            "search_keyword": task.search_keyword,
            "task_status": task.task_status,
            "current_stage": task.current_stage,
            "current_url": task.current_url,
            "progress": task.progress,
            "max_posts": task.max_posts,
            "quality_threshold": task.quality_threshold,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_message": task.error_message,
            "created_at": task.created_at,
        },
    }
