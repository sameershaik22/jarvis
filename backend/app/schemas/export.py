from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExportFilterParams(BaseModel):
    preset: Literal[
        "all",
        "qualified",
        "verified",
        "email_available",
        "manual_review",
    ] = "all"
    qualification_status: str | None = None
    identity_verification_status: str | None = None
    contact_verification_status: str | None = None
    has_email: bool | None = None
    company: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_quality_score: int | None = Field(default=None, ge=0, le=100)
    research_task_id: int | None = None
    selected_ids: list[int] | None = None


class ExportLogOut(BaseModel):
    id: int
    export_format: str
    filename: str
    filter_preset: str
    filters_json: dict[str, Any] | None = None
    record_count: int
    status: str
    download_url: str
    created_at: datetime

