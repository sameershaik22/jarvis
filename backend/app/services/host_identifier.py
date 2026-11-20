from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.browser_controller import BrowserController
from app.services.page_extractor import canonicalize_url, classify_external_links

HOST_PATTERNS = [
    re.compile(r"(?:hosted by|your host[,:\s]+|podcast host[,:\s]+|host[,:\s]+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.IGNORECASE),
    re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+(?:hosts|is the host of|welcomes)", re.IGNORECASE),
]

GUEST_EXCLUSION_PATTERNS = [
    re.compile(r"(?:guest|featuring|joined by|interview with|special guest|welcomes)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.IGNORECASE),
]


@dataclass
class HostIdentificationResult:
    host_name: str | None
    host_role: str
    host_linkedin_url: str | None
    associated_company: str | None
    confidence_score: int
    manual_review_required: bool
    evidence_urls: list[str]
    notes: str


def _detect_guest_names(caption: str) -> set[str]:
    guests: set[str] = set()
    for pat in GUEST_EXCLUSION_PATTERNS:
        for m in pat.findall(caption or ""):
            guests.add(m.strip().lower())
    return guests


async def identify_podcast_host(
    post_data: dict[str, Any],
    podcast_name: str,
    ai_entities: dict[str, Any] | None = None,
    browser: BrowserController | None = None,
) -> HostIdentificationResult:
    """Module 5: Identify ONLY the podcast host (never guests or interviewees)."""
    caption = post_data.get("post_caption", "") or ""
    posting_account = (post_data.get("posting_account") or "").strip()
    posting_account_url = canonicalize_url(post_data.get("posting_account_url"))
    external_urls = post_data.get("external_urls", []) or []
    classified_links = classify_external_links(external_urls)

    guest_names = _detect_guest_names(caption)
    evidence_urls: list[str] = []
    if post_data.get("post_url"):
        evidence_urls.append(post_data["post_url"])

    host_name: str | None = (ai_entities or {}).get("host_name")
    confidence = int((ai_entities or {}).get("host_confidence") or 0)

    if not host_name:
        for pat in HOST_PATTERNS:
            m = pat.search(caption)
            if m:
                candidate = re.sub(r"\s+", " ", m.group(1)).strip()
                if candidate.lower() not in guest_names:
                    host_name = candidate
                    confidence = 78
                    break

    # If posting account is a person's name (2-3 words, no company keywords), recognize as host
    if not host_name and posting_account:
        tokens = posting_account.split()
        non_person_words = {
            "podcast", "show", "media", "tv", "productions", "network",
            "channel", "llc", "inc", "company", "group", "daily", "news",
            "realty", "investing", "properties", "real", "estate"
        }
        if 2 <= len(tokens) <= 3 and not any(t.lower() in non_person_words for t in tokens):
            if posting_account.lower() not in guest_names:
                host_name = posting_account
                confidence = 72

    # If posting account is a personal LinkedIn profile (/in/) and not flagged as a guest, strong host signal
    host_linkedin_url: str | None = None
    if posting_account_url and "/in/" in posting_account_url:
        if not host_name and posting_account and posting_account.lower() not in guest_names:
            host_name = posting_account
            confidence = 70
        if host_name and posting_account and host_name.lower().split()[0] in posting_account.lower():
            host_linkedin_url = posting_account_url
            evidence_urls.append(host_linkedin_url)
            confidence = max(confidence, 82)

    if not host_linkedin_url and classified_links["linkedin_profiles"]:
        host_linkedin_url = classified_links["linkedin_profiles"][0]
        evidence_urls.append(host_linkedin_url)

    # Extract company mention if explicitly linked to host (stop cleanly at sentence/clause boundaries)
    associated_company = None
    comp_match = re.search(
        r"(?:founder|ceo|managing partner|broker|president|host)\s+(?:at|of)\s+([A-Z][A-Za-z0-9&' \-]{2,50})",
        caption,
        re.IGNORECASE,
    )
    if comp_match:
        raw_comp = comp_match.group(1).strip(" .,-")
        # Trim trailing lowercase sentence words if regex continued past company name
        raw_comp = re.split(r"\s+(?:and|with|on|where|who|today)\b", raw_comp, maxsplit=1, flags=re.IGNORECASE)[0]
        associated_company = raw_comp.strip(" .,-")

    if not host_name:
        return HostIdentificationResult(
            host_name=None,
            host_role="Podcast Host",
            host_linkedin_url=host_linkedin_url,
            associated_company=associated_company,
            confidence_score=25,
            manual_review_required=True,
            evidence_urls=list(dict.fromkeys(evidence_urls)),
            notes="Podcast host could not be confidently separated from caption/account; flagged for manual review rather than guessing.",
        )

    manual_review = confidence < 65 or bool((ai_entities or {}).get("needs_manual_review"))
    return HostIdentificationResult(
        host_name=host_name,
        host_role="Podcast Host",
        host_linkedin_url=host_linkedin_url,
        associated_company=associated_company,
        confidence_score=confidence,
        manual_review_required=manual_review,
        evidence_urls=list(dict.fromkeys(evidence_urls)),
        notes=f"Identified podcast host '{host_name}' for '{podcast_name}' (excluded guest mentions: {sorted(guest_names)}).",
    )

