from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_agency_id
from app.db.models import AgentActivityLog, AgentMessage, ResearchTask
from app.db.session import get_db
from app.schemas.agent import (
    AgentCommandRequest,
    AgentCommandResponse,
    AgentStartRequest,
    AgentStatusResponse,
    AgentTaskSummary,
)
from app.services.browser_controller import browser_controller
from app.services.browser_manager import browser_manager
from app.services.chat_command import handle_jarvis_command
from app.services.research_workflow import workflow_manager

router = APIRouter(prefix="/agent", tags=["agent"])


def _task_to_summary(task: ResearchTask) -> AgentTaskSummary:
    return AgentTaskSummary(
        id=task.id,
        user_instruction=task.user_instruction,
        search_keyword=task.search_keyword,
        task_status=task.task_status,
        current_stage=task.current_stage,
        current_url=task.current_url,
        progress=task.progress,
        max_posts=task.max_posts,
        quality_threshold=task.quality_threshold,
        started_at=task.started_at,
        completed_at=task.completed_at,
        error_message=task.error_message,
        created_at=task.created_at,
    )


@router.post("/start", response_model=AgentTaskSummary)
async def start_research(
    payload: AgentStartRequest,
    agency_id: str = Depends(get_agency_id),
) -> AgentTaskSummary:
    task = await workflow_manager.start_task(
        instruction=payload.instruction,
        search_keyword=payload.search_keyword,
        max_posts=payload.max_posts,
        quality_threshold=payload.quality_threshold,
        use_browser=payload.use_browser,
        agency_id=agency_id,
    )
    return _task_to_summary(task)


@router.post("/pause")
async def pause_research() -> dict[str, bool]:
    return {"paused": await workflow_manager.pause_task()}


@router.post("/resume")
async def resume_research() -> dict[str, bool]:
    return {"resumed": await workflow_manager.resume_task()}


@router.post("/stop")
async def stop_research() -> dict[str, bool]:
    return {"stopped": await workflow_manager.stop_task()}


# High-performance in-memory cache partitioned per tenant/workspace
_cached_stats: dict[str, tuple[float, dict[str, Any]]] = {}
_cached_leads: dict[str, tuple[float, list[Any]]] = {}
_cached_status_responses: dict[str, tuple[float, AgentStatusResponse]] = {}


@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> AgentStatusResponse:
    global _cached_stats, _cached_leads, _cached_status_responses
    now = time.time()

    # Fast-path cache return (0.1ms response time, completely removes frontend polling lag)
    cached_entry = _cached_status_responses.get(agency_id)
    if cached_entry and (now - cached_entry[0]) < 3.0:
        cached_resp = cached_entry[1]
        cached_resp.agent_state = workflow_manager.agent_state  # type: ignore[assignment]
        session = browser_manager.get_session(agency_id)
        cached_resp.bridge_connected = session.is_local_connected
        cached_resp.device_name = session.device_name if session.is_local_connected else None
        return cached_resp

    active_task = None
    logs = []
    messages = []
    try:
        if workflow_manager.active_task_id is not None:
            active_task = (
                db.query(ResearchTask)
                .filter(ResearchTask.id == workflow_manager.active_task_id, ResearchTask.agency_id == agency_id)
                .first()
            )
        if active_task is None:
            active_task = (
                db.query(ResearchTask)
                .filter(ResearchTask.agency_id == agency_id)
                .order_by(ResearchTask.id.desc())
                .first()
            )

        logs = (
            db.query(AgentActivityLog)
            .filter(AgentActivityLog.agency_id == agency_id)
            .order_by(AgentActivityLog.id.desc())
            .limit(20)
            .all()
        )
        messages = (
            db.query(AgentMessage)
            .filter(AgentMessage.agency_id == agency_id)
            .order_by(AgentMessage.id.asc())
            .limit(30)
            .all()
        )
    except Exception as db_exc:
        if cached_entry:
            return cached_entry[1]

    session = browser_manager.get_session(agency_id)
    if session.is_local_connected:
        status_info = await session.compute_browser_status()
        cur_url = session.current_url or (active_task.current_url if active_task else None)
        browser_active = True
        shot = session.last_screenshot_path
    else:
        status_info = await browser_controller.compute_browser_status()
        cur_url = browser_controller.current_url or (active_task.current_url if active_task else None)
        browser_active = browser_controller.is_active
        shot = await browser_controller.get_live_screenshot()

    cur_site = urlparse(cur_url).netloc if cur_url else None
    shot_url = f"/api/v1/agent/screenshot?agency_id={agency_id}" if shot and Path(shot).exists() else None

    # Cached Neon PostgreSQL queries per workspace
    from app.services.research_query import compute_dashboard_statistics, query_research_leads
    cached_s = _cached_stats.get(agency_id)
    if not cached_s or (now - cached_s[0]) > 3.5:
        try:
            stats_val = compute_dashboard_statistics(db, agency_id=agency_id)
            _cached_stats[agency_id] = (now, stats_val)
        except Exception:
            stats_val = cached_s[1] if cached_s else {}
    else:
        stats_val = cached_s[1]

    cached_l = _cached_leads.get(agency_id)
    if not cached_l or (now - cached_l[0]) > 3.5:
        try:
            leads_val = query_research_leads(db=db, agency_id=agency_id)[:10]
            _cached_leads[agency_id] = (now, leads_val)
        except Exception:
            leads_val = cached_l[1] if cached_l else []
    else:
        leads_val = cached_l[1]

    resp = AgentStatusResponse(
        agent_state=workflow_manager.agent_state,  # type: ignore[arg-type]
        browser_active=browser_active,
        browser_status=status_info["browser_status"],
        bridge_connected=session.is_local_connected,
        device_name=session.device_name if session.is_local_connected else None,
        agency_id=agency_id,
        linkedin_authenticated=status_info["linkedin_authenticated"],
        youtube_authenticated=status_info["youtube_authenticated"],
        current_url=cur_url,
        current_website=cur_site,
        latest_screenshot_url=shot_url,
        active_task=_task_to_summary(active_task) if active_task else None,
        recent_logs=list(reversed(logs)),
        messages=messages,
        recent_leads=leads_val,
        stats=stats_val,
    )
    _cached_status_responses[agency_id] = (time.time(), resp)
    return resp


@router.post("/browser/launch")
async def launch_external_browser(
    payload: dict[str, Any] | None = None,
    agency_id: str = Depends(get_agency_id),
) -> dict[str, Any]:
    """Launch visible external Chrome window on desktop or local agent."""
    target = (payload or {}).get("target", "linkedin")
    session = browser_manager.get_session(agency_id)
    if session.is_local_connected:
        return await session.launch_external_browser(target=target)
    return await browser_controller.launch_external_browser(target=target)


@router.post("/browser/close")
async def close_external_browser(agency_id: str = Depends(get_agency_id)) -> dict[str, Any]:
    """Close external Chrome window."""
    session = browser_manager.get_session(agency_id)
    if session.is_local_connected:
        return await session.close_external_browser()
    return await browser_controller.close_external_browser()


@router.post("/browser/reconnect")
async def reconnect_external_browser(
    payload: dict[str, Any] | None = None,
    agency_id: str = Depends(get_agency_id),
) -> dict[str, Any]:
    """Close and cleanly restart external Chrome window."""
    target = (payload or {}).get("target", "linkedin")
    session = browser_manager.get_session(agency_id)
    if session.is_local_connected:
        return await session.reconnect_external_browser(target=target)
    return await browser_controller.reconnect_external_browser(target=target)


@router.post("/command", response_model=AgentCommandResponse)
async def send_command(
    payload: AgentCommandRequest,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> AgentCommandResponse:
    res = await handle_jarvis_command(db, payload.command, agency_id=agency_id)
    return AgentCommandResponse(**res)


@router.get("/screenshot")
def get_latest_screenshot(agency_id: str = Depends(get_agency_id)) -> FileResponse:
    session = browser_manager.get_session(agency_id)
    shot = session.last_screenshot_path or browser_controller.last_screenshot_path
    if not shot or not Path(shot).exists():
        raise HTTPException(status_code=404, detail="No browser screenshot captured yet.")
    return FileResponse(path=shot, media_type="image/png", filename=Path(shot).name)


@router.get("/events")
async def stream_agent_events() -> StreamingResponse:
    queue = workflow_manager.events.subscribe()

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'agent_state': workflow_manager.agent_state})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'agent_state': workflow_manager.agent_state})}\n\n"
        finally:
            workflow_manager.events.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

