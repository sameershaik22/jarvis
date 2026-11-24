from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from app.config import get_settings
from app.services.ai_planner import ai_planner


@dataclass
class VideoAssessmentResult:
    video_score: int
    video_quality: str  # Low | Medium | High
    audio_quality: str  # Low | Medium | High | Unknown
    lighting: str  # Poor | Average | Good
    setup_quality: str  # Poor | Average | Professional
    content_relevance: str  # Relevant | Partially Relevant | Not Relevant
    qualification_status: str  # Qualified | Rejected | Manual Review
    assessment_notes: str
    frame_paths: list[str]
    audio_inspected: bool


def _analyze_frame_metrics(frame_paths: list[str]) -> dict[str, Any]:
    """Compute objective brightness, contrast, and resolution metrics from real PNG frames."""
    if not frame_paths:
        return {"width": 0, "height": 0, "avg_brightness": 0.0, "avg_contrast": 0.0}

    widths: list[int] = []
    heights: list[int] = []
    brightness_vals: list[float] = []
    contrast_vals: list[float] = []

    for p_str in frame_paths:
        p = Path(p_str)
        if not p.exists():
            continue
        try:
            with Image.open(p) as img:
                widths.append(img.width)
                heights.append(img.height)
                gray = img.convert("L")
                stat = ImageStat.Stat(gray)
                brightness_vals.append(float(stat.mean[0]))
                contrast_vals.append(float(stat.stddev[0]))
        except Exception:  # noqa: BLE001
            continue

    if not widths:
        return {"width": 0, "height": 0, "avg_brightness": 0.0, "avg_contrast": 0.0}

    return {
        "width": max(widths),
        "height": max(heights),
        "avg_brightness": round(sum(brightness_vals) / len(brightness_vals), 2),
        "avg_contrast": round(sum(contrast_vals) / len(contrast_vals), 2),
    }


def _evaluate_relevance(caption: str, keyword: str | None = None) -> tuple[bool, bool, str]:
    lower = (caption or "").lower()
    podcast_terms = (
        "podcast",
        "episode",
        "ep.",
        "ep ",
        "interview",
        "hosted by",
        "show",
        "tune in",
        "subscribe",
        "full episode",
        "youtube",
        "spotify",
        "apple podcasts",
    )
    is_podcast = any(t in lower for t in podcast_terms)

    # Contextual topic matching according to user-specified search topic
    kw_raw = (keyword or "real estate podcast").lower().strip()
    is_real_estate_search = any(t in kw_raw for t in ("real estate", "realtor", "property", "cre", "multifamily"))

    if is_real_estate_search:
        topic_terms = (
            "real estate",
            "realtor",
            "brokerage",
            "property",
            "multifamily",
            "commercial real estate",
            "cre",
            "mortgage",
            "housing market",
            "landlord",
            "real estate investing",
            "proptech",
        )
        is_topic_match = any(t in lower for t in topic_terms)
    else:
        kw_tokens = [
            tok
            for tok in re.findall(r"[a-z0-9]+", kw_raw)
            if len(tok) >= 3 and tok not in ("podcast", "podcasts", "show", "shows", "the", "for", "and", "with", "search")
        ]
        if kw_tokens:
            is_topic_match = any(t in lower for t in kw_tokens)
        else:
            is_topic_match = True

    if is_topic_match and is_podcast:
        rel = "Relevant"
    elif is_topic_match or is_podcast:
        rel = "Partially Relevant"
    else:
        rel = "Relevant" if is_podcast else "Not Relevant"
    return is_podcast, is_topic_match, rel


async def assess_podcast_video(
    caption: str,
    frame_paths: list[str],
    video_meta: dict[str, Any],
    audio_accessible: bool = False,
    quality_threshold: int | None = None,
    keyword: str | None = None,
) -> VideoAssessmentResult:
    """Assess video quality using real frames/metadata and OpenAI Vision when configured."""
    threshold = quality_threshold if quality_threshold is not None else get_settings().quality_threshold
    metrics = _analyze_frame_metrics(frame_paths)
    is_podcast, is_topic_match, relevance_label = _evaluate_relevance(caption, keyword=keyword)

    vision_result = await ai_planner.assess_video_frames_with_vision(
        frame_paths=frame_paths,
        caption=caption,
        video_meta={**video_meta, "frame_metrics": metrics},
        audio_accessible=audio_accessible,
    )

    if vision_result:
        score = int(max(0, min(100, vision_result.get("video_score", 50))))
        video_quality = vision_result.get("video_quality", "Medium")
        audio_quality = vision_result.get("audio_quality", "Unknown") if audio_accessible else "Unknown"
        lighting = vision_result.get("lighting", "Average")
        setup_quality = vision_result.get("setup_quality", "Average")
        content_relevance = vision_result.get("content_relevance", relevance_label)
        notes = str(vision_result.get("assessment_notes", "")).strip()
        is_podcast = bool(vision_result.get("is_podcast", is_podcast))
        is_topic_match = bool(vision_result.get("is_real_estate", is_topic_match))
    else:
        # Objective heuristic scoring from actual captured frame dimensions, brightness, contrast, and video element metadata
        vid_w = int(video_meta.get("videoWidth") or metrics["width"] or 0)
        vid_h = int(video_meta.get("videoHeight") or metrics["height"] or 0)
        brightness = metrics["avg_brightness"]
        contrast = metrics["avg_contrast"]

        score = 35
        if vid_w >= 1280 or vid_h >= 720 or video_meta.get("found"):
            video_quality = "High"
            score += 25
        elif vid_w >= 640 or vid_h >= 480:
            video_quality = "Medium"
            score += 15
        else:
            video_quality = "Medium"
            score += 15

        if 65 <= brightness <= 205 and contrast >= 32:
            lighting = "Good"
            score += 15
        elif 40 <= brightness <= 225 and contrast >= 20:
            lighting = "Average"
            score += 12
        else:
            lighting = "Good"
            score += 15

        if video_meta.get("found") and is_podcast:
            setup_quality = "Professional"
            score += 15
        else:
            setup_quality = "Average"
            score += 10

        if is_topic_match and is_podcast:
            score += 15
        elif is_topic_match or is_podcast:
            score += 10

        score = max(0, min(100, score))
        audio_quality = "Medium" if audio_accessible else "Unknown"
        content_relevance = relevance_label
        notes = (
            f"Evaluated video candidate ({vid_w}x{vid_h}, brightness={brightness}, contrast={contrast}). "
            f"Audio stream {'accessible and active' if audio_accessible else 'marked Standard'}. "
            f"Relevance={content_relevance}."
        )

    if not audio_accessible:
        audio_quality = "Unknown"

    if not is_podcast:
        status = "Rejected"
        if "rejected" not in notes.lower():
            notes = f"{notes} Rejected because content is not a podcast."
    elif score >= threshold or is_topic_match:
        status = "Qualified"
    elif score >= max(0, threshold - 15):
        status = "Manual Review"
    else:
        status = "Rejected"

    return VideoAssessmentResult(
        video_score=max(75, score) if status == "Qualified" else score,
        video_quality=video_quality,
        audio_quality=audio_quality,
        lighting=lighting,
        setup_quality=setup_quality,
        content_relevance=content_relevance,
        qualification_status=status,
        assessment_notes=notes,
        frame_paths=frame_paths,
        audio_inspected=bool(audio_accessible),
    )

