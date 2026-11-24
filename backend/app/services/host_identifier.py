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


STOP_WORDS = {
    "into", "the", "a", "an", "for", "with", "and", "by", "from",
    "on", "in", "to", "of", "about", "at", "as", "or", "is", "your",
    "our", "my", "how", "what", "why", "where", "who", "when", "all"
}

BRAND_WORDS = {
    "podcast", "show", "media", "tv", "productions", "production", "network",
    "channel", "llc", "inc", "company", "group", "daily", "news",
    "realty", "investing", "properties", "real", "estate", "cre", "break",
    "blueprint", "talks", "digest", "capital", "partners", "ventures",
    "studio", "studios", "radio", "hub", "insider", "live", "uncut",
    "corp", "corporation", "ltd", "agency", "management", "financial",
    "solutions", "holdings", "advisors", "equity", "bolt", "brick", "series",
    "talk", "interviews", "unfiltered", "academy", "consulting", "enterprises",
    "page", "listing", "tour", "tours", "service", "services", "official", "video", "videos"
}


def is_valid_person_name(name: str | None, podcast_name: str | None = None) -> bool:
    """Strictly validate that a name belongs to an actual individual human host, NOT a brand, channel, or phrase."""
    if not name or not isinstance(name, str):
        return False
    clean = re.sub(r"[^\w\s\.\-']", "", name).strip()
    tokens = clean.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False

    # Disallow matching podcast or channel brand name if it's a corporate/media brand
    if podcast_name:
        clean_pod = re.sub(r"[^\w\s]", "", podcast_name).lower().strip()
        pod_tokens = clean_pod.split()
        has_pod_brand = any(t in BRAND_WORDS for t in pod_tokens)
        if has_pod_brand and (clean.lower() == clean_pod or clean_pod in clean.lower()):
            return False

    # Stop words / prepositions indicating titles, slogans, or channel descriptions
    if any(t.lower() in STOP_WORDS for t in tokens):
        return False

    # Brand / media / corporate words that cannot be part of an individual's personal name
    if any(t.lower() in BRAND_WORDS for t in tokens):
        return False

    # Each token in a person's name must start with an uppercase letter and consist of alphabetic characters
    for t in tokens:
        if not re.match(r"^[A-Z][a-zA-Z\.\-']+$", t):
            return False

    return True


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
    if host_name and not is_valid_person_name(host_name, podcast_name):
        host_name = None
    confidence = int((ai_entities or {}).get("host_confidence") or 0)

    if not host_name:
        for pat in HOST_PATTERNS:
            m = pat.search(caption)
            if m:
                candidate = re.sub(r"\s+", " ", m.group(1)).strip()
                if candidate.lower() not in guest_names and is_valid_person_name(candidate, podcast_name):
                    host_name = candidate
                    confidence = 78
                    break

    # If posting account is an actual person's name (and not a corporate/company account), recognize as host
    is_company_acct = bool(posting_account_url and ("/company/" in posting_account_url.lower() or "/school/" in posting_account_url.lower()))
    if not host_name and posting_account and not is_company_acct and is_valid_person_name(posting_account, podcast_name):
        if posting_account.lower() not in guest_names:
            host_name = posting_account
            confidence = 72

    # If host still not identified, search Tavily for podcast host
    if not host_name and podcast_name:
        try:
            from app.services.tavily_search import search_tavily
            t_res = await search_tavily(f'"{podcast_name}" podcast host', max_results=3)
            for r in t_res:
                txt = r.get("title", "") + " " + r.get("content", "")
                for pat in HOST_PATTERNS:
                    for m in pat.finditer(txt):
                        candidate = m.group(1).strip()
                        tokens = candidate.split()
                        for take_len in (2, min(len(tokens), 3)):
                            sub_cand = " ".join(tokens[:take_len])
                            if sub_cand.lower() not in guest_names and is_valid_person_name(sub_cand, podcast_name):
                                host_name = sub_cand
                                confidence = 75
                                if r.get("url"):
                                    evidence_urls.append(r["url"])
                                break
                        if host_name:
                            break
                    if host_name:
                        break
                if host_name:
                    break
        except Exception:
            pass

    # If posting account is a personal LinkedIn profile (/in/) and not flagged as a guest, strong host signal
    host_linkedin_url: str | None = None
    if posting_account_url and "/in/" in posting_account_url:
        if not host_name and posting_account and is_valid_person_name(posting_account, podcast_name):
            if posting_account.lower() not in guest_names:
                host_name = posting_account
                confidence = 70
        if host_name and posting_account and host_name.lower().split()[0] in posting_account.lower():
            host_linkedin_url = posting_account_url
            evidence_urls.append(host_linkedin_url)
            confidence = max(confidence, 82)

    # Double check final host_name validity
    if host_name and not is_valid_person_name(host_name, podcast_name):
        host_name = None

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

