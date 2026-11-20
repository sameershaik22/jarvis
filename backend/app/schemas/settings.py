from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SafeSettingsOut(BaseModel):
    openai_model: str
    openai_configured: bool
    gemini_model: str
    gemini_configured: bool
    tavily_configured: bool
    apollo_configured: bool
    n8n_configured: bool
    browser_headless: bool
    browser_channel: str
    default_search_keyword: str
    quality_threshold: int
    max_posts_per_run: int
    database_status: dict[str, Any]


class SafeSettingsUpdate(BaseModel):
    openai_model: str | None = Field(default=None, min_length=2, max_length=120)
    browser_headless: bool | None = None
    browser_channel: str | None = Field(default=None, max_length=40)
    default_search_keyword: str | None = Field(default=None, min_length=2, max_length=255)
    quality_threshold: int | None = Field(default=None, ge=0, le=100)
    max_posts_per_run: int | None = Field(default=None, ge=1, le=50)

