from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


def _call_gemini_sync(
    prompt: str, inline_parts: list[dict[str, Any]] | None = None, json_mode: bool = True
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        return None
    model = settings.gemini_model or "gemini-flash-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if inline_parts:
        parts.extend(inline_parts)
    payload: dict[str, Any] = {"contents": [{"parts": parts}]}
    if json_mode:
        payload["generationConfig"] = {"response_mime_type": "application/json"}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key.strip()},
    )
    for attempt in range(1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                cand = data.get("candidates", [])
                if cand:
                    text_out = cand[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    logger.info("Gemini (%s) response: %d chars", model, len(text_out))
                    if json_mode:
                        return json.loads(text_out)
                    return {"text": text_out}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini call attempt %d error: %s", attempt + 1, exc)
    return None


def extract_keyword_from_text(command: str) -> str:
    """Extract targeted podcast topic, niche, or role from user command with smart normalization."""
    import re

    cleaned = command.strip()

    # 1. Strip leading action triggers
    lead_patterns = [
        r"^(?:can\s+you\s+)?(?:please\s+)?(?:search|find|look\s+for|research|discover|scrape|get|show\s+me)\s+(?:for\s+)?(?:me\s+)?",
        r"^(?:start\s+automation\s+for|automate\s+search\s+for|run\s+research\s+on)\s+",
        r"^(?:i\s+want\s+to\s+search\s+for|i\s+need\s+to\s+search\s+for|i\s+want\s+to\s+find|i\s+want)\s+",
        r"^(?:can\s+you\s+please\s+find|can\s+you\s+find)\s+",
        r"^(?:please\s+)?(?:export|download)\s+(?:all\s+)?",
    ]
    for pat in lead_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # 2. Strip trailing boilerplates
    trail_patterns = [
        r"\s+(?:and\s+)?show\s+me\s+what\s+results\s+(?:is\s+it\s+giving|it\s+gives|are\s+there).*$",
        r"\s+(?:and\s+)?show\s+me\s+results.*$",
        r"\s+(?:and\s+)?show\s+me.*$",
        r"\s+for\s+me.*$",
        r"\s+type\s+this.*$",
        r"\s+(?:and\s+)?(?:locate|find)\s+(?:their\s+)?(?:business\s+)?(?:emails?|contacts?).*$",
        r"\s+(?:and\s+)?(?:identify|extract)\s+hosts?.*$",
        r"\s+prioritize\s+recent\s+video\s+posts.*$",
        r"\s+and\s+search.*$",
        r"\s+hosts?\s+and\s+emails?.*$",
        r"\s+hosts?.*$",
        r"\s+leads\s+to\s+(?:excel|csv|xlsx).*$",
        r"\s+to\s+(?:excel|csv|xlsx).*$",
        r"\s+leads.*$",
    ]
    for pat in trail_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    cleaned = cleaned.strip(" ,.?!:;\"\'")
    if not cleaned:
        return "Real Estate Podcast"

    # Normalize 's podcast' shorthand or typo to 'SaaS Podcast'
    cleaned = re.sub(r"\b[sS]\s+[pP]odcast\b", "SaaS Podcast", cleaned)

    if "podcast" not in cleaned.lower() and "show" not in cleaned.lower():
        cleaned = f"{cleaned} Podcast"

    words = cleaned.split()
    capitalized = []
    for w in words:
        w_lower = w.lower()
        if w_lower == "saas":
            capitalized.append("SaaS")
        elif w_lower in ("ai", "b2b", "b2c", "cto", "ceo", "cmo", "vc", "cre", "it", "llm", "hr"):
            capitalized.append(w.upper())
        elif w_lower in ("and", "or", "for", "of", "in", "on", "with", "the", "to", "by"):
            capitalized.append(w_lower)
        else:
            capitalized.append(w.capitalize())
    return " ".join(capitalized)


class AIPlanner:
    """Multi-provider AI planner supporting OpenAI GPT-4o and Google Gemini with deterministic fallback."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI | None:
        settings = get_settings()
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            return None
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key.strip())
        return self._client

    @property
    def is_configured(self) -> bool:
        settings = get_settings()
        has_openai = bool(settings.openai_api_key and settings.openai_api_key.strip())
        has_gemini = bool(settings.gemini_api_key and settings.gemini_api_key.strip())
        return has_openai or has_gemini

    async def parse_command_intent(self, command: str) -> dict[str, Any]:
        """Classify user's Jarvis instruction into actionable intent and parameters."""
        lower = command.lower().strip()

        # Deterministic fast-path for explicit control/export/status queries
        if any(w in lower for w in ("export", "download", "excel", "xlsx", "csv")):
            fmt = "csv" if "csv" in lower else "xlsx"
            preset = "all"
            if "verified" in lower:
                preset = "verified"
            elif "email" in lower:
                preset = "email_available"
            elif "manual review" in lower or "review" in lower:
                preset = "manual_review"
            elif "qualified" in lower:
                preset = "qualified"
            days = 7 if ("7 day" in lower or "seven day" in lower or "last week" in lower) else None

            # Extract target keyword if user asked to export a specific topic (e.g. "export SaaS podcast leads")
            kw_clean = extract_keyword_from_text(command)
            kw_target = None
            if kw_clean and kw_clean.lower() not in (
                "excel podcast", "csv podcast", "export podcast", "leads podcast", "download podcast",
                "all podcast", "verified podcast"
            ):
                kw_target = kw_clean

            return {
                "intent": "export_leads",
                "format": fmt,
                "preset": preset,
                "last_days": days,
                "keyword": kw_target,
                "summary": f"Prepare {fmt.upper()} export ({preset}){f' for {kw_target}' if kw_target else ''}.",
            }

        # Deterministic fast-path for stop / pause / resume commands
        if any(w in lower for w in ("stop", "cancel", "halt", "terminate", "kill", "abort", "shut down", "end research")):
            return {"intent": "stop_research", "summary": "Stop the active research task."}
        if any(w in lower for w in ("pause", "freeze", "hold on")):
            return {"intent": "pause_research", "summary": "Pause the active research task."}
        if any(w in lower for w in ("resume", "continue", "unpause")):
            return {"intent": "resume_research", "summary": "Resume the paused research task."}
        if any(p in lower for p in ("show me the research", "research completed so far", "status", "summary", "overview", "what leads", "how many")):
            return {"intent": "show_research_summary", "summary": "Summarize collected research from PostgreSQL."}
        if lower in {"hi", "hello", "hey", "help", "what can you do", "who are you"}:
            return {"intent": "conversational_help", "summary": "Provide conversational help and guidance."}

        # Check scope exclusions (Section 2)
        excluded_phrases = ("guest company", "marketing decision", "marketing employee", "cold email", "send email", "send linkedin message", "whatsapp")
        if any(phrase in lower for phrase in excluded_phrases):
            return {
                "intent": "out_of_scope",
                "summary": "This request includes functionality outside YoursBuddy AI v1 scope (strictly podcast discovery & podcast-host research, no guest prospecting or automated messaging).",
            }

        prompt = (
            "You are the planning engine for YoursBuddy AI, an autonomous podcast-host research assistant. "
            "Extract the user's intent and specific target topic/role/niche. "
            "Return valid JSON with keys: "
            "intent (start_research | verify_host | check_youtube_email | show_research_summary | export_leads | pause_research | resume_research | stop_research | out_of_scope), "
            "keyword (the specific podcast topic/niche/role extracted from command, e.g. 'SaaS Podcast and Tech Podcast', 'AI Podcast', 'Fintech Podcast', or 'Real Estate Podcast' if no topic specified), "
            "max_posts (int 1..25, default 10), "
            "target_name (string or null), "
            "summary (short human-readable plan). "
            f"User command: {command}"
        )

        # 1. Try Gemini
        gemini_parsed = await asyncio.to_thread(_call_gemini_sync, prompt)
        if gemini_parsed and isinstance(gemini_parsed, dict) and "intent" in gemini_parsed:
            return gemini_parsed

        # 2. Try OpenAI
        client = self._get_client()
        if client is not None:
            try:
                settings = get_settings()
                resp = await client.chat.completions.create(
                    model=settings.openai_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are the planning engine for YoursBuddy AI. "
                                "Classify command into JSON with intent, keyword, max_posts, target_name, summary."
                            ),
                        },
                        {"role": "user", "content": command},
                    ],
                    temperature=0.1,
                )
                content = resp.choices[0].message.content or "{}"
                parsed = json.loads(content)
                if "intent" in parsed:
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI intent parsing fallback due to error: %s", exc)

        # Deterministic research command fallback: dynamically extract keyword/niche from user command
        keyword = extract_keyword_from_text(command)

        return {
            "intent": "start_research",
            "keyword": keyword,
            "max_posts": get_settings().max_posts_per_run,
            "summary": f"Run LinkedIn -> Video Quality -> Original Podcast -> Host & Company -> Contact Discovery workflow for '{keyword}'.",
        }

    async def assess_video_frames_with_vision(
        self,
        frame_paths: list[str],
        caption: str,
        video_meta: dict[str, Any],
        audio_accessible: bool,
    ) -> dict[str, Any] | None:
        """Analyze actual captured video frames with Gemini or OpenAI Vision."""
        if not frame_paths:
            return None

        prompt = (
            "Evaluate these real extracted frames from a LinkedIn video post for a real estate podcast research task.\n"
            f"Post caption: {caption[:1200]}\n"
            f"Video element metadata: {json.dumps(video_meta)}\n"
            f"Audio stream accessible: {audio_accessible}\n"
            "Return strict JSON with keys:\n"
            "video_score (0-100), video_quality (Low|Medium|High), "
            "audio_quality (Low|Medium|High|Unknown - MUST be 'Unknown' if audio_accessible is false), "
            "lighting (Poor|Average|Good), setup_quality (Poor|Average|Professional), "
            "content_relevance (Relevant|Partially Relevant|Not Relevant), "
            "is_podcast (bool), is_real_estate (bool), "
            "assessment_notes (concise factual explanation referencing what is visible)."
        )

        inline_images: list[dict[str, Any]] = []
        for path_str in frame_paths[:2]:
            p = Path(path_str)
            if p.exists() and p.is_file():
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                inline_images.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": b64
                    }
                })

        # Try Gemini Vision
        gemini_res = await asyncio.to_thread(_call_gemini_sync, prompt, inline_images)
        if gemini_res and isinstance(gemini_res, dict) and "video_score" in gemini_res:
            if not audio_accessible:
                gemini_res["audio_quality"] = "Unknown"
            return gemini_res

        # Try OpenAI Vision
        client = self._get_client()
        if client is not None:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for path_str in frame_paths[:2]:
                p = Path(path_str)
                if p.exists() and p.is_file():
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"},
                    })
            try:
                settings = get_settings()
                resp = await client.chat.completions.create(
                    model=settings.openai_model,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": content_parts}],
                    temperature=0.1,
                )
                result = json.loads(resp.choices[0].message.content or "{}")
                if not audio_accessible:
                    result["audio_quality"] = "Unknown"
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI vision assessment failed: %s", exc)

        return None

    async def extract_podcast_and_host_entities(
        self, caption: str, posting_account: str, comments_text: str = ""
    ) -> dict[str, Any] | None:
        """Use Gemini or OpenAI reasoning to distinguish podcast name, episode title, and HOST (not guest)."""
        prompt = (
            "Identify ONLY the podcast show name, episode title, and the PODCAST HOST (not the guest or interviewee). "
            "If uncertain who the host is, set host_name to null and needs_manual_review to true. Never guess. "
            f"Posting account: {posting_account}\nCaption:\n{caption[:2500]}\nComments:\n{comments_text[:1500]}\n"
            "Return JSON: {podcast_name, episode_title, host_name, host_confidence (0-100), distinctive_phrases (list[str]), needs_manual_review (bool), reasoning (str)}."
        )

        # 1. Try Gemini
        gemini_res = await asyncio.to_thread(_call_gemini_sync, prompt)
        if gemini_res and isinstance(gemini_res, dict) and "host_name" in gemini_res:
            return gemini_res

        # 2. Try OpenAI
        client = self._get_client()
        if client is not None:
            try:
                settings = get_settings()
                resp = await client.chat.completions.create(
                    model=settings.openai_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": "Identify ONLY the podcast show name and PODCAST HOST. Never guess.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                return json.loads(resp.choices[0].message.content or "{}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI host extraction failed: %s", exc)

        return None


ai_planner = AIPlanner()


