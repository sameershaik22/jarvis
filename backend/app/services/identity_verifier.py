from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class VerificationSummary:
    identity_status: str  # Verified | Partially Verified | Unverified | Possible Match | Manual Review Required
    contact_status: str  # Verified | Partially Verified | Unverified | Possible Match | Manual Review Required
    confidence_score: int
    manual_review_required: bool
    notes: str


def verify_host_and_contact(
    host_name: str | None,
    host_linkedin_url: str | None,
    company_name: str | None,
    official_website: str | None,
    youtube_channel_url: str | None,
    email: str | None,
    email_category: str,
    contact_source_type: str | None,
    host_confidence: int = 0,
) -> VerificationSummary:
    """Module 8: Cross-source identity and contact verification."""
    signals = 0
    reasons: list[str] = []

    if host_name:
        signals += 1
        reasons.append("host name identified")
    if host_linkedin_url:
        signals += 1
        reasons.append("host LinkedIn URL verified")
    if company_name:
        signals += 1
        reasons.append("company associated")
    if official_website:
        signals += 1
        reasons.append("official website recorded")
    if youtube_channel_url:
        signals += 1
        reasons.append("original YouTube channel linked")

    # Determine identity status
    if signals >= 4 and host_confidence >= 75:
        identity_status = "Verified"
    elif signals >= 3 and host_name:
        identity_status = "Partially Verified"
    elif host_name and signals >= 1:
        identity_status = "Possible Match"
    else:
        identity_status = "Manual Review Required"

    # Cross-check email domain against official website if both exist
    domain_matches_site = False
    if email and official_website:
        email_domain = email.split("@")[-1].lower().lstrip("www.")
        site_domain = urlparse(official_website).netloc.lower().lstrip("www.")
        if email_domain and site_domain and (email_domain == site_domain or email_domain in site_domain):
            domain_matches_site = True
            reasons.append("email domain matches official website")

    if not email:
        contact_status = "Unverified"
    elif email_category == "channel_inquiry":
        # Never classify generic channel inquiry emails as verified personal business emails
        contact_status = "Unverified"
    elif domain_matches_site and identity_status == "Verified" and email_category == "host_direct_business":
        contact_status = "Verified"
    elif domain_matches_site and email_category in ("host_direct_business", "podcast_business"):
        contact_status = "Partially Verified"
    elif contact_source_type == "LinkedIn Profile" and email_category == "host_direct_business":
        contact_status = "Verified"
    elif contact_source_type in ("YouTube About", "Official Website") and email:
        contact_status = "Partially Verified" if domain_matches_site else "Unverified"
    elif contact_source_type == "Apollo":
        contact_status = "Partially Verified" if identity_status in ("Verified", "Partially Verified") else "Manual Review Required"
    else:
        contact_status = "Unverified"

    confidence = min(100, max(host_confidence, signals * 18 + (15 if domain_matches_site else 0)))
    manual_review = identity_status in ("Manual Review Required", "Possible Match") or contact_status == "Manual Review Required"

    return VerificationSummary(
        identity_status=identity_status,
        contact_status=contact_status,
        confidence_score=confidence,
        manual_review_required=manual_review,
        notes="; ".join(reasons) if reasons else "Insufficient verification signals.",
    )

