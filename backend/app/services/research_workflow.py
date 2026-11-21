from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AgentActivityLog, AgentMessage, ResearchTask
from app.db.session import SessionLocal
from app.services.ai_planner import ai_planner
from app.services.browser_controller import BrowserController, browser_controller
from app.services.browser_manager import browser_manager
from app.services.company_researcher import research_host_company
from app.services.contact_discovery import discover_host_contacts
from app.services.host_identifier import identify_podcast_host
from app.services.identity_verifier import verify_host_and_contact
from app.services.original_podcast_finder import find_original_podcast
from app.services.research_query import compute_dashboard_statistics
from app.services.page_extractor import (
    build_linkedin_video_search_url,
    build_youtube_search_url,
    parse_linkedin_posts_from_html,
    parse_youtube_search_results_from_html,
)
from app.services.persistence import (
    add_evidence,
    upsert_company,
    upsert_contact,
    upsert_host_person,
    upsert_linkedin_post,
    upsert_person_company_role,
    upsert_podcast,
    upsert_quality_assessment,
)
from app.services.video_quality import assess_podcast_video

logger = logging.getLogger(__name__)


class LiveEventBus:
    """In-memory pub/sub for SSE live dashboard updates."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    async def publish(self, event: dict[str, Any]) -> None:
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                if q.full():
                    _ = q.get_nowait()
                q.put_nowait(event)
            except Exception:  # noqa: BLE001
                stale.append(q)
        for q in stale:
            self._subscribers.discard(q)


def generate_search_keyword_variations(primary_keyword: str) -> list[str]:
    """Generate dynamic contextual search queries based on the user's chosen topic or niche."""
    kw = (primary_keyword or "Real Estate Podcast").strip()
    results = [kw]

    # Split composite keywords ('X and Y')
    parts = [p.strip() for p in kw.split(" and ") if p.strip()]
    for p in parts:
        if p not in results:
            results.append(p)

    is_real_estate = any(w in kw.lower() for w in ("real estate", "property", "multifamily", "commercial real estate", "cre"))
    if is_real_estate:
        re_defaults = [
            "Commercial Real Estate Podcast",
            "Multifamily Real Estate Podcast",
            "Real Estate Investing Show",
            "Real Estate Host Interview",
            "Property Investment Podcast",
            "Real Estate Syndication Show",
            "Real Estate Development Podcast",
        ]
        for r in re_defaults:
            if r not in results:
                results.append(r)
    else:
        # Build contextual variations based on the user's specific topics/roles
        for p in parts:
            clean = p.replace(" Podcasts", "").replace(" podcasts", "").replace(" Podcast", "").replace(" podcast", "").replace(" Shows", "").replace(" Show", "").replace(" show", "").strip()
            if not clean:
                continue
            variations = [
                f"{clean} Podcast",
                f"{clean} Show",
                f"{clean} Founder Interview",
                f"{clean} Host Interview",
                f"Top {clean} Podcast",
                f"B2B {clean} Podcast",
            ]
            for v in variations:
                if v not in results:
                    results.append(v)

    return results[:8]


class ResearchWorkflowManager:
    """Orchestrates Jarvis-like autonomous browser research with pause/resume/stop & checkpoints."""

    def __init__(self, browser: BrowserController | None = None) -> None:
        self.browser = browser or browser_controller
        self.events = LiveEventBus()
        self._active_task_id: int | None = None
        self._bg_task: asyncio.Task[None] | None = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._stop_requested = False
        self._agent_state: str = "idle"

    @property
    def agent_state(self) -> str:
        return self._agent_state

    @property
    def active_task_id(self) -> int | None:
        return self._active_task_id

    async def _log(
        self,
        task_id: int | None,
        stage: str,
        action: str,
        message: str,
        url: str | None = None,
        level: str = "INFO",
        screenshot_path: str | None = None,
        progress: int | None = None,
    ) -> None:
        db: Session = SessionLocal()
        try:
            entry = AgentActivityLog(
                agency_id="default",
                research_task_id=task_id,
                level=level,
                stage=stage,
                action=action,
                url=url,
                message=message,
                screenshot_path=screenshot_path,
            )
            db.add(entry)
            if task_id is not None:
                task = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
                if task:
                    entry.agency_id = task.agency_id
                    task.current_stage = stage
                    if url is not None:
                        task.current_url = url
                    if progress is not None:
                        task.progress = max(0, min(100, progress))
            db.commit()
        finally:
            db.close()

        await self.events.publish(
            {
                "type": "activity",
                "task_id": task_id,
                "agent_state": self._agent_state,
                "level": level,
                "stage": stage,
                "action": action,
                "url": url,
                "message": message,
                "screenshot_path": screenshot_path,
                "progress": progress,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _checkpoint(self, task_id: int, checkpoint_data: dict[str, Any]) -> None:
        db: Session = SessionLocal()
        try:
            task = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
            if task:
                task.checkpoint_data = checkpoint_data
                db.commit()
        finally:
            db.close()

    async def _wait_if_paused(self, task_id: int) -> bool:
        """Returns False if stop was requested while paused."""
        if self._stop_requested:
            return False
        if not self._resume_event.is_set():
            self._agent_state = "paused"
            db = SessionLocal()
            try:
                t = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
                if t:
                    t.task_status = "paused"
                    db.commit()
            finally:
                db.close()

            await self._log(
                task_id,
                "paused",
                "wait",
                "Research paused: waiting for authentication. Please log in to LinkedIn in the opened Chrome window. (Agent will auto-resume once login is detected, or click Resume).",
            )

            # Wait loop: checks for user Resume click, Stop click, or auto-detects login completion
            while not self._resume_event.is_set() and not self._stop_requested:
                try:
                    await asyncio.wait_for(self._resume_event.wait(), timeout=3.0)
                    break
                except asyncio.TimeoutError:
                    try:
                        auth = await self.browser.check_platform_auth("linkedin")
                        if auth.get("status") == "Logged In":
                            await self._log(
                                task_id,
                                "access_gate",
                                "authenticated",
                                "LinkedIn login detected! Resuming research automatically...",
                            )
                            self._resume_event.set()
                            break
                    except Exception:  # noqa: BLE001
                        pass

            if not self._stop_requested:
                self._agent_state = "running"
                db = SessionLocal()
                try:
                    t = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
                    if t:
                        t.task_status = "running"
                        db.commit()
                finally:
                    db.close()
                await self._log(task_id, "resumed", "resume", "Resuming research from saved checkpoint.")
        return not self._stop_requested

    async def start_task(
        self,
        instruction: str,
        search_keyword: str | None = None,
        max_posts: int | None = None,
        quality_threshold: int | None = None,
        use_browser: bool = True,
        agency_id: str = "default",
    ) -> ResearchTask:
        settings = get_settings()
        keyword = (search_keyword or settings.default_search_keyword).strip() or "Real Estate Podcast"
        limit = max_posts or settings.max_posts_per_run
        threshold = quality_threshold if quality_threshold is not None else settings.quality_threshold

        db: Session = SessionLocal()
        try:
            task = ResearchTask(
                agency_id=agency_id,
                user_instruction=instruction,
                search_keyword=keyword,
                task_status="pending",
                current_stage="queued",
                progress=0,
                max_posts=limit,
                quality_threshold=threshold,
                checkpoint_data={"stage": "init", "processed_urls": []},
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
        finally:
            db.close()

        self._stop_requested = False
        self._resume_event.set()
        self._active_task_id = task_id
        self._agent_state = "running"

        self._bg_task = asyncio.create_task(self._execute_task(task_id, use_browser=use_browser))
        return task

    async def pause_task(self) -> bool:
        if self._active_task_id is None or self._agent_state not in ("running",):
            return False
        self._resume_event.clear()
        self._agent_state = "paused"
        db = SessionLocal()
        try:
            t = db.query(ResearchTask).filter(ResearchTask.id == self._active_task_id).first()
            if t:
                t.task_status = "paused"
                db.commit()
        finally:
            db.close()
        await self._log(self._active_task_id, "paused", "pause", "Task paused.")
        return True

    async def resume_task(self) -> bool:
        if self._active_task_id is None:
            return False
        db = SessionLocal()
        try:
            t = db.query(ResearchTask).filter(ResearchTask.id == self._active_task_id).first()
            if t:
                t.task_status = "running"
                db.commit()
        finally:
            db.close()
        self._agent_state = "running"
        self._resume_event.set()
        return True

    async def stop_task(self) -> bool:
        if self._active_task_id is None:
            return False
        self._stop_requested = True
        self._agent_state = "stopping"
        self._resume_event.set()
        db = SessionLocal()
        try:
            t = db.query(ResearchTask).filter(ResearchTask.id == self._active_task_id).first()
            if t:
                t.task_status = "stopped"
                t.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
        await self._log(self._active_task_id, "stopped", "stop", "Stop requested by user.")
        return True

    async def process_single_post(
        self,
        db: Session,
        task_id: int,
        post_data: dict[str, Any],
        quality_threshold: int = 65,
        frame_paths: list[str] | None = None,
        video_meta: dict[str, Any] | None = None,
        audio_accessible: bool = False,
        allow_live_browser: bool = True,
        agency_id: str = "default",
        browser: Any = None,
    ) -> dict[str, Any]:
        """Execute Modules 3 -> 8 for a single discovered podcast post."""
        if self._stop_requested:
            return {"status": "Stopped", "is_new": False}
        active_b = browser or self.browser
        post, is_new = upsert_linkedin_post(db, task_id, post_data, agency_id=agency_id)
        add_evidence(
            db,
            task_id,
            "linkedin_post",
            post.id,
            post.post_url,
            "LinkedIn Post",
            f"Caption: {post.post_caption[:400]} | Account: {post.posting_account}",
            agency_id=agency_id,
        )

        # Module 3 — Video Quality Assessment
        frames = frame_paths or []
        v_meta = video_meta or {"found": bool(post.video_url)}
        if allow_live_browser and not frames and post.post_url and getattr(active_b, "is_active", False):
            try:
                nav = await active_b.open_url(post.post_url, screenshot_label=f"post_{post.id}")
                if nav.success and (not nav.gate or not nav.gate.restricted):
                    cap = await active_b.capture_video_frames(max_frames=2)
                    frames = cap.get("frame_paths", [])
                    v_meta = cap.get("video_meta", {})
                    audio_accessible = cap.get("audio_accessible", False)
            except Exception as b_err:
                logger.debug("Frame capture skipped or failed: %s", b_err)

        qa_res = await assess_podcast_video(
            caption=post.post_caption,
            frame_paths=frames,
            video_meta=v_meta,
            audio_accessible=audio_accessible,
            quality_threshold=quality_threshold,
        )
        qa = upsert_quality_assessment(
            db=db,
            linkedin_post_id=post.id,
            video_score=qa_res.video_score,
            video_quality=qa_res.video_quality,
            audio_quality=qa_res.audio_quality,
            lighting=qa_res.lighting,
            setup_quality=qa_res.setup_quality,
            content_relevance=qa_res.content_relevance,
            qualification_status=qa_res.qualification_status,
            assessment_notes=qa_res.assessment_notes,
            frame_paths=qa_res.frame_paths,
            audio_inspected=qa_res.audio_inspected,
            agency_id=agency_id,
        )
        db.commit()

        # If video is rejected, do not proceed with entity and contact discovery
        if qa.qualification_status == "Rejected":
            return {"post_id": post.id, "status": "Rejected", "is_new": is_new}

        # Extract podcast & host AI reasoning if OpenAI configured
        comments_text = "\n".join(post_data.get("comments") or [])
        ai_entities = await ai_planner.extract_podcast_and_host_entities(
            post.post_caption, post.posting_account, comments_text
        )

        # Module 4 — Original Podcast Discovery
        orig_res = await find_original_podcast(
            post_data=post_data,
            ai_entities=ai_entities,
            browser=active_b if allow_live_browser else None,
            allow_live_search=allow_live_browser,
        )

        # Module 5 — Host Identification (strictly Host only)
        host_res = await identify_podcast_host(
            post_data=post_data,
            podcast_name=orig_res.podcast_name,
            ai_entities=ai_entities,
            browser=active_b if allow_live_browser else None,
        )

        # Module 6 — Host Company Research (no guest/marketing employee prospecting)
        comp_res = await research_host_company(
            host_name=host_res.host_name,
            host_linkedin_url=host_res.host_linkedin_url,
            initial_company_name=host_res.associated_company,
            post_external_urls=post_data.get("external_urls"),
            browser=active_b if allow_live_browser else None,
            allow_live_browser=allow_live_browser,
        )

        # Module 7 — Host Contact Discovery (LinkedIn -> YouTube About -> Website -> Apollo)
        contacts_found = await discover_host_contacts(
            post_data=post_data,
            host_name=host_res.host_name,
            host_linkedin_url=comp_res.host_linkedin_url or host_res.host_linkedin_url,
            company_name=comp_res.company_name,
            official_website=comp_res.official_website,
            youtube_channel_url=orig_res.youtube_channel_url,
            browser=active_b if allow_live_browser else None,
            allow_live_browser=allow_live_browser,
        )

        # Module 8 — Cross-source Identity Verification
        primary_contact = contacts_found[0] if contacts_found else None
        ver = verify_host_and_contact(
            host_name=host_res.host_name,
            host_linkedin_url=comp_res.host_linkedin_url or host_res.host_linkedin_url,
            company_name=comp_res.company_name,
            official_website=comp_res.official_website or (primary_contact.official_website if primary_contact else None),
            youtube_channel_url=orig_res.youtube_channel_url,
            email=primary_contact.email if primary_contact else None,
            email_category=primary_contact.email_category if primary_contact else "unknown",
            contact_source_type=primary_contact.source_type if primary_contact else None,
            host_confidence=host_res.confidence_score,
        )

        # Persist normalized entities cleanly (strictly valid individual persons, not channel brands)
        host_person = None
        from app.services.host_identifier import is_valid_person_name
        if host_res.host_name and is_valid_person_name(host_res.host_name, orig_res.podcast_name):
            host_person = upsert_host_person(
                db=db,
                full_name=host_res.host_name,
                linkedin_url=comp_res.host_linkedin_url or host_res.host_linkedin_url,
                designation=comp_res.host_designation or host_res.host_role,
                location=comp_res.company_location,
                identity_status=ver.identity_status,
                confidence_score=ver.confidence_score,
                manual_review_required=ver.manual_review_required or host_res.manual_review_required,
                notes=f"{host_res.notes} | {ver.notes}",
                agency_id=agency_id,
            )
            for ev_url in host_res.evidence_urls:
                add_evidence(
                    db, task_id, "person", host_person.id, ev_url, "Host Discovery", host_res.notes, agency_id=agency_id
                )

        company_obj = None
        if comp_res.company_name:
            company_obj = upsert_company(
                db=db,
                company_name=comp_res.company_name,
                linkedin_url=comp_res.company_linkedin_url,
                website=comp_res.official_website,
                location=comp_res.company_location,
                agency_id=agency_id,
            )
            for ev_url in comp_res.evidence_urls:
                add_evidence(
                    db, task_id, "company", company_obj.id, ev_url, "Company Research", comp_res.notes, agency_id=agency_id
                )

        if host_person and company_obj:
            upsert_person_company_role(
                db=db,
                person_id=host_person.id,
                company_id=company_obj.id,
                designation=comp_res.host_designation or host_res.host_role,
                relationship_status=comp_res.relationship_status,
                evidence_url=comp_res.company_linkedin_url or comp_res.host_linkedin_url,
                agency_id=agency_id,
            )

        podcast = upsert_podcast(
            db=db,
            linkedin_post_id=post.id,
            host_id=host_person.id if host_person else None,
            podcast_name=orig_res.podcast_name,
            episode_title=orig_res.episode_title,
            original_podcast_url=orig_res.original_podcast_url,
            youtube_channel_name=orig_res.youtube_channel_name,
            youtube_channel_url=orig_res.youtube_channel_url,
            discovery_method=orig_res.discovery_method,
            confidence_score=orig_res.confidence_score,
            manual_review_required=orig_res.manual_review_required or ver.manual_review_required,
            research_notes=orig_res.research_notes,
            agency_id=agency_id,
        )
        for ev_url in orig_res.evidence_urls:
            add_evidence(
                db, task_id, "podcast", podcast.id, ev_url, "Podcast Discovery", orig_res.research_notes, agency_id=agency_id
            )

        for c in contacts_found:
            contact_status = ver.contact_status if c.email else "Unverified"
            c_obj = upsert_contact(
                db=db,
                person_id=host_person.id if host_person else None,
                podcast_id=podcast.id,
                email=c.email,
                email_category=c.email_category,
                phone=c.phone,
                official_website=c.official_website or comp_res.official_website,
                contact_page=c.contact_page,
                verification_status=contact_status,
                confidence_score=max(c.confidence_score, ver.confidence_score if c.email else 0),
                research_notes=c.notes,
                source_type=c.source_type,
                source_url=c.source_url,
                discovery_method=c.discovery_method,
                agency_id=agency_id,
            )
            if c.source_url:
                add_evidence(db, task_id, "contact", c_obj.id, c.source_url, c.source_type, c.notes, agency_id=agency_id)

        db.commit()
        return {
            "post_id": post.id,
            "podcast_id": podcast.id,
            "status": qa.qualification_status,
            "host_name": host_person.full_name if host_person else None,
            "email": primary_contact.email if primary_contact else None,
        }

    async def _execute_task(self, task_id: int, use_browser: bool = True) -> None:
        db = SessionLocal()
        try:
            task = db.query(ResearchTask).filter(ResearchTask.id == task_id).first()
            if not task:
                return
            keyword = task.search_keyword
            max_posts = task.max_posts
            threshold = task.quality_threshold
            agency_id = task.agency_id
            task.task_status = "running"
            task.started_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

        try:
            await self._log(task_id, "browser_init", "start", f"Starting browser research for '{keyword}'.", progress=5)

            if use_browser:
                agency_session = browser_manager.get_session(agency_id)
                active_browser = agency_session if agency_session.is_local_connected else self.browser
                browser_started = False
                info: dict[str, Any] = {}
                try:
                    info = await active_browser.start()
                    browser_started = bool(info.get("started", True) and getattr(active_browser, "is_active", False))
                except Exception as b_exc:
                    logger.warning("Browser startup notice: %s", b_exc)
                    browser_started = False

                if browser_started:
                    await self._log(
                        task_id,
                        "browser_ready",
                        "launch",
                        f"Browser active ({info.get('channel')}). Navigating to LinkedIn search.",
                        url=info.get("url"),
                        progress=10,
                    )
                else:
                    await self._log(
                        task_id,
                        "browser_notice",
                        "fallback",
                        "Desktop Chrome bridge agent offline. Operating in Cloud Discovery Mode (Tavily + YouTube public data). Run start_agent.bat on your PC to automate your desktop Chrome.",
                        url=None,
                        progress=10,
                    )

                # Continuous Autonomous Research Loop
                # Continues searching across user-specified podcast topic keywords across YouTube & LinkedIn until user stops
                SEARCH_KEYWORDS = generate_search_keyword_variations(keyword)
                seen_urls: set[str] = set()
                total_processed = 0
                cycle = 0

                while not self._stop_requested:
                    current_kw = SEARCH_KEYWORDS[cycle % len(SEARCH_KEYWORDS)]
                    cycle += 1
                    batch_candidates: list[dict[str, Any]] = []

                    # 1. YouTube Discovery (Dedicated YouTube Tab in existing Chrome window if active)
                    yt_query = current_kw if "podcast" in current_kw.lower() else f"{current_kw} podcast"
                    yt_search_url = build_youtube_search_url(yt_query)
                    await self._log(
                        task_id,
                        "youtube_search",
                        "navigate",
                        f"Searching YouTube for '{yt_query}' (cycle {cycle})...",
                        url=yt_search_url,
                        progress=min(95, 20 + (cycle % 12) * 5),
                    )
                    if browser_started and getattr(active_browser, "is_active", False):
                        try:
                            yt_nav = await active_browser.open_url(yt_search_url, screenshot_label=f"yt_search_{cycle}")
                            if yt_nav.success:
                                await active_browser.scroll("down", 1000)
                                await asyncio.sleep(1)
                                yt_html = await active_browser.get_html()
                                yt_results = parse_youtube_search_results_from_html(yt_html)
                                for y in yt_results:
                                    candidate_url = y.get("video_url") or y.get("channel_url")
                                    if candidate_url and candidate_url not in seen_urls:
                                        seen_urls.add(candidate_url)
                                        ch_name = y.get("channel_name") or y.get("title") or current_kw
                                        batch_candidates.append({
                                            "post_url": candidate_url,
                                            "post_caption": f"{y.get('title', '')} - {current_kw} by {ch_name}",
                                            "posting_account": ch_name,
                                            "posting_account_url": y.get("channel_url"),
                                            "video_url": y.get("video_url") if (y.get("video_url") and "/watch?v=" in str(y.get("video_url"))) else None,
                                            "has_video_element": True,
                                            "published_label": "YouTube",
                                            "keywords_matched": [current_kw, "podcast"],
                                            "external_urls": [u for u in [candidate_url, y.get("channel_url")] if u],
                                            "comments": [],
                                            "youtube_channel_url": y.get("channel_url"),
                                            "podcast_name": ch_name,
                                            "episode_title": y.get("title"),
                                        })
                        except Exception as yt_err:
                            logger.warning("YouTube search step encountered error: %s", yt_err)

                    # 2. LinkedIn Discovery (Dedicated LinkedIn Tab in existing Chrome window if active)
                    if browser_started and getattr(active_browser, "is_active", False):
                        li_search_url = build_linkedin_video_search_url(current_kw)
                        await self._log(
                            task_id,
                            "linkedin_search",
                            "navigate",
                            f"Searching LinkedIn Posts (video) for '{current_kw}' (cycle {cycle})...",
                            url=li_search_url,
                            progress=min(95, 22 + (cycle % 12) * 5),
                        )
                        try:
                            li_nav = await active_browser.open_url(li_search_url, screenshot_label=f"li_search_{cycle}")
                            if li_nav.gate and li_nav.gate.restricted:
                                await self._log(
                                    task_id,
                                    "access_gate",
                                    li_nav.gate.gate_type or "login_wall",
                                    f"LinkedIn login page open in Chrome. Sign in when convenient to enable full LinkedIn feed scraping. YouTube & public podcast network research continues seamlessly.",
                                    url=li_nav.url,
                                    level="WARNING",
                                    screenshot_path=li_nav.screenshot_path,
                                )
                            elif li_nav.success:
                                for scroll_idx in range(2):
                                    if self._stop_requested or not await self._wait_if_paused(task_id):
                                        break
                                    html = await active_browser.get_html()
                                    parsed = parse_linkedin_posts_from_html(html, keyword=current_kw)
                                    for item in parsed:
                                        if item["post_url"] not in seen_urls:
                                            seen_urls.add(item["post_url"])
                                            batch_candidates.append(item)
                                    await active_browser.scroll("down", 800)
                        except Exception as li_err:
                            logger.warning("LinkedIn search step encountered error: %s", li_err)

                    # 3. Augmented discovery via Tavily if candidates are low
                    if len(batch_candidates) < 3 and not self._stop_requested:
                        try:
                            from app.services.tavily_search import search_tavily
                            t_res = await search_tavily(f'"{current_kw}" podcast youtube channel host', max_results=6)
                            for r in t_res:
                                u = r.get("url", "")
                                if u and u not in seen_urls and not any(d in u.lower() for d in ("instagram.com", "facebook.com", "tiktok.com")):
                                    seen_urls.add(u)
                                    title = (r.get("title") or current_kw).split("|")[0].strip()[:80]
                                    ch_url = u if ("youtube.com/@" in u or "youtube.com/channel/" in u or "youtube.com/c/" in u) else None
                                    batch_candidates.append({
                                        "post_url": u,
                                        "post_caption": r.get("content") or f"{title} - {current_kw}",
                                        "posting_account": title,
                                        "posting_account_url": ch_url,
                                        "video_url": u if "youtube.com/watch" in u else None,
                                        "has_video_element": True,
                                        "published_label": "Web/Tavily",
                                        "keywords_matched": [current_kw, "podcast"],
                                        "external_urls": [u],
                                        "comments": [],
                                        "youtube_channel_url": ch_url,
                                        "podcast_name": title,
                                    })
                        except Exception as exc:
                            logger.debug("Tavily fallback: %s", exc)

                    if batch_candidates:
                        await self._log(
                            task_id,
                            "multi_channel_discovery",
                            "found",
                            f"Discovered {len(batch_candidates)} candidate podcast channels & episodes for '{current_kw}'. Processing research on each channel...",
                            progress=min(95, 25 + (total_processed % 35) * 2),
                        )

                    # 4. Process each discovered podcast/channel with resilient skip-on-error logic
                    # Never gets stuck on one channel; if fetching fails, logs and proceeds to next channel!
                    for candidate in batch_candidates:
                        if self._stop_requested or not await self._wait_if_paused(task_id):
                            break

                        total_processed += 1
                        channel_name = candidate.get("posting_account") or candidate.get("podcast_name") or f"Channel #{total_processed}"
                        target_url = candidate.get("post_url") or candidate.get("youtube_channel_url")

                        await self._log(
                            task_id,
                            "channel_research",
                            "start",
                            f"Researching channel/lead #{total_processed}: '{channel_name}'...",
                            url=target_url,
                            progress=min(95, 25 + (total_processed % 35) * 2),
                        )

                        db_item = SessionLocal()
                        try:
                            res = await self.process_single_post(
                                db=db_item,
                                task_id=task_id,
                                post_data=candidate,
                                quality_threshold=threshold,
                                allow_live_browser=True,
                                agency_id=agency_id,
                                browser=active_browser,
                            )
                            lead_name = res.get("host_name") or channel_name
                            lead_email = res.get("email") or "Searching..."
                            status_val = res.get("status") or "Processed"
                            await self._log(
                                task_id,
                                "next_channel",
                                "continue",
                                f"Saved podcast '{lead_name}' (Status: {status_val}, Email: {lead_email}) to PostgreSQL. Advancing to next channel...",
                                url=target_url,
                                progress=min(95, 28 + (total_processed % 35) * 2),
                            )
                        except Exception as exc:
                            logger.warning("Error processing channel '%s': %s", channel_name, exc)
                            await self._log(
                                task_id,
                                "next_channel",
                                "skip",
                                f"Notice: Could not fetch details for channel '{channel_name}': {exc}. Gracefully moving to next channel...",
                                url=target_url,
                                level="WARNING",
                            )
                        finally:
                            db_item.close()

                    # Clean up any extra background tabs opened during research to free RAM and CPU
                    if browser_started and getattr(active_browser, "is_active", False):
                        try:
                            await active_browser.cleanup_stray_tabs()
                        except Exception:
                            pass

                    # Pause briefly before next cycle
                    if self._stop_requested:
                        break
                    await asyncio.sleep(2)

            # Final state update when stopped or completed
            db_done = SessionLocal()
            try:
                t = db_done.query(ResearchTask).filter(ResearchTask.id == task_id).first()
                if t:
                    if self._stop_requested:
                        t.task_status = "stopped"
                        t.current_stage = "stopped"
                        t.progress = min(t.progress or 0, 95)
                        t.completed_at = datetime.now(timezone.utc)
                    else:
                        t.task_status = "completed"
                        t.current_stage = "completed"
                        t.progress = 100
                        t.completed_at = datetime.now(timezone.utc)
                    final_stats = compute_dashboard_statistics(db_done, agency_id=agency_id)
                    action_word = "stopped" if self._stop_requested else "completed"
                    summary_msg = (
                        f"Research session {action_word}. Total collected in PostgreSQL: "
                        f"{final_stats['qualified_podcasts']} qualified podcast(s), "
                        f"{final_stats['hosts_identified']} host(s), and "
                        f"{final_stats['emails_discovered']} email contact(s)."
                    )
                    db_done.add(
                        AgentMessage(
                            agency_id=agency_id,
                            research_task_id=task_id,
                            role="assistant",
                            content=summary_msg,
                            metadata_json={"stats": final_stats},
                        )
                    )
                    db_done.commit()
            finally:
                db_done.close()

            self._agent_state = "idle"
            if self._stop_requested:
                await self._log(task_id, "stopped", "stop", "Research session stopped by user.")
            else:
                await self._log(task_id, "completed", "done", "Research workflow finished. All data saved to PostgreSQL.", progress=100)

            # Best-effort n8n webhook trigger if configured
            settings = get_settings()
            if settings.n8n_webhook_url:
                try:
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        await client.post(
                            settings.n8n_webhook_url,
                            json={"event": "research_completed", "task_id": task_id, "keyword": keyword},
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Optional n8n webhook notification failed: %s", exc)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Research task %s failed", task_id)
            self._agent_state = "error"
            db_err = SessionLocal()
            try:
                t = db_err.query(ResearchTask).filter(ResearchTask.id == task_id).first()
                if t:
                    t.task_status = "failed"
                    t.error_message = str(exc)
                    t.completed_at = datetime.now(timezone.utc)
                    db_err.commit()
            finally:
                db_err.close()
            await self._log(task_id, "error", "exception", f"Task failed: {exc}", level="ERROR")


workflow_manager = ResearchWorkflowManager()

