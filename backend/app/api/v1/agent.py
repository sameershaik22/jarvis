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


# High-performance in-memory cache to prevent Neon PostgreSQL saturation during polling
_cached_stats: dict[str, Any] = {}
_cached_stats_time: float = 0.0
_cached_leads: list[Any] = []
_cached_leads_time: float = 0.0
_cached_status_response: AgentStatusResponse | None = None
_cached_status_time: float = 0.0


@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> AgentStatusResponse:
    global _cached_stats, _cached_stats_time, _cached_leads, _cached_leads_time, _cached_status_response, _cached_status_time
    now = time.time()

    # Fast-path cache return (0.1ms response time, completely removes frontend polling lag)
    if _cached_status_response is not None and (now - _cached_status_time) < 5.0:
        _cached_status_response.agent_state = workflow_manager.agent_state  # type: ignore[assignment]
        _cached_status_response.browser_active = browser_controller.is_active
        cur_u = browser_controller.current_url or _cached_status_response.current_url
        if cur_u:
            _cached_status_response.current_url = cur_u
            _cached_status_response.current_website = urlparse(cur_u).netloc
        return _cached_status_response

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
        if _cached_status_response:
            return _cached_status_response
    cur_url = browser_controller.current_url or (active_task.current_url if active_task else None)
    cur_site = urlparse(cur_url).netloc if cur_url else None
    status_info = await browser_controller.compute_browser_status()
    shot = await browser_controller.get_live_screenshot()
    shot_url = "/api/v1/agent/screenshot" if shot and Path(shot).exists() else None

    # Cached Neon PostgreSQL queries (refreshed at most once every 3.5s to eliminate query lag)
    from app.services.research_query import compute_dashboard_statistics, query_research_leads
    if now - _cached_stats_time > 3.5 or not _cached_stats:
        try:
            _cached_stats = compute_dashboard_statistics(db, agency_id=agency_id)
            _cached_stats_time = now
        except Exception:
            pass
    if now - _cached_leads_time > 3.5 or not _cached_leads:
        try:
            _cached_leads = query_research_leads(db=db, agency_id=agency_id)[:10]
            _cached_leads_time = now
        except Exception:
            pass

    resp = AgentStatusResponse(
        agent_state=workflow_manager.agent_state,  # type: ignore[arg-type]
        browser_active=browser_controller.is_active,
        browser_status=status_info["browser_status"],
        linkedin_authenticated=status_info["linkedin_authenticated"],
        youtube_authenticated=status_info["youtube_authenticated"],
        current_url=cur_url,
        current_website=cur_site,
        latest_screenshot_url=shot_url,
        active_task=_task_to_summary(active_task) if active_task else None,
        recent_logs=list(reversed(logs)),
        messages=messages,
        recent_leads=_cached_leads,
        stats=_cached_stats,
    )
    _cached_status_response = resp
    _cached_status_time = time.time()
    return resp


@router.post("/browser/launch")
async def launch_external_browser(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Launch visible external Chrome window on desktop."""
    target = (payload or {}).get("target", "linkedin")
    return await browser_controller.launch_external_browser(target=target)


@router.post("/browser/close")
async def close_external_browser() -> dict[str, Any]:
    """Close external Chrome window."""
    return await browser_controller.close_external_browser()


@router.post("/browser/reconnect")
async def reconnect_external_browser(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Close and cleanly restart external Chrome window."""
    target = (payload or {}).get("target", "linkedin")
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
def get_latest_screenshot() -> FileResponse:
    shot = browser_controller.last_screenshot_path
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

