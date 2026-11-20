from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_agency_id
from app.db.models import AgentActivityLog, ResearchTask
from app.db.session import get_database_status, get_db
from app.schemas.dashboard import DashboardOverviewResponse, DashboardStatistics
from app.services.research_query import compute_dashboard_statistics, query_research_leads

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/statistics", response_model=DashboardStatistics)
def get_statistics(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> DashboardStatistics:
    return DashboardStatistics(**compute_dashboard_statistics(db, agency_id=agency_id))


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_overview(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    stats = compute_dashboard_statistics(db, agency_id=agency_id)
    tasks = (
        db.query(ResearchTask)
        .filter(ResearchTask.agency_id == agency_id)
        .order_by(ResearchTask.id.desc())
        .limit(10)
        .all()
    )
    leads = query_research_leads(db=db, agency_id=agency_id)[:10]
    return DashboardOverviewResponse(
        statistics=DashboardStatistics(**stats),
        recent_tasks=[
            {
                "id": t.id,
                "user_instruction": t.user_instruction,
                "search_keyword": t.search_keyword,
                "task_status": t.task_status,
                "progress": t.progress,
                "created_at": t.created_at,
            }
            for t in tasks
        ],
        recent_leads=leads,
        database_status=get_database_status(),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/activity")
def get_activity(
    limit: int = 50,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    logs = (
        db.query(AgentActivityLog)
        .filter(AgentActivityLog.agency_id == agency_id)
        .order_by(AgentActivityLog.id.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": l.id,
            "research_task_id": l.research_task_id,
            "level": l.level,
            "stage": l.stage,
            "action": l.action,
            "url": l.url,
            "message": l.message,
            "screenshot_path": l.screenshot_path,
            "created_at": l.created_at,
        }
        for l in logs
    ]
