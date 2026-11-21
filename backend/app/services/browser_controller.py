from __future__ import annotations

import asyncio
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger(__name__)

CDP_URL = "http://127.0.0.1:9222"

MUTE_AUDIO_SCRIPT = """
(() => {
  if (window.__yoursbuddyMuted) {
    try {
      document.querySelectorAll('video, audio').forEach(el => { el.muted = true; el.volume = 0; });
    } catch (e) {}
    return;
  }
  window.__yoursbuddyMuted = true;
  const forceMute = (el) => {
    try {
      if (el) {
        el.muted = true;
        el.volume = 0;
        if (el.setAttribute) el.setAttribute('muted', 'muted');
      }
    } catch (e) {}
  };
  const muteAll = () => {
    try {
      document.querySelectorAll('video, audio').forEach(forceMute);
    } catch (e) {}
  };
  muteAll();
  try {
    const origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function(...args) {
      forceMute(this);
      return origPlay.apply(this, args);
    };
  } catch (e) {}
  try {
    document.addEventListener('volumechange', (e) => {
      if (e.target && (e.target.tagName === 'VIDEO' || e.target.tagName === 'AUDIO')) {
        if (!e.target.muted || e.target.volume > 0) {
          forceMute(e.target);
        }
      }
    }, true);
    document.addEventListener('playing', (e) => {
      if (e.target && (e.target.tagName === 'VIDEO' || e.target.tagName === 'AUDIO')) {
        forceMute(e.target);
      }
    }, true);
  } catch (e) {}
  try {
    const obs = new MutationObserver(muteAll);
    const startObs = () => {
      if (document.documentElement) {
        obs.observe(document.documentElement, { childList: true, subtree: true });
      }
    };
    if (document.documentElement) startObs();
    else document.addEventListener('DOMContentLoaded', startObs);
  } catch (e) {}
})();
"""


@dataclass
class AccessGateStatus:
    restricted: bool
    gate_type: str | None = None  # login | captcha | rate_limit | blocked
    reason: str | None = None
    url: str | None = None


@dataclass
class BrowserActionResult:
    success: bool
    url: str | None = None
    title: str | None = None
    screenshot_path: str | None = None
    error: str | None = None
    gate: AccessGateStatus | None = None


class BrowserController:
    """Single shared Playwright browser controller for YoursBuddy AI.

    Connects strictly to the user's EXISTING Google Chrome browser via CDP on port 9222.
    - Uses one shared Playwright CDP connection.
    - Reuses the existing Chrome window and its tabs.
    - Opens LinkedIn in a new tab in that existing Chrome window.
    - Opens YouTube in another new tab in that same Chrome window.
    - Never silently launches duplicate browsers or creates separate profiles.
    - If Chrome is not running on port 9222, reports a clear instruction to the user.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yb-cdp-browser")
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._active: bool = False
        self._last_url: str | None = None
        self._last_screenshot: str | None = None
        self._last_shot_time: float = 0.0
        self._cached_auth_state: dict[str, bool] = {"linkedin": False, "youtube": False}
        self._cached_auth_time: float = 0.0

    @property
    def is_active(self) -> bool:
        return bool(self._active)

    @property
    def current_url(self) -> str | None:
        return self._last_url

    @property
    def last_screenshot_path(self) -> str | None:
        return self._last_screenshot

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args, **kwargs))

    def _is_cdp_available(self) -> bool:
        """Check if user's Chrome is running and listening on port 9222."""
        try:
            with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _start_sync(self, headless: bool | None = None) -> dict[str, Any]:
        """Connect to the user's existing Chrome window via CDP.

        Does NOT silently spawn another browser if Chrome is not open on port 9222.
        """
        from playwright.sync_api import sync_playwright

        # If already connected and context has live pages, reuse the existing connection
        if self._active and self._context is not None:
            try:
                pages = [p for p in self._context.pages if not p.is_closed()]
                if pages:
                    self._page = pages[0]
                    self._last_url = self._page.url
                    return {"started": True, "url": self._page.url, "channel": "existing_chrome_cdp"}
            except Exception:
                self._stop_sync()

        # Check if Chrome is listening on port 9222
        if not self._is_cdp_available():
            settings = get_settings()
            if settings.browser_headless or settings.environment != "development":
                logger.info("CDP not detected on port 9222; attempting ultra-lean headless Chromium for cloud environment.")
                try:
                    if self._pw is None:
                        self._pw = sync_playwright().start()
                    self._browser = self._pw.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--no-zygote",
                            "--single-process",
                            "--disable-extensions",
                            "--disable-background-networking",
                            "--disable-renderer-backgrounding",
                            "--mute-audio",
                            "--disable-software-rasterizer",
                            "--js-flags=--max-old-space-size=128",
                        ],
                    )
                    self._context = self._browser.new_context()
                    try:
                        self._context.add_init_script(MUTE_AUDIO_SCRIPT)
                    except Exception:
                        pass
                    self._page = self._context.new_page()
                    self._active = True
                    self._last_url = self._page.url
                    return {"started": True, "url": self._page.url, "channel": "headless_cloud_chromium"}
                except Exception as exc:
                    logger.warning("Cloud headless Chromium could not start: %s. Using Cloud Discovery Fallback.", exc)
                    self._active = False
                    return {"started": False, "url": "about:blank", "channel": "cloud_discovery_fallback", "error": str(exc)}

            self._active = False
            raise RuntimeError(
                "Google Chrome is not running with remote debugging enabled on port 9222. "
                "Please run 'start_agent.bat' on your computer to connect your desktop Chrome, then click Start Research."
            )

        if self._pw is None:
            self._pw = sync_playwright().start()

        try:
            self._browser = self._pw.chromium.connect_over_cdp(CDP_URL)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            try:
                self._context.add_init_script(MUTE_AUDIO_SCRIPT)
            except Exception:
                pass
            pages = [p for p in self._context.pages if not p.is_closed() and not (p.url or "").startswith("chrome://")]
            self._page = pages[0] if pages else (self._context.pages[0] if self._context.pages else self._context.new_page())
            self._mute_page_sync(self._page)
            self._active = True
            self._last_url = self._page.url
            logger.info("Connected over CDP to existing Chrome (open tabs: %d)", len(self._context.pages))
            return {"started": True, "url": self._page.url, "channel": "existing_chrome_cdp"}
        except Exception as exc:
            self._active = False
            logger.error("Failed connecting to Chrome via CDP: %s", exc)
            raise RuntimeError(f"Could not connect to existing Chrome over CDP ({exc}).") from exc

    def _mute_page_sync(self, page: Any) -> None:
        """Silently mute all audio/video playback on the automated page."""
        if page is None:
            return
        try:
            if not page.is_closed() and not (page.url or "").startswith("chrome://"):
                page.evaluate(MUTE_AUDIO_SCRIPT)
        except Exception:
            pass

    def _stop_sync(self) -> None:
        """Disconnect CDP client without closing the user's Chrome window."""
        self._active = False
        self._page = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def _cleanup_stray_tabs_sync(self) -> int:
        """Close extra tabs in Chrome, keeping only the dedicated LinkedIn and YouTube tabs to free RAM and CPU."""
        closed_count = 0
        if not self._context:
            return 0
        try:
            pages = [p for p in self._context.pages if not p.is_closed()]
            if len(pages) > 2:
                for p in pages:
                    u = (p.url or "").lower()
                    # Keep dedicated core tabs (LinkedIn and YouTube) and blank tabs
                    is_core = ("linkedin.com" in u) or ("youtube.com" in u) or (u.startswith("chrome://")) or (u == "about:blank")
                    if not is_core:
                        try:
                            p.close()
                            closed_count += 1
                        except Exception:
                            pass
        except Exception as exc:
            logger.debug("Tab cleanup error: %s", exc)
        return closed_count

    async def cleanup_stray_tabs(self) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._cleanup_stray_tabs_sync)

    def _get_or_open_tab_sync(self, domain_keyword: str) -> Any:
        """Get existing tab matching domain_keyword or open a new tab in the existing Chrome window."""
        for attempt in range(2):
            try:
                self._ensure_connection_sync()
                if not self._context:
                    return self._page

                pages = [p for p in self._context.pages if not p.is_closed()]
                for p in pages:
                    url = (p.url or "").lower()
                    if domain_keyword.lower() in url:
                        try:
                            p.bring_to_front()
                            self._page = p
                            self._last_url = p.url
                            return p
                        except Exception:
                            pass

                # Open a new tab in the same existing Chrome window
                new_page = self._context.new_page()
                try:
                    new_page.bring_to_front()
                except Exception:
                    pass
                self._page = new_page
                self._last_url = new_page.url
                return new_page
            except Exception as exc:
                logger.warning("Tab creation error for %s (attempt %d): %s", domain_keyword, attempt + 1, exc)
                self._stop_sync()
                time.sleep(0.5)
                try:
                    self._start_sync()
                except Exception:
                    pass

        return self._ensure_connection_sync()

    def _ensure_connection_sync(self) -> Any:
        for attempt in range(2):
            try:
                if not self._active or self._context is None:
                    self._start_sync()
                if self._context is not None:
                    pages = [p for p in self._context.pages if not p.is_closed()]
                    if not pages:
                        self._page = self._context.new_page()
                    elif self._page is None or self._page.is_closed():
                        self._page = pages[0]
                if self._page is not None:
                    _ = self._page.url
                    return self._page
            except Exception as exc:
                logger.warning("CDP ensure_connection attempt %d failed: %s", attempt + 1, exc)
                self._stop_sync()
                time.sleep(0.5)
                try:
                    self._start_sync()
                except Exception:
                    pass
        return self._page

    def _detect_access_gate_sync(self, page: Any) -> AccessGateStatus:
        url = (page.url or "").lower()
        try:
            body_text = (page.inner_text("body") or "")[:2000].lower()
        except Exception:
            body_text = ""

        # CAPTCHA / anti-bot
        captcha_signals = [
            "verify you are human",
            "security verification",
            "arkose",
            "recaptcha",
            "hcaptcha",
            "cf-turnstile",
            "unusual traffic from your computer",
            "complete a quick security check",
        ]
        if any(s in body_text or s in url for s in captcha_signals):
            return AccessGateStatus(
                restricted=True,
                gate_type="captcha",
                reason="Verification challenge detected. Please complete it in your Chrome window.",
                url=page.url,
            )

        # Login wall
        login_signals = [
            "uas/login",
            "/login",
            "servicelogin",
            "signin",
            "sign in to linkedin",
            "join linkedin",
            "authwall",
            "instagram.com",
            "facebook.com",
            "tiktok.com",
        ]
        if any(s in url for s in login_signals):
            return AccessGateStatus(
                restricted=True,
                gate_type="login",
                reason="Login required. Please log in directly in that tab in Chrome.",
                url=page.url,
            )

        return AccessGateStatus(restricted=False, url=page.url)

    def _capture_screenshot_sync(self, label: str = "snap") -> str | None:
        if not self._active or self._page is None:
            return self._last_screenshot
        try:
            if self._page.is_closed():
                return self._last_screenshot
            settings = get_settings()
            settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            out = settings.screenshots_dir / f"{ts}_{label}.png"
            self._page.screenshot(path=str(out), full_page=False)
            self._last_screenshot = str(out)
            self._last_shot_time = time.time()
            return str(out)
        except Exception as exc:
            logger.debug("Screenshot skipped: %s", exc)
            return self._last_screenshot

    def _open_url_sync(
        self, url: str, wait_until: str = "domcontentloaded", screenshot_label: str = "nav"
    ) -> BrowserActionResult:
        """Route navigation to the dedicated tab in the user's existing Chrome window.

        - Opens LinkedIn in a tab dedicated to LinkedIn.
        - Opens YouTube in another tab dedicated to YouTube.
        """
        u_lower = (url or "").lower()
        blocked_domains = ("instagram.com", "facebook.com", "fb.com", "tiktok.com", "threads.net", "twitter.com", "x.com")
        if any(d in u_lower for d in blocked_domains):
            logger.info("Blocked navigation to social authwall site: %s", url)
            return BrowserActionResult(success=False, url=url, error="Skipping social authwall domain")

        try:
            if "linkedin.com" in u_lower:
                page = self._get_or_open_tab_sync("linkedin.com")
            elif "youtube.com" in u_lower:
                page = self._get_or_open_tab_sync("youtube.com")
            else:
                page = self._ensure_connection_sync()

            if page is None:
                return BrowserActionResult(success=False, url=url, error="No active browser page available")

            try:
                page.add_init_script(MUTE_AUDIO_SCRIPT)
            except Exception:
                pass
            page.goto(url, wait_until=wait_until, timeout=25000)
            self._mute_page_sync(page)
            try:
                page.bring_to_front()
            except Exception:
                pass
            page.wait_for_timeout(1000)
            self._mute_page_sync(page)
            self._last_url = page.url
            gate = self._detect_access_gate_sync(page)
            shot = self._capture_screenshot_sync(screenshot_label)
            return BrowserActionResult(
                success=True,
                url=page.url,
                title=page.title(),
                screenshot_path=shot,
                gate=gate,
            )
        except Exception as exc:
            logger.warning("Navigation error to %s: %s", url, exc)
            return BrowserActionResult(success=False, url=url, error=str(exc))

    def _click_sync(self, selector: str, timeout_ms: int = 8000) -> BrowserActionResult:
        page = self._ensure_connection_sync()
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            locator.click(timeout=timeout_ms)
            page.wait_for_timeout(600)
            self._last_url = page.url
            return BrowserActionResult(
                success=True,
                url=page.url,
                title=page.title(),
                gate=self._detect_access_gate_sync(page),
            )
        except Exception as exc:
            return BrowserActionResult(success=False, url=page.url, error=str(exc))

    def _type_sync(
        self, selector: str, text: str, clear: bool = True, press_enter: bool = False, timeout_ms: int = 8000
    ) -> BrowserActionResult:
        page = self._ensure_connection_sync()
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            if clear:
                locator.fill("")
            locator.type(text, delay=30)
            if press_enter:
                locator.press("Enter")
                page.wait_for_timeout(1000)
            self._last_url = page.url
            return BrowserActionResult(
                success=True,
                url=page.url,
                title=page.title(),
                gate=self._detect_access_gate_sync(page),
            )
        except Exception as exc:
            return BrowserActionResult(success=False, url=page.url, error=str(exc))

    def _scroll_sync(self, direction: str = "down", pixels: int = 900) -> BrowserActionResult:
        page = self._ensure_connection_sync()
        delta = pixels if direction == "down" else -pixels
        try:
            page.evaluate(f"window.scrollBy(0, {int(delta)})")
            page.wait_for_timeout(600)
            return BrowserActionResult(success=True, url=page.url, title=page.title())
        except Exception as exc:
            return BrowserActionResult(success=False, url=page.url, error=str(exc))

    def _go_back_sync(self) -> BrowserActionResult:
        page = self._ensure_connection_sync()
        try:
            page.go_back(wait_until="domcontentloaded")
            page.wait_for_timeout(600)
            self._last_url = page.url
            return BrowserActionResult(success=True, url=page.url, title=page.title())
        except Exception as exc:
            return BrowserActionResult(success=False, url=page.url, error=str(exc))

    def _switch_tab_sync(self, index: int = 0) -> BrowserActionResult:
        self._ensure_connection_sync()
        pages = self._context.pages if self._context else []
        if not pages or index < 0 or index >= len(pages):
            return BrowserActionResult(success=False, error=f"Tab index {index} out of range ({len(pages)} tabs)")
        self._page = pages[index]
        self._page.bring_to_front()
        self._last_url = self._page.url
        return BrowserActionResult(success=True, url=self._page.url, title=self._page.title())

    def _open_tab_sync(self, url: str | None = None) -> BrowserActionResult:
        try:
            self._ensure_connection_sync()
            if self._context:
                new_page = self._context.new_page()
                self._page = new_page
                if url:
                    return self._open_url_sync(url)
                return BrowserActionResult(success=True, url=new_page.url, title=new_page.title())
        except Exception as exc:
            logger.warning("Error opening new tab: %s", exc)
        return BrowserActionResult(success=False, error="Failed to open new tab")

    def _read_visible_text_sync(self, max_chars: int = 15000) -> str:
        page = self._ensure_connection_sync()
        try:
            txt = page.inner_text("body") or ""
            return txt[:max_chars]
        except Exception:
            return ""

    def _get_html_sync(self) -> str:
        page = self._ensure_connection_sync()
        try:
            return page.content() or ""
        except Exception:
            return ""

    def _evaluate_sync(self, script: str, arg: Any = None) -> Any:
        page = self._ensure_connection_sync()
        return page.evaluate(script, arg) if arg is not None else page.evaluate(script)

    def _capture_video_frames_sync(self, max_frames: int = 1) -> dict[str, Any]:
        page = self._ensure_connection_sync()
        settings = get_settings()
        settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        frames: list[str] = []
        audio_accessible = False
        video_meta: dict[str, Any] = {}

        try:
            self._mute_page_sync(page)
            video_meta = page.evaluate(
                """() => {
                    const v = document.querySelector('video');
                    if (!v) return { found: false };
                    v.muted = true;
                    v.volume = 0;
                    return {
                        found: true,
                        videoWidth: v.videoWidth || 0,
                        videoHeight: v.videoHeight || 0,
                        duration: Number.isFinite(v.duration) ? v.duration : 0,
                        muted: true,
                        src: v.currentSrc || v.src || null
                    };
                }"""
            )
            if video_meta.get("found"):
                audio_accessible = False
                video_loc = page.locator("video").first
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                out_path = settings.screenshots_dir / f"{ts}_frame.png"
                try:
                    video_loc.screenshot(path=str(out_path))
                    frames.append(str(out_path))
                except Exception:
                    pass
                # Pause video playback immediately after frame capture
                try:
                    page.evaluate("() => { document.querySelectorAll('video, audio').forEach(el => { el.muted = true; el.volume = 0; try { el.pause(); } catch (e) {} }); }")
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Video frame extraction: %s", exc)

        if not frames:
            shot = self._capture_screenshot_sync("page_visual")
            if shot:
                frames.append(shot)

        return {
            "video_found": bool(video_meta.get("found")),
            "video_meta": video_meta,
            "frame_paths": frames,
            "audio_accessible": audio_accessible,
        }

    def _check_linkedin_auth_sync(self, force_navigate: bool = False) -> dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            if not self._is_cdp_available():
                return {
                    "status": "Chrome Standby",
                    "reason": "Chrome is not connected on port 9222.",
                    "last_checked": now_iso,
                    "url": None,
                }
            self._ensure_connection_sync()
            if self._context is not None:
                # 1. Cookie check (li_at)
                for c in self._context.cookies():
                    if "linkedin.com" in c.get("domain", "") and c.get("name") == "li_at":
                        exp = c.get("expires", -1)
                        if exp == -1 or exp > time.time():
                            return {
                                "status": "Logged In",
                                "reason": "Active authenticated LinkedIn session cookie (li_at) present in Chrome.",
                                "last_checked": now_iso,
                                "url": self._page.url if self._page else None,
                            }

                # 2. Check open tabs
                for p in self._context.pages:
                    u = (p.url or "").lower()
                    if "linkedin.com" in u and "/login" not in u and "/uas/login" not in u:
                        return {
                            "status": "Logged In",
                            "reason": "Active LinkedIn session open in Chrome tab.",
                            "last_checked": now_iso,
                            "url": p.url,
                        }

            if force_navigate:
                page = self._get_or_open_tab_sync("linkedin.com")
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1500)
                return self._check_linkedin_auth_sync(force_navigate=False)

            return {
                "status": "Login Required",
                "reason": "LinkedIn login required.",
                "last_checked": now_iso,
                "url": self._page.url if self._page else None,
            }
        except Exception as exc:
            return {
                "status": "Connection Error",
                "reason": f"Browser communication error: {exc}",
                "last_checked": now_iso,
                "url": None,
            }

    def _check_youtube_auth_sync(self, force_navigate: bool = False) -> dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            if not self._is_cdp_available():
                return {
                    "status": "Chrome Standby",
                    "reason": "Chrome is not connected on port 9222.",
                    "last_checked": now_iso,
                    "url": None,
                }
            self._ensure_connection_sync()
            if self._context is not None:
                for c in self._context.cookies():
                    dom = c.get("domain", "")
                    if ("youtube.com" in dom or "google.com" in dom) and c.get("name") in ("SID", "__Secure-1PSID", "LOGIN_INFO"):
                        exp = c.get("expires", -1)
                        if exp == -1 or exp > time.time():
                            return {
                                "status": "Logged In",
                                "reason": "Active YouTube/Google session cookies present in Chrome.",
                                "last_checked": now_iso,
                                "url": self._page.url if self._page else None,
                            }

            return {
                "status": "Login Required",
                "reason": "No active YouTube/Google session cookies found.",
                "last_checked": now_iso,
                "url": self._page.url if self._page else None,
            }
        except Exception as exc:
            return {
                "status": "Connection Error",
                "reason": f"Browser communication error: {exc}",
                "last_checked": now_iso,
                "url": None,
            }

    def _open_platform_login_sync(self, platform: str) -> dict[str, Any]:
        page = self._get_or_open_tab_sync("linkedin.com" if platform == "linkedin" else "youtube.com")
        target_url = "https://www.linkedin.com/login" if platform == "linkedin" else "https://accounts.google.com/ServiceLogin?service=youtube"
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            page.bring_to_front()
        except Exception as exc:
            logger.warning("Open platform login goto error: %s", exc)

        shot = self._capture_screenshot_sync(f"{platform}_tab_opened")
        return {
            "success": True,
            "platform": platform,
            "url": page.url,
            "screenshot": shot,
            "message": f"Opened {platform.capitalize()} tab in Chrome.",
        }

    def _disconnect_platform_sync(self, platform: str) -> bool:
        if not self._context:
            return True
        domains = ["linkedin.com", ".linkedin.com"] if platform == "linkedin" else ["youtube.com", ".youtube.com", "google.com", ".google.com"]
        try:
            cookies = self._context.cookies()
            remaining = [c for c in cookies if not any(d in c.get("domain", "").lower() for d in domains)]
            self._context.clear_cookies()
            if remaining:
                self._context.add_cookies(remaining)
            return True
        except Exception as exc:
            logger.warning("Disconnect platform error: %s", exc)
            return False

    def _get_live_screenshot_sync(self) -> str | None:
        if not self._is_cdp_available():
            return self._last_screenshot
        now = time.time()
        # Fast path: if captured within the last 2.5s, return immediately to prevent CDP blocking
        if self._last_screenshot and Path(self._last_screenshot).exists() and (now - self._last_shot_time) < 2.5:
            return self._last_screenshot
        if not self._active or self._page is None or self._context is None:
            return self._last_screenshot
        try:
            if self._context is not None:
                pages = [p for p in self._context.pages if not p.is_closed() and not (p.url or "").startswith("chrome://")]
                if pages:
                    self._page = pages[0]
                elif self._context.pages:
                    self._page = self._context.pages[0]
            if self._page and not self._page.is_closed():
                self._last_url = self._page.url
                return self._capture_screenshot_sync("live_sync")
        except Exception as exc:
            logger.debug("Live screenshot error: %s", exc)
        return self._last_screenshot

    def _compute_browser_status_sync(self) -> dict[str, Any]:
        from app.services.research_workflow import workflow_manager

        running_task = workflow_manager.agent_state == "running" and workflow_manager.active_task_id is not None
        paused_task = workflow_manager.agent_state == "paused" and workflow_manager.active_task_id is not None
        cdp_up = self._is_cdp_available()
        settings = get_settings()
        is_cloud = bool(settings.browser_headless or settings.environment != "development")

        if not self.is_active:
            status = (
                "Research in progress"
                if running_task
                else (
                    "Waiting for manual login"
                    if paused_task
                    else ("Chrome Connected" if cdp_up else ("Cloud Chromium Standby" if is_cloud else "Chrome Standby"))
                )
            )
            return {
                "browser_status": status,
                "browser_active": bool(cdp_up),
                "linkedin_authenticated": False,
                "youtube_authenticated": False,
                "current_url": self._last_url,
            }

        now = time.time()
        if now - self._cached_auth_time > 8.0 or not self._cached_auth_state:
            li_cookie = False
            yt_cookie = False
            if self._context is not None:
                try:
                    for c in self._context.cookies():
                        dom = c.get("domain", "")
                        name = c.get("name", "")
                        if "linkedin.com" in dom and name == "li_at":
                            exp = c.get("expires", -1)
                            if exp == -1 or exp > time.time():
                                li_cookie = True
                        if ("youtube.com" in dom or "google.com" in dom) and name in ("SID", "__Secure-1PSID", "LOGIN_INFO"):
                            exp = c.get("expires", -1)
                            if exp == -1 or exp > time.time():
                                yt_cookie = True
                except Exception:
                    pass
            self._cached_auth_state = {"linkedin": li_cookie, "youtube": yt_cookie}
            self._cached_auth_time = now
        else:
            li_cookie = self._cached_auth_state.get("linkedin", False)
            yt_cookie = self._cached_auth_state.get("youtube", False)

        if running_task:
            status = "Research in progress"
        elif paused_task:
            status = "Waiting for manual login"
        else:
            cur_url = (self._page.url or "").lower() if self._page and not self._page.is_closed() else ""
            if any(w in cur_url for w in ("/login", "/uas/login", "servicelogin", "signin")):
                status = "Waiting for manual login"
            elif li_cookie:
                status = "LinkedIn authenticated"
            elif yt_cookie:
                status = "YouTube authenticated"
            else:
                status = "Cloud Chromium Active" if is_cloud and not cdp_up else "Chrome Connected"

        return {
            "browser_status": status,
            "browser_active": self.is_active,
            "linkedin_authenticated": li_cookie,
            "youtube_authenticated": yt_cookie,
            "current_url": self._last_url,
        }

    def _launch_external_browser_sync(self, target: str = "linkedin") -> dict[str, Any]:
        """Launch browser or initialize cloud browser connection."""
        settings = get_settings()
        is_cloud = bool(settings.browser_headless or settings.environment != "development")
        target_url = "https://www.linkedin.com/login" if target == "linkedin" else "https://www.youtube.com"

        if not self._is_cdp_available() and not is_cloud:
            import subprocess
            for chrome_path in [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]:
                if Path(chrome_path).exists():
                    try:
                        subprocess.Popen([
                            chrome_path,
                            "--remote-debugging-port=9222",
                            f"--user-data-dir={settings.resolved_browser_user_data_dir}",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--mute-audio",
                            target_url,
                        ])
                        time.sleep(2)
                        break
                    except Exception as e:
                        logger.debug("Failed launching local chrome: %s", e)

        res = self._start_sync()
        if target_url:
            self._open_url_sync(target_url, screenshot_label=f"launch_{target}")

        return {
            "success": True,
            "channel": res.get("channel", "active"),
            "url": self._last_url or target_url,
            "message": f"Browser active on {target}. Connect local agent if using desktop Chrome with cloud backend.",
        }

    # Public Async Interface
    async def get_live_screenshot(self) -> str | None:
        return await self._run(self._get_live_screenshot_sync)

    async def compute_browser_status(self) -> dict[str, Any]:
        return await self._run(self._compute_browser_status_sync)

    async def launch_external_browser(self, target: str = "linkedin") -> dict[str, Any]:
        return await self._run(self._launch_external_browser_sync, target)

    async def close_external_browser(self) -> dict[str, Any]:
        await self._run(self._stop_sync)
        return {"success": True, "message": "Browser disconnected."}

    async def reconnect_external_browser(self, target: str = "linkedin") -> dict[str, Any]:
        await self._run(self._stop_sync)
        await asyncio.sleep(0.5)
        return await self._run(self._launch_external_browser_sync, target)

    async def reset_browser_session(self) -> bool:
        def _reset_sync():
            self._disconnect_platform_sync("linkedin")
            self._disconnect_platform_sync("youtube")
            self._cached_auth_state = {"linkedin": False, "youtube": False}
            self._cached_auth_time = 0.0
            return True
        return await self._run(_reset_sync)

    async def check_platform_auth(self, platform: str, force_navigate: bool = False) -> dict[str, Any]:
        if platform == "linkedin":
            return await self._run(self._check_linkedin_auth_sync, force_navigate)
        return await self._run(self._check_youtube_auth_sync, force_navigate)

    async def open_platform_login(self, platform: str) -> dict[str, Any]:
        return await self._run(self._open_platform_login_sync, platform)

    async def disconnect_platform(self, platform: str) -> bool:
        return await self._run(self._disconnect_platform_sync, platform)

    async def start(self, headless: bool | None = None) -> dict[str, Any]:
        return await self._run(self._start_sync, headless)

    async def stop(self) -> None:
        await self._run(self._stop_sync)

    async def open_url(
        self, url: str, wait_until: str = "domcontentloaded", screenshot_label: str = "nav"
    ) -> BrowserActionResult:
        return await self._run(self._open_url_sync, url, wait_until, screenshot_label)

    async def click(self, selector: str, timeout_ms: int = 8000) -> BrowserActionResult:
        return await self._run(self._click_sync, selector, timeout_ms)

    async def type_text(
        self, selector: str, text: str, clear: bool = True, press_enter: bool = False, timeout_ms: int = 8000
    ) -> BrowserActionResult:
        return await self._run(self._type_sync, selector, text, clear, press_enter, timeout_ms)

    async def scroll(self, direction: str = "down", pixels: int = 900) -> BrowserActionResult:
        return await self._run(self._scroll_sync, direction, pixels)

    async def go_back(self) -> BrowserActionResult:
        return await self._run(self._go_back_sync)

    async def switch_tab(self, index: int = 0) -> BrowserActionResult:
        return await self._run(self._switch_tab_sync, index)

    async def open_tab(self, url: str | None = None) -> BrowserActionResult:
        return await self._run(self._open_tab_sync, url)

    async def read_visible_text(self, max_chars: int = 15000) -> str:
        return await self._run(self._read_visible_text_sync, max_chars)

    async def get_html(self) -> str:
        return await self._run(self._get_html_sync)

    async def capture_screenshot(self, label: str = "page") -> str | None:
        return await self._run(self._capture_screenshot_sync, label)

    async def detect_access_gate(self) -> AccessGateStatus:
        return await self._run(lambda: self._detect_access_gate_sync(self._ensure_connection_sync()))

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        return await self._run(self._evaluate_sync, script, arg)

    async def capture_video_frames(self, max_frames: int = 3) -> dict[str, Any]:
        return await self._run(self._capture_video_frames_sync, max_frames)


browser_controller = BrowserController()
