from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentStartRequest(BaseModel):
    instruction: str = Field(..., min_length=3, max_length=4000)
    search_keyword: str | None = Field(default=None, max_length=255)
    max_posts: int | None = Field(default=None, ge=1, le=50)
    quality_threshold: int | None = Field(default=None, ge=0, le=100)
    use_browser: bool = True


class AgentCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4000)


class AgentTaskSummary(BaseModel):
    id: int
    user_instruction: str
    search_keyword: str
    task_status: str
    current_stage: str
    current_url: str | None = None
    progress: int
    max_posts: int
    quality_threshold: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


class AgentActivityLogOut(BaseModel):
    id: int
    research_task_id: int | None = None
    level: str
    stage: str
    action: str
    url: str | None = None
    message: str
    screenshot_path: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentMessageOut(BaseModel):
    id: int
    research_task_id: int | None = None
    role: str
    content: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusResponse(BaseModel):
    agent_state: Literal["idle", "running", "paused", "stopping", "error"]
    browser_active: bool
    browser_status: str = Field(default="Browser disconnected")
    bridge_connected: bool = Field(default=False)
    device_name: str | None = Field(default=None)
    agency_id: str = Field(default="default")
    linkedin_authenticated: bool = Field(default=False)
    youtube_authenticated: bool = Field(default=False)
    current_url: str | None = None
    current_website: str | None = None
    latest_screenshot_url: str | None = None
    active_task: AgentTaskSummary | None = None
    recent_logs: list[AgentActivityLogOut] = Field(default_factory=list)
    messages: list[AgentMessageOut] = Field(default_factory=list)
    recent_leads: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class AgentCommandResponse(BaseModel):
    reply: str
    intent: str
    action_taken: str
    task: AgentTaskSummary | None = None
    export_download_url: str | None = None
    data: dict[str, Any] | None = None

