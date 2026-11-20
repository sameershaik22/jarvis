from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DashboardStatistics(BaseModel):
    total_research_tasks: int
    linkedin_videos_discovered: int
    qualified_podcasts: int
    rejected_videos: int
    hosts_identified: int
    companies_identified: int
    emails_discovered: int
    verified_contacts: int
    pending_manual_reviews: int


class DashboardOverviewResponse(BaseModel):
    statistics: DashboardStatistics
    recent_tasks: list[dict[str, Any]]
    recent_leads: list[dict[str, Any]]
    database_status: dict[str, Any]
    generated_at: datetime

