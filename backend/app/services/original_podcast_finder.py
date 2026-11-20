from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.browser_controller import BrowserController
from app.services.tavily_search import search_tavily
from app.services.page_extractor import (
    build_google_search_url,
    build_youtube_search_url,
    canonicalize_url,
    classify_external_links,
    parse_google_results_from_html,
    parse_youtube_search_results_from_html,
)


@dataclass
class OriginalPodcastResult:
    podcast_name: str
    episode_title: str | None
    original_podcast_url: str | None
    youtube_channel_name: str | None
    youtube_channel_url: str | None
    discovery_method: str  # description | comments | posting_account | youtube_search | google_search | manual_review
    confidence_score: int
    manual_review_required: bool
    research_notes: str
    evidence_urls: list[str]


def _extract_podcast_name_guess(caption: str, posting_account: str) -> str:
    patterns = [
        re.compile(r"(?:on|from|welcome to|tune in to)\s+(?:the\s+)?([A-Z][A-Za-z0-9&'\- ]{3,55}Podcast)", re.IGNORECASE),
        re.compile(r"([A-Z][A-Za-z0-9&'\- ]{3,55}Podcast)"),
        re.compile(r"([A-Z][A-Za-z0-9&'\- ]{3,55}Show)"),
    ]
    for pat in patterns:
        m = pat.search(caption or "")
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" .,-|")
    if posting_account and "podcast" in posting_account.lower():
        return posting_account.strip()
    return f"{posting_account.strip()} Real Estate Podcast" if posting_account else "Real Estate Podcast"


def _extract_episode_title_guess(caption: str) -> str | None:
    if not caption:
        return None
    m = re.search(r"(?:Episode\s*#?\d+[:\-\s]+|Ep\.?\s*\d+[:\-\s]+)([^\n.]{5,120})", caption, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    first_line = caption.strip().splitlines()[0][:140]
    return first_line if len(first_line) >= 8 else None


def _extract_distinctive_phrase(caption: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", caption or "")
    cleaned = re.sub(r"#\w+", "", cleaned).strip()
    words = [w for w in cleaned.split() if len(w) > 2]
    return " ".join(words[:10])


async def find_original_podcast(
    post_data: dict[str, Any],
    ai_entities: dict[str, Any] | None = None,
    browser: BrowserController | None = None,
    allow_live_search: bool = True,
) -> OriginalPodcastResult:
    """Module 4: Find the original podcast episode & YouTube channel.

    Order:
    1. LinkedIn video description / caption / post links
    2. Comments & posting-account links
    3. YouTube & Google search using distinctive phrases, podcast name, or host clues
    """
    caption = post_data.get("post_caption", "") or ""
    comments = post_data.get("comments", []) or []
    posting_account = post_data.get("posting_account", "") or ""
    external_urls = post_data.get("external_urls", []) or []

    podcast_name = (
        post_data.get("podcast_name")
        or (ai_entities or {}).get("podcast_name")
        or _extract_podcast_name_guess(caption, posting_account)
    )
    episode_title = post_data.get("episode_title") or (ai_entities or {}).get("episode_title") or _extract_episode_title_guess(caption)

    links_in_caption = classify_external_links(external_urls)
    evidence_urls: list[str] = []

    youtube_video_url = (
        post_data.get("video_url")
        if (post_data.get("video_url") and "watch?v=" in str(post_data.get("video_url")))
        else (links_in_caption["youtube_videos"][0] if links_in_caption["youtube_videos"] else None)
    )
    youtube_channel_url = post_data.get("youtube_channel_url") or (
        links_in_caption["youtube_channels"][0] if links_in_caption["youtube_channels"] else None
    )
    platform_url = links_in_caption["podcast_platforms"][0] if links_in_caption["podcast_platforms"] else None
    website_url = links_in_caption["websites"][0] if links_in_caption["websites"] else None

    if youtube_video_url or youtube_channel_url or platform_url:
        orig_url = youtube_video_url or platform_url or youtube_channel_url or website_url
        if orig_url:
            evidence_urls.append(orig_url)
        if youtube_channel_url:
            evidence_urls.append(youtube_channel_url)
        method = "comments" if comments and any(orig_url in c for c in comments if orig_url) else "description"
        return OriginalPodcastResult(
            podcast_name=podcast_name,
            episode_title=episode_title,
            original_podcast_url=canonicalize_url(orig_url),
            youtube_channel_name=podcast_name if youtube_channel_url else None,
            youtube_channel_url=canonicalize_url(youtube_channel_url),
            discovery_method=method,
            confidence_score=85 if youtube_channel_url or youtube_video_url else 75,
            manual_review_required=not bool(youtube_channel_url or youtube_video_url),
            research_notes=f"Original podcast link discovered directly in LinkedIn {method}.",
            evidence_urls=list(dict.fromkeys(evidence_urls)),
        )

    # Approach C: Search YouTube & Google when links aren't in caption/comments
    found_yt_channel_name = None
    found_yt_channel_url = None
    found_original_url = website_url
    discovery_method = "manual_review"
    confidence = 35
    notes = "No direct podcast link in caption or comments."

    if allow_live_search and browser is not None:
        query_parts = [podcast_name]
        host_clue = (ai_entities or {}).get("host_name")
        if host_clue:
            query_parts.append(str(host_clue))
        phrase = _extract_distinctive_phrase(caption)
        if phrase and len(query_parts) == 1:
            query_parts.append(phrase)
        search_query = " ".join(query_parts)[:120]

        yt_res = await browser.open_url(build_youtube_search_url(search_query), screenshot_label="yt_search")
        if yt_res.success and (not yt_res.gate or not yt_res.gate.restricted):
            yt_html = await browser.get_html()
            yt_matches = parse_youtube_search_results_from_html(yt_html)
            if yt_matches:
                best = yt_matches[0]
                found_original_url = best.get("video_url")
                found_yt_channel_url = best.get("channel_url")
                found_yt_channel_name = best.get("channel_name") or podcast_name
                discovery_method = "youtube_search"
                confidence = 72 if found_yt_channel_url else 58
                notes = f"Matched via YouTube search query '{search_query}' -> {best.get('title')}."
                if found_original_url:
                    evidence_urls.append(found_original_url)
                if found_yt_channel_url:
                    evidence_urls.append(found_yt_channel_url)

        # Fast Tavily search check if channel not yet found
        if not found_yt_channel_url:
            t_results = await search_tavily(f"{search_query} podcast YouTube channel", max_results=5)
            for r in t_results:
                u = r.get("url", "")
                if "youtube.com/@" in u or "youtube.com/channel/" in u or "youtube.com/c/" in u:
                    found_yt_channel_url = u
                    found_yt_channel_name = r.get("title") or podcast_name
                    discovery_method = "tavily_search"
                    confidence = 80
                    evidence_urls.append(u)
                    notes = f"Tavily search discovered YouTube channel: {u}."
                    break
                if not found_original_url and ("youtube.com/watch" in u or "spotify.com" in u or "apple.com" in u):
                    found_original_url = u
                    evidence_urls.append(u)

        if not found_yt_channel_url:
            g_res = await browser.open_url(build_google_search_url(f"{search_query} podcast youtube"), screenshot_label="google_search")
            if g_res.success and (not g_res.gate or not g_res.gate.restricted):
                g_html = await browser.get_html()
                g_matches = parse_google_results_from_html(g_html)
                for item in g_matches:
                    u = item["url"]
                    if "youtube.com/@" in u or "youtube.com/channel/" in u:
                        found_yt_channel_url = u
                        found_yt_channel_name = item["title"]
                        discovery_method = "google_search"
                        confidence = 68
                        evidence_urls.append(u)
                        notes += f" Google search located channel: {u}."
                        break
                    if not found_original_url and any(k in u.lower() for k in ("podcast", "spotify", "apple", "youtube")):
                        found_original_url = u
                        discovery_method = "google_search"
                        confidence = 60
                        evidence_urls.append(u)

    needs_review = confidence < 65 or not bool(found_yt_channel_url)
    return OriginalPodcastResult(
        podcast_name=podcast_name,
        episode_title=episode_title,
        original_podcast_url=canonicalize_url(found_original_url),
        youtube_channel_name=found_yt_channel_name,
        youtube_channel_url=canonicalize_url(found_yt_channel_url),
        discovery_method=discovery_method,
        confidence_score=confidence,
        manual_review_required=needs_review,
        research_notes=notes,
        evidence_urls=list(dict.fromkeys(evidence_urls)),
    )

