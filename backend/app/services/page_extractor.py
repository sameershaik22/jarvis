from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
URL_REGEX = re.compile(r"https?://[^\s<>\"')\]}]+")

NOISE_EMAIL_DOMAINS = {
    "example.com",
    "sentry.io",
    "w3.org",
    "schema.org",
    "youtube.com",
    "linkedin.com",
    "googleusercontent.com",
    "gstatic.com",
    "tavily.com",
    "openai.com",
    "google.com",
    "cloudflare.com",
}


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip().rstrip(".,;)")
    try:
        parsed = urlparse(cleaned)
        if not parsed.scheme or not parsed.netloc:
            return cleaned
        # Remove common tracking query parameters while keeping essential IDs (e.g. YouTube ?v=)
        qs = parse_qs(parsed.query, keep_blank_values=False)
        filtered_qs = {
            k: v
            for k, v in qs.items()
            if not k.lower().startswith("utm_")
            and k.lower() not in {"trk", "trkinfo", "rcm", "lipi", "licu", "ref", "fbclid", "gclid"}
        }
        new_query = urlencode(filtered_qs, doseq=True)
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", new_query, ""))
    except Exception:  # noqa: BLE001
        return cleaned


def extract_emails_from_text(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in EMAIL_REGEX.findall(text):
        lower = match.lower().strip(".")
        # Trim accidental concatenated text after common TLDs (e.g. .commaster -> .com)
        for tld in (".com", ".org", ".net", ".edu", ".gov", ".io", ".co"):
            idx = lower.rfind(tld)
            if idx != -1 and idx + len(tld) < len(lower):
                trailing = lower[idx + len(tld):]
                if trailing.isalpha() and len(trailing) >= 2:
                    lower = lower[:idx + len(tld)]
                    break
        domain = lower.split("@")[-1]
        if domain in NOISE_EMAIL_DOMAINS:
            continue
        if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")):
            continue
        if lower not in seen:
            seen.add(lower)
            found.append(lower)
    return found


def extract_phones_from_text(text: str) -> list[str]:
    if not text:
        return []
    phones: list[str] = []
    for m in PHONE_REGEX.findall(text):
        cleaned = re.sub(r"\s+", " ", m).strip()
        if len(re.sub(r"\D", "", cleaned)) >= 10 and cleaned not in phones:
            phones.append(cleaned)
    return phones


def extract_urls_from_text(text: str) -> list[str]:
    if not text:
        return []
    urls: list[str] = []
    for raw in URL_REGEX.findall(text):
        c = canonicalize_url(raw)
        if c and c not in urls:
            urls.append(c)
    return urls


def classify_external_links(urls: list[str]) -> dict[str, list[str]]:
    youtube_videos: list[str] = []
    youtube_channels: list[str] = []
    podcast_platforms: list[str] = []
    linkedin_profiles: list[str] = []
    linkedin_companies: list[str] = []
    websites: list[str] = []

    for u in urls:
        lower = u.lower()
        if "youtube.com/watch" in lower or "youtu.be/" in lower:
            youtube_videos.append(u)
        elif "youtube.com/@" in lower or "youtube.com/channel/" in lower or "youtube.com/c/" in lower:
            youtube_channels.append(u)
        elif any(p in lower for p in ("podcasts.apple.com", "open.spotify.com/show", "open.spotify.com/episode", "buzzsprout", "libsyn", "podbean", "anchor.fm")):
            podcast_platforms.append(u)
        elif "linkedin.com/in/" in lower:
            linkedin_profiles.append(u)
        elif "linkedin.com/company/" in lower:
            linkedin_companies.append(u)
        elif not any(d in lower for d in (
            "linkedin.com", "google.com", "instagram.com", "facebook.com",
            "fb.com", "tiktok.com", "twitter.com", "x.com", "threads.net",
            "pinterest.com", "reddit.com", "t.me", "whatsapp.com"
        )):
            websites.append(u)

    return {
        "youtube_videos": youtube_videos,
        "youtube_channels": youtube_channels,
        "podcast_platforms": podcast_platforms,
        "linkedin_profiles": linkedin_profiles,
        "linkedin_companies": linkedin_companies,
        "websites": websites,
    }


def build_linkedin_video_search_url(keyword: str = "Real Estate Podcast") -> str:
    encoded = quote_plus(keyword.strip() or "Real Estate Podcast")
    return (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={encoded}&origin=FACETED_SEARCH&sortBy=%22date_posted%22&contentType=%22videos%22"
    )


def build_youtube_search_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(query.strip())}"


def build_google_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query.strip())}"


def parse_linkedin_posts_from_html(html: str, keyword: str = "Real Estate Podcast") -> list[dict[str, Any]]:
    """Deterministic HTML parser for LinkedIn search content/posts DOM."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Support both standard LinkedIn feed cards and generic semantic article/result containers
    containers = soup.select(
        "div.feed-shared-update-v2, li.reusable-search__result-container, div.search-content__result, article"
    )
    if not containers:
        containers = [soup]

    kw_tokens = [t.lower() for t in keyword.split() if len(t) > 2]

    for node in containers:
        links = [a.get("href", "") for a in node.find_all("a", href=True)]
        post_url = None
        account_url = None
        account_name = ""
        for href in links:
            abs_href = href if href.startswith("http") else f"https://www.linkedin.com{href}"
            if any(marker in abs_href for marker in ("/feed/update/", "/posts/", "urn:li:activity:")):
                post_url = canonicalize_url(abs_href)
            elif ("/in/" in abs_href or "/company/" in abs_href) and not account_url:
                account_url = canonicalize_url(abs_href)

        # Fallback: extract activity URN from data-urn / data-id attributes on LinkedIn feed cards
        if not post_url:
            for attr in ("data-urn", "data-id"):
                urn_val = node.get(attr) or ""
                if "urn:li:activity:" in urn_val:
                    urn_part = urn_val[urn_val.index("urn:li:activity:") :].split(",")[0].strip()
                    post_url = f"https://www.linkedin.com/feed/update/{urn_part}"
                    break

        if not post_url or post_url in seen_urls:
            continue

        # Posting account name
        actor_el = node.select_one(
            ".update-components-actor__name, .feed-shared-actor__name, .entity-result__title-text, a[href*='/in/'], a[href*='/company/']"
        )
        if actor_el:
            account_name = re.sub(r"\s+", " ", actor_el.get_text(" ", strip=True))[:200]

        # Caption text
        caption_el = node.select_one(
            ".feed-shared-update-v2__description, .update-components-text, .feed-shared-text, p"
        )
        caption = re.sub(r"\s+", " ", (caption_el.get_text(" ", strip=True) if caption_el else node.get_text(" ", strip=True)))

        # Video element or video link
        video_tag = node.find("video")
        video_url = None
        if video_tag:
            video_url = video_tag.get("src") or (video_tag.find("source").get("src") if video_tag.find("source") else None)
        if not video_url:
            for href in links:
                if "video" in href.lower() or "youtu" in href.lower():
                    video_url = href
                    break

        # Published time label
        time_el = node.select_one("time, .update-components-actor__sub-description, .feed-shared-actor__sub-description")
        published_label = re.sub(r"\s+", " ", time_el.get_text(" ", strip=True))[:80] if time_el else None

        # Comments text if visible inside container
        comment_els = node.select(".comments-comment-item__main-content, .comments-comments-list__comment-item")
        comments = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in comment_els if c.get_text(strip=True)]

        caption_lower = caption.lower()
        matched_keywords = [tok for tok in kw_tokens if tok in caption_lower]
        if "podcast" in caption_lower and "podcast" not in matched_keywords:
            matched_keywords.append("podcast")

        seen_urls.add(post_url)
        posts.append(
            {
                "post_url": post_url,
                "post_caption": caption[:4000],
                "posting_account": account_name or "LinkedIn Account",
                "posting_account_url": account_url,
                "video_url": video_url,
                "has_video_element": bool(video_tag or video_url),
                "published_label": published_label,
                "keywords_matched": matched_keywords,
                "external_urls": extract_urls_from_text(caption + " " + " ".join(comments)),
                "comments": comments,
            }
        )

    return posts


def parse_youtube_search_results_from_html(html: str) -> list[dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. Parse top channel cards (<ytd-channel-renderer>)
    channel_cards = soup.select("ytd-channel-renderer")
    for card in channel_cards:
        ch_link = card.select_one("a#main-link, a[href*='/@'], a[href*='/channel/'], a[href*='/c/']")
        if not ch_link:
            continue
        href = ch_link.get("href", "")
        ch_url = canonicalize_url(href if href.startswith("http") else f"https://www.youtube.com{href}")
        if not ch_url or ch_url in seen:
            continue
        name_el = card.select_one("yt-formatted-string#text") or card.select_one("#channel-title, h3")
        ch_name = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)) if name_el else None
        if ch_name:
            parts = ch_name.split()
            half = len(parts) // 2
            if len(parts) >= 2 and len(parts) % 2 == 0 and parts[:half] == parts[half:]:
                ch_name = " ".join(parts[:half])
        seen.add(ch_url)
        results.append(
            {
                "title": f"{ch_name or 'Real Estate'} Podcast Channel",
                "video_url": ch_url,
                "channel_name": ch_name or "Real Estate Podcast",
                "channel_url": ch_url,
                "is_channel": True,
            }
        )

    # 2. Prefer real YouTube video cards (<ytd-video-renderer>) so channel links & titles match accurately
    video_cards = soup.select("ytd-video-renderer")
    if video_cards:
        for card in video_cards:
            title_link = card.select_one("a#video-title") or card.select_one("a[href*='/watch?v=']")
            if not title_link:
                continue
            href = title_link.get("href", "")
            if "/watch?v=" not in href:
                continue
            full_url = canonicalize_url(href if href.startswith("http") else f"https://www.youtube.com{href}")
            # Strip timestamp parameter &t=... when canonicalizing watch URLs
            if full_url and "&t=" in full_url:
                full_url = full_url.split("&t=")[0]
            if not full_url or full_url in seen:
                continue
            title = re.sub(r"\s+", " ", title_link.get("title") or title_link.get_text(" ", strip=True))
            if not title or len(title) < 4:
                continue
            ch_link = card.select_one(
                "ytd-channel-name a[href*='/@'], ytd-channel-name a[href*='/channel/'], ytd-channel-name a[href*='/c/'], a[href*='/@'], a[href*='/channel/'], a[href*='/c/']"
            )
            channel_name = None
            channel_url = None
            if ch_link:
                ch_href = ch_link.get("href", "")
                channel_url = canonicalize_url(ch_href if ch_href.startswith("http") else f"https://www.youtube.com{ch_href}")
                channel_name = re.sub(r"\s+", " ", ch_link.get_text(" ", strip=True)) or None
            seen.add(full_url)
            results.append(
                {
                    "title": title,
                    "video_url": full_url,
                    "channel_name": channel_name,
                    "channel_url": channel_url,
                }
            )
            if len(results) >= 10:
                break
        if results:
            return results

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/watch?v=" not in href or "&t=" in href:
            continue
        full_url = canonicalize_url(href if href.startswith("http") else f"https://www.youtube.com{href}")
        if not full_url or full_url in seen:
            continue
        title = re.sub(r"\s+", " ", a.get("title") or a.get_text(" ", strip=True))
        if not title or len(title) < 4:
            continue
        parent = a.find_parent(["ytd-video-renderer", "article", "div"])
        channel_name = None
        channel_url = None
        if parent:
            ch_link = parent.select_one("a[href*='/@'], a[href*='/channel/'], a[href*='/c/']")
            if ch_link:
                ch_href = ch_link.get("href", "")
                channel_url = canonicalize_url(ch_href if ch_href.startswith("http") else f"https://www.youtube.com{ch_href}")
                channel_name = re.sub(r"\s+", " ", ch_link.get_text(" ", strip=True))
        seen.add(full_url)
        results.append(
            {
                "title": title,
                "video_url": full_url,
                "channel_name": channel_name,
                "channel_url": channel_url,
            }
        )
        if len(results) >= 10:
            break
    return results


def parse_youtube_about_from_html(html: str, channel_url: str) -> dict[str, Any]:
    if not html:
        return {"channel_url": channel_url, "emails": [], "websites": [], "description": ""}
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # Also inspect embedded ytInitialData script text if present (often holds full channel description/links)
    script_texts: list[str] = []
    for script in soup.find_all("script"):
        s_txt = script.string or ""
        if "ytInitialData" in s_txt or "channelMetadataRenderer" in s_txt:
            script_texts.append(s_txt)
    combined_text = text + "\n" + "\n".join(script_texts)

    emails = extract_emails_from_text(combined_text)

    # Also check mailto: links and YouTube redirect links (/redirect?q=...)
    ignored_domains = (
        "youtube.com",
        "youtubekids.com",
        "youtube-nocookie.com",
        "studio.youtube.com",
        "youtu.be",
        "google.com",
        "gstatic.com",
        "ggpht.com",
        "googleapis.com",
        "instagram.com",
        "facebook.com",
        "fb.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "threads.net",
        "pinterest.com",
        "reddit.com",
        "t.me",
        "whatsapp.com",
        "spotify.com",
        "apple.com",
        "podcasts.apple.com",
    )
    websites: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            addr = href.replace("mailto:", "").split("?")[0].strip().lower()
            if addr and addr not in emails:
                emails.append(addr)
        elif "/redirect?" in href:
            qs = parse_qs(urlparse(href).query)
            if "q" in qs and qs["q"]:
                target = canonicalize_url(qs["q"][0])
                host = urlparse(target or "").netloc.lower()
                if target and target not in websites and not any(d in host for d in ignored_domains):
                    websites.append(target)
        elif href.startswith("http"):
            c = canonicalize_url(href)
            host = urlparse(c or "").netloc.lower()
            if c and c not in websites and not any(d in host for d in ignored_domains):
                websites.append(c)

    title_tag = soup.find("title")
    channel_name = title_tag.get_text(strip=True).replace(" - YouTube", "") if title_tag else ""
    return {
        "channel_name": channel_name,
        "channel_url": canonicalize_url(channel_url) or channel_url,
        "emails": emails,
        "websites": websites[:10],
        "description": text[:3000],
    }


UNSAFE_WEBSITE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "google.com",
    "gstatic.com",
    "ggpht.com",
    "googleapis.com",
    "linkedin.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "threads.net",
    "pinterest.com",
    "reddit.com",
    "t.me",
    "whatsapp.com",
    "spotify.com",
    "apple.com",
    "podcasts.apple.com",
)


def is_safe_company_website(url: str | None) -> bool:
    """Return True only if url is an HTTP/HTTPS link and not a social/media platform with login walls."""
    if not url or not str(url).startswith("http"):
        return False
    host = urlparse(str(url)).netloc.lower()
    return not any(d in host for d in UNSAFE_WEBSITE_DOMAINS)


def parse_google_results_from_html(html: str) -> list[dict[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/url?q="):
            qs = parse_qs(urlparse(href).query)
            href = qs.get("q", [""])[0]
        if not href.startswith("http") or "google.com" in urlparse(href).netloc:
            continue
        c = canonicalize_url(href)
        if not c or c in seen:
            continue
        h3 = a.find("h3")
        title = re.sub(r"\s+", " ", h3.get_text(" ", strip=True) if h3 else a.get_text(" ", strip=True))
        if not title or len(title) < 4:
            continue
        seen.add(c)
        results.append({"title": title, "url": c})
        if len(results) >= 10:
            break
    return results

