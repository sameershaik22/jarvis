from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VerifyHostRequest(BaseModel):
    host_id: int
    full_name: str | None = None
    linkedin_url: str | None = None
    designation: str | None = None
    company_name: str | None = None
    company_linkedin_url: str | None = None
    company_website: str | None = None
    company_location: str | None = None
    identity_status: Literal[
        "Verified",
        "Partially Verified",
        "Unverified",
        "Possible Match",
        "Manual Review Required",
    ] = "Verified"
    manual_review_required: bool = False
    notes: str | None = None


class VerifyContactRequest(BaseModel):
    contact_id: int
    email: str | None = None
    email_category: Literal[
        "host_direct_business",
        "podcast_business",
        "company_contact",
        "channel_inquiry",
        "unknown",
    ] | None = None
    phone: str | None = None
    contact_status: Literal["active", "rejected", "needs_review"] = "active"
    verification_status: Literal[
        "Verified",
        "Partially Verified",
        "Unverified",
        "Possible Match",
        "Manual Review Required",
    ] = "Verified"
    notes: str | None = None


class ManualReviewActionRequest(BaseModel):
    podcast_id: int | None = None
    host_id: int | None = None
    contact_id: int | None = None
    action: Literal["approve", "reject", "request_recheck"] = "approve"
    notes: str | None = None
    corrected_host_name: str | None = None
    corrected_company_name: str | None = None
    corrected_email: str | None = None
    corrected_youtube_url: str | None = None

