from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import get_settings
from app.services.browser_controller import BrowserController
from app.services.tavily_search import search_tavily
from app.services.page_extractor import (
    canonicalize_url,
    extract_emails_from_text,
    extract_phones_from_text,
    is_safe_company_website,
    parse_youtube_about_from_html,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredContact:
    email: str | None
    email_category: str  # host_direct_business | podcast_business | company_contact | channel_inquiry | unknown
    phone: str | None
    official_website: str | None
    contact_page: str | None
    source_type: str  # LinkedIn Profile | LinkedIn Post | LinkedIn Company | YouTube About | Official Website | Apollo
    source_url: str | None
    discovery_method: str
    verification_status: str  # Verified | Partially Verified | Unverified | Possible Match | Manual Review Required
    confidence_score: int
    notes: str


def categorize_email(email: str, host_name: str | None, source_type: str) -> str:
    lower = email.lower()
    local_part = lower.split("@")[0]

    general_prefixes = ("info", "contact", "hello", "support", "media", "press", "admin", "office", "team")
    podcast_prefixes = ("podcast", "show", "booking", "bookings", "episode", "guest", "inquiries", "business")

    if source_type == "YouTube About":
        if any(p in local_part for p in podcast_prefixes):
            return "podcast_business"
        if any(local_part.startswith(p) for p in general_prefixes):
            return "channel_inquiry"
        # Check if host's name is actually in local part before classifying as host direct
        if host_name:
            tokens = [t.lower() for t in host_name.split() if len(t) > 2]
            if any(t in local_part for t in tokens):
                return "host_direct_business"
        return "channel_inquiry"

    if host_name:
        tokens = [t.lower() for t in host_name.split() if len(t) > 2]
        if any(t in local_part for t in tokens):
            return "host_direct_business"

    if any(p in local_part for p in podcast_prefixes):
        return "podcast_business"
    if any(local_part.startswith(p) for p in general_prefixes):
        return "company_contact"
    return "unknown"


async def _apollo_person_enrich(
    host_name: str,
    company_name: str | None,
    host_linkedin_url: str | None,
    official_website: str | None,
) -> dict[str, Any] | None:
    """Priority 3: Apollo API enrichment fallback (only if configured and verified match)."""
    settings = get_settings()
    if not settings.apollo_api_key or not settings.apollo_api_key.strip():
        return None

    parts = host_name.strip().split()
    if len(parts) < 2:
        return None
    first_name, last_name = parts[0], " ".join(parts[1:])
    domain = urlparse(official_website).netloc.replace("www.", "") if official_website else None

    payload: dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "reveal_personal_emails": False,
    }
    if company_name:
        payload["organization_name"] = company_name
    if domain:
        payload["domain"] = domain
    if host_linkedin_url:
        payload["linkedin_url"] = host_linkedin_url

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": settings.apollo_api_key.strip(),
                },
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning("Apollo API returned status %s", resp.status_code)
                return None
            data = resp.json()
            person = data.get("person")
            if not person:
                return None
            return {
                "email": person.get("email"),
                "email_status": person.get("email_status"),
                "name": person.get("name"),
                "title": person.get("title"),
                "linkedin_url": person.get("linkedin_url"),
                "organization": (person.get("organization") or {}).get("name"),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Apollo API lookup failed: %s", exc)
        return None


async def discover_host_contacts(
    post_data: dict[str, Any],
    host_name: str | None,
    host_linkedin_url: str | None,
    company_name: str | None,
    official_website: str | None,
    youtube_channel_url: str | None,
    browser: BrowserController | None = None,
    allow_live_browser: bool = True,
) -> list[DiscoveredContact]:
    """Module 7: Host Contact Discovery following strict Priority 1 -> 2 -> 3."""
    discovered: list[DiscoveredContact] = []
    seen_emails: set[str] = set()

    # Priority 1: LinkedIn post description, comments, and public links
    post_text = (post_data.get("post_caption") or "") + "\n" + "\n".join(post_data.get("comments") or [])
    post_emails = extract_emails_from_text(post_text)
    post_phones = extract_phones_from_text(post_text)
    for email in post_emails:
        seen_emails.add(email)
        cat = categorize_email(email, host_name, "LinkedIn Post")
        discovered.append(
            DiscoveredContact(
                email=email,
                email_category=cat,
                phone=post_phones[0] if post_phones else None,
                official_website=official_website,
                contact_page=None,
                source_type="LinkedIn Post",
                source_url=post_data.get("post_url"),
                discovery_method="linkedin_post_caption_or_comments",
                verification_status="Partially Verified",
                confidence_score=72,
                notes="Extracted directly from LinkedIn post caption or comments.",
            )
        )

    # Check host LinkedIn contact overlay / public profile text if browser active
    if allow_live_browser and browser is not None and host_linkedin_url and not discovered:
        contact_overlay = host_linkedin_url.rstrip("/") + "/overlay/contact-info/"
        res = await browser.open_url(contact_overlay, screenshot_label="li_contact_info")
        if res.success and (not res.gate or not res.gate.restricted):
            txt = await browser.read_visible_text(8000)
            for email in extract_emails_from_text(txt):
                if email not in seen_emails:
                    seen_emails.add(email)
                    cat = categorize_email(email, host_name, "LinkedIn Profile")
                    discovered.append(
                        DiscoveredContact(
                            email=email,
                            email_category=cat,
                            phone=(extract_phones_from_text(txt) or [None])[0],
                            official_website=official_website,
                            contact_page=None,
                            source_type="LinkedIn Profile",
                            source_url=host_linkedin_url,
                            discovery_method="linkedin_profile_contact_info",
                            verification_status="Verified",
                            confidence_score=88,
                            notes="Extracted from host LinkedIn profile contact info.",
                        )
                    )

    # Priority 2: Original YouTube channel About section (MANDATORY when no suitable email found yet!)
    if not discovered and youtube_channel_url and allow_live_browser and browser is not None:
        for yt_target in (youtube_channel_url.rstrip("/") + "/about", youtube_channel_url.rstrip("/")):
            yt_res = await browser.open_url(yt_target, screenshot_label="youtube_about")
            if yt_res.success and (not yt_res.gate or not yt_res.gate.restricted):
                # Click '...more' channel description button if visible (never touches CAPTCHA)
                await browser.click("button:has-text('more'), yt-attributed-string button", timeout_ms=2000)
                yt_html = await browser.get_html()
                yt_about = parse_youtube_about_from_html(yt_html, youtube_channel_url)
                if yt_about["websites"] and not official_website:
                    official_website = yt_about["websites"][0]
                for email in yt_about["emails"]:
                    if email not in seen_emails:
                        seen_emails.add(email)
                        cat = categorize_email(email, host_name, "YouTube About")
                        discovered.append(
                            DiscoveredContact(
                                email=email,
                                email_category=cat,
                                phone=None,
                                official_website=official_website,
                                contact_page=None,
                                source_type="YouTube About",
                                source_url=yt_about["channel_url"],
                                discovery_method="youtube_channel_about_section",
                                verification_status="Partially Verified",
                                confidence_score=78,
                                notes="Discovered in original podcast YouTube channel About section.",
                            )
                        )
                if discovered:
                    break

    # Check official company website /contact page if still no email
    if not discovered and official_website and is_safe_company_website(official_website) and allow_live_browser and browser is not None:
        for candidate_url in [official_website, urljoin(official_website.rstrip("/") + "/", "contact")]:
            if not is_safe_company_website(candidate_url):
                continue
            web_res = await browser.open_url(candidate_url, screenshot_label="official_site_contact")
            if web_res.success and (not web_res.gate or not web_res.gate.restricted):
                txt = await browser.read_visible_text(10000)
                emails = extract_emails_from_text(txt)
                phones = extract_phones_from_text(txt)
                if emails:
                    for email in emails[:2]:
                        if email not in seen_emails:
                            seen_emails.add(email)
                            cat = categorize_email(email, host_name, "Official Website")
                            discovered.append(
                                DiscoveredContact(
                                    email=email,
                                    email_category=cat,
                                    phone=phones[0] if phones else None,
                                    official_website=official_website,
                                    contact_page=canonicalize_url(candidate_url),
                                    source_type="Official Website",
                                    source_url=canonicalize_url(candidate_url),
                                    discovery_method="company_website_contact_page",
                                    verification_status="Partially Verified",
                                    confidence_score=74,
                                    notes="Extracted from official host/company website.",
                                )
                            )
                    break

    # Check Tavily public web search for host/podcast contact or website
    if not discovered and host_name:
        t_res = await search_tavily(f"{host_name} {company_name or 'podcast'} contact email", max_results=3)
        for r in t_res:
            content = (r.get("content") or "") + " " + (r.get("title") or "")
            emails = extract_emails_from_text(content)
            for email in emails:
                if email not in seen_emails:
                    seen_emails.add(email)
                    cat = categorize_email(email, host_name, "Official Website")
                    discovered.append(
                        DiscoveredContact(
                            email=email,
                            email_category=cat,
                            phone=None,
                            official_website=official_website or r.get("url"),
                            contact_page=r.get("url"),
                            source_type="Official Website",
                            source_url=r.get("url"),
                            discovery_method="public_web_search_snippet",
                            verification_status="Partially Verified",
                            confidence_score=70,
                            notes=f"Discovered via public web search: {r.get('url')}",
                        )
                    )
            if discovered:
                break

    # Priority 3: Apollo fallback ONLY if no email found above
    if not discovered and host_name:
        apollo_match = await _apollo_person_enrich(
            host_name=host_name,
            company_name=company_name,
            host_linkedin_url=host_linkedin_url,
            official_website=official_website,
        )
        if apollo_match and apollo_match.get("email"):
            matched_company = (apollo_match.get("organization") or "").lower()
            comp_ok = bool(not company_name or (company_name.lower() in matched_company or matched_company in company_name.lower()))
            li_ok = bool(
                not host_linkedin_url
                or not apollo_match.get("linkedin_url")
                or canonicalize_url(host_linkedin_url) == canonicalize_url(apollo_match.get("linkedin_url"))
            )
            status = "Partially Verified" if (comp_ok and li_ok) else "Manual Review Required"
            conf = 80 if (comp_ok and li_ok) else 50
            discovered.append(
                DiscoveredContact(
                    email=apollo_match["email"].lower(),
                    email_category="host_direct_business",
                    phone=None,
                    official_website=official_website,
                    contact_page=None,
                    source_type="Apollo",
                    source_url=apollo_match.get("linkedin_url") or host_linkedin_url or "https://app.apollo.io",
                    discovery_method="apollo_people_match_fallback",
                    verification_status=status,
                    confidence_score=conf,
                    notes=f"Apollo enrichment match (company_match={comp_ok}, linkedin_match={li_ok}, apollo_status={apollo_match.get('email_status')}).",
                )
            )

    # Always record website/no-email record if nothing found so evidence isn't silently lost
    if not discovered:
        discovered.append(
            DiscoveredContact(
                email=None,
                email_category="unknown",
                phone=post_phones[0] if post_phones else None,
                official_website=official_website,
                contact_page=None,
                source_type="LinkedIn Post",
                source_url=youtube_channel_url or host_linkedin_url or post_data.get("post_url"),
                discovery_method="multi_source_search_exhausted",
                verification_status="Unverified",
                confidence_score=25,
                notes="No public business email discovered across LinkedIn, YouTube About, official website, or Apollo.",
            )
        )

    return discovered

