from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LeadRecordOut(BaseModel):
    lead_id: int  # podcasts.id or linkedin_posts.id
    linkedin_post_id: int | None = None
    podcast_id: int | None = None
    host_id: int | None = None
    company_id: int | None = None
    contact_id: int | None = None
    research_task_id: int | None = None

    podcast_name: str
    episode_title: str | None = None
    linkedin_post_url: str | None = None
    video_posting_date: str | None = None
    youtube_channel_name: str | None = None
    youtube_channel_url: str | None = None
    original_podcast_url: str | None = None

    host_full_name: str | None = None
    host_designation: str | None = None
    host_linkedin_url: str | None = None
    host_company: str | None = None
    company_linkedin_url: str | None = None
    company_website: str | None = None
    company_location: str | None = None

    business_email: str | None = None
    email_category: str | None = None
    phone: str | None = None
    contact_source: str | None = None
    contact_source_url: str | None = None

    video_quality_score: int | None = None
    video_quality: str | None = None
    audio_quality: str | None = None
    lighting: str | None = None
    podcast_setup: str | None = None
    content_relevance: str | None = None
    qualification_status: str | None = None

    identity_verification_status: str | None = None
    contact_verification_status: str | None = None
    confidence_score: int = 0
    manual_review_required: bool = False
    research_date: datetime | None = None
    research_notes: str | None = None


class EvidenceOut(BaseModel):
    id: int
    research_task_id: int | None = None
    entity_type: str
    entity_id: int
    source_url: str
    source_type: str
    extracted_information: str
    collected_at: datetime

    model_config = {"from_attributes": True}


class VideoPostOut(BaseModel):
    id: int
    research_task_id: int
    post_url: str
    post_caption: str
    posting_account: str
    posting_account_url: str | None = None
    video_url: str | None = None
    published_label: str | None = None
    discovered_at: datetime
    quality_score: int | None = None
    qualification_status: str | None = None
    assessment_notes: str | None = None


class HostOut(BaseModel):
    id: int
    full_name: str
    linkedin_url: str | None = None
    designation: str | None = None
    location: str | None = None
    identity_status: str
    confidence_score: int
    manual_review_required: bool
    notes: str | None = None
    companies: list[dict[str, Any]] = []
    podcasts: list[dict[str, Any]] = []


class ContactOut(BaseModel):
    id: int
    person_id: int | None = None
    host_name: str | None = None
    podcast_id: int | None = None
    podcast_name: str | None = None
    email: str | None = None
    email_category: str
    phone: str | None = None
    official_website: str | None = None
    contact_page: str | None = None
    contact_status: str
    verification_status: str
    confidence_score: int
    research_notes: str | None = None
    sources: list[dict[str, Any]] = []

