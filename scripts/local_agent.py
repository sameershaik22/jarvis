#!/usr/bin/env python3
"""
YoursBuddy AI — Multi-User Desktop Chrome Bridge Agent

Runs on the user's local Windows computer and connects their desktop Chrome instance
(running strictly on localhost:9222) outbound to the cloud FastAPI backend on Render.

Security & Architecture:
- Outbound only: initiates persistent WebSocket/HTTP polling to Render.
- Port 9222 is NEVER exposed to the public internet or external networks.
- Automatic registration: associates the user's machine with their workspace (agency_id).
- Tab control: handles video navigation, host verification, audio muting, and screenshots.

Usage:
    python scripts/local_agent.py [--backend https://javis-backend-3pfy.onrender.com] [--agency-id default]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("yoursbuddy-agent")


def is_cdp_available(port: int = 9222) -> bool:
    """Check if desktop Chrome is currently listening on localhost CDP port."""
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YoursBuddyBridge/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def launch_local_chrome(port: int = 9222) -> bool:
    """Launch desktop Chrome with remote debugging on localhost."""
    logger.info("Attempting to launch desktop Chrome with remote debugging on port %d...", port)
    candidate_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome",
        "google-chrome",
    ]
    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\AutomationData")
    os.makedirs(user_data_dir, exist_ok=True)

    for path in candidate_paths:
        try:
            cmd = [
                path,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--mute-audio",
                "https://www.linkedin.com",
            ]
            subprocess.Popen(cmd)
            # Wait for startup
            for _ in range(12):
                time.sleep(0.5)
                if is_cdp_available(port):
                    logger.info("Chrome launched and listening on port %d.", port)
                    return True
        except Exception:
            continue
    return is_cdp_available(port)


class LocalChromeWorker:
    """Controls the local Chrome instance via Playwright CDP connection."""

    def __init__(self, cdp_port: int = 9222) -> None:
        self.cdp_port = cdp_port
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def connect(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            if self._pw is None:
                self._pw = sync_playwright().start()

            cdp_url = f"http://127.0.0.1:{self.cdp_port}"
            self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context()

            # Find or create a usable page
            for p in self._context.pages:
                if not p.is_closed() and not (p.url or "").startswith("chrome://"):
                    self._page = p
                    break
            if self._page is None:
                self._page = self._context.new_page()

            logger.info("Successfully connected to desktop Chrome over CDP (open pages: %d).", len(self._context.pages))
            return True
        except Exception as exc:
            logger.error("Failed to connect Playwright to desktop Chrome on port %d: %s", self.cdp_port, exc)
            return False

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None

    def _ensure_page(self) -> Any:
        if self._page is None or self._page.is_closed():
            if self._context and not self._browser.is_connected():
                self.connect()
            if self._context:
                pages = [p for p in self._context.pages if not p.is_closed() and not (p.url or "").startswith("chrome://")]
                if pages:
                    self._page = pages[0]
                else:
                    self._page = self._context.new_page()
        return self._page

    def get_auth_status(self) -> tuple[bool, bool, int, str | None]:
        """Returns (linkedin_auth, youtube_auth, open_tabs_count, current_url)."""
        li_auth = False
        yt_auth = False
        tabs_count = 0
        cur_url = None
        try:
            if self._context:
                tabs_count = len(self._context.pages)
                now = time.time()
                for c in self._context.cookies():
                    dom = c.get("domain", "")
                    name = c.get("name", "")
                    exp = c.get("expires", -1)
                    valid = exp == -1 or exp > now
                    if "linkedin.com" in dom and name == "li_at" and valid:
                        li_auth = True
                    if ("youtube.com" in dom or "google.com" in dom) and name in ("SID", "__Secure-1PSID", "LOGIN_INFO") and valid:
                        yt_auth = True
            page = self._ensure_page()
            if page and not page.is_closed():
                cur_url = page.url
        except Exception:
            pass
        return li_auth, yt_auth, tabs_count, cur_url

    def execute_command(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a browser command dispatched from the cloud backend."""
        page = self._ensure_page()
        if page is None:
            return {"success": False, "error": "No active Chrome tab available"}

        try:
            if action == "open_url":
                url = params.get("url", "")
                wait_until = params.get("wait_until", "domcontentloaded")
                page.goto(url, wait_until=wait_until, timeout=35000)
                # Auto-mute media in page to prevent background noise
                try:
                    page.evaluate("document.querySelectorAll('video, audio').forEach(el => { el.muted = true; });")
                except Exception:
                    pass

                # Detect access gates
                gate = self._detect_gate(page)
                shot_b64 = None
                try:
                    shot_bytes = page.screenshot(type="png")
                    shot_b64 = base64.b64encode(shot_bytes).decode("ascii")
                except Exception:
                    pass

                return {
                    "success": True,
                    "url": page.url,
                    "title": page.title(),
                    "gate": gate,
                    "screenshot_base64": shot_b64,
                }

            elif action == "click":
                selector = params.get("selector", "")
                timeout_ms = params.get("timeout_ms", 8000)
                page.click(selector, timeout=timeout_ms)
                return {"success": True, "url": page.url, "title": page.title()}

            elif action == "type_text":
                selector = params.get("selector", "")
                text = params.get("text", "")
                timeout_ms = params.get("timeout_ms", 8000)
                if params.get("clear", True):
                    page.fill(selector, "", timeout=timeout_ms)
                page.type(selector, text, timeout=timeout_ms)
                if params.get("press_enter", False):
                    page.keyboard.press("Enter")
                return {"success": True, "url": page.url, "title": page.title()}

            elif action == "scroll":
                direction = params.get("direction", "down")
                pixels = params.get("pixels", 900)
                delta = pixels if direction == "down" else -pixels
                page.evaluate(f"window.scrollBy(0, {delta})")
                return {"success": True, "url": page.url, "title": page.title()}

            elif action == "get_html":
                html = page.content()
                return {"success": True, "html": html, "url": page.url}

            elif action == "read_visible_text":
                max_chars = params.get("max_chars", 15000)
                text = page.inner_text("body")[:max_chars]
                return {"success": True, "text": text, "url": page.url}

            elif action == "capture_screenshot":
                shot_bytes = page.screenshot(type="png")
                b64 = base64.b64encode(shot_bytes).decode("ascii")
                return {"success": True, "screenshot_base64": b64, "url": page.url}

            elif action == "detect_access_gate":
                gate = self._detect_gate(page)
                return {"success": True, "gate": gate, "url": page.url}

            elif action == "capture_video_frames":
                max_frames = params.get("max_frames", 3)
                frames_b64 = []
                video_meta = {"found": False}
                audio_accessible = False

                try:
                    v_info = page.evaluate("""() => {
                        const v = document.querySelector('video');
                        if (!v) return null;
                        return {
                            duration: v.duration || 0,
                            paused: v.paused,
                            src: v.src || '',
                            videoWidth: v.videoWidth || 0,
                            videoHeight: v.videoHeight || 0
                        };
                    }""")
                    if v_info:
                        video_meta = {"found": True, **v_info}
                        audio_accessible = True

                    # Take 1-2 frames
                    shot_bytes = page.screenshot(type="png")
                    frames_b64.append(base64.b64encode(shot_bytes).decode("ascii"))
                except Exception as e:
                    logger.warning("Frame capture notice: %s", e)

                return {
                    "success": True,
                    "frames_base64": frames_b64,
                    "video_meta": video_meta,
                    "audio_accessible": audio_accessible,
                }

            elif action == "cleanup_stray_tabs":
                closed_count = 0
                if self._context:
                    pages = [p for p in self._context.pages if not p.is_closed()]
                    # Keep at least 1-2 tabs open
                    for stray in pages[2:]:
                        try:
                            stray.close()
                            closed_count += 1
                        except Exception:
                            pass
                return {"success": True, "closed_count": closed_count}

            elif action == "check_auth":
                platform_target = params.get("platform", "linkedin").lower()
                li_auth, yt_auth, _, _ = self.get_auth_status()
                authed = li_auth if platform_target == "linkedin" else yt_auth
                return {
                    "success": True,
                    "status": "Authenticated" if authed else "Not Authenticated",
                    "reason": "Active session cookie verified" if authed else "No session cookie found",
                    "url": page.url,
                }

            else:
                return {"success": False, "error": f"Unknown action '{action}'"}

        except Exception as exc:
            logger.error("Command '%s' failed: %s", action, exc)
            return {"success": False, "error": str(exc), "url": getattr(page, "url", None)}

    def _detect_gate(self, page: Any) -> dict[str, Any]:
        """Detect login walls, CAPTCHA challenges, or verification roadblocks."""
        cur = (page.url or "").lower()
        if any(w in cur for w in ("/checkpoint/challenge", "/uas/login", "/login", "servicelogin", "signin")):
            return {
                "restricted": True,
                "gate_type": "login_wall",
                "reason": "Login page detected. Log in once on desktop Chrome to enable full scraping.",
                "url": page.url,
            }
        try:
            content = page.content().lower()
            if "captcha" in content or "robot" in content or "recaptcha" in content:
                return {
                    "restricted": True,
                    "gate_type": "captcha",
                    "reason": "CAPTCHA challenge detected on page.",
                    "url": page.url,
                }
        except Exception:
            pass
        return {"restricted": False, "gate_type": None, "reason": None, "url": page.url}


async def run_websocket_bridge(
    backend_url: str,
    agency_id: str,
    device_id: str,
    device_name: str,
    worker: LocalChromeWorker,
) -> None:
    """Connect outbound to cloud backend WebSocket and execute browser commands."""
    import websockets

    # Format ws URL: replace https:// with wss:// and http:// with ws://
    parsed = urllib.parse.urlparse(backend_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = (
        f"{ws_scheme}://{parsed.netloc}/api/v1/agent/bridge/ws"
        f"?agency_id={urllib.parse.quote(agency_id)}"
        f"&device_id={urllib.parse.quote(device_id)}"
        f"&device_name={urllib.parse.quote(device_name)}"
    )

    logger.info("Connecting outbound to Cloud WebSocket: %s", ws_url)

    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=25) as ws:
        logger.info("Outbound WebSocket bridge CONNECTED! Workspace: '%s'", agency_id)

        # Heartbeat background task
        async def heartbeat_loop():
            while True:
                await asyncio.sleep(10.0)
                li_auth, yt_auth, tabs, cur_url = worker.get_auth_status()
                hb = {
                    "type": "heartbeat",
                    "agency_id": agency_id,
                    "device_id": device_id,
                    "device_name": device_name,
                    "linkedin_authenticated": li_auth,
                    "youtube_authenticated": yt_auth,
                    "tabs_count": tabs,
                    "current_url": cur_url,
                    "timestamp": time.time(),
                }
                await ws.send(json.dumps(hb))

        hb_task = asyncio.create_task(heartbeat_loop())

        try:
            while True:
                msg_text = await ws.recv()
                try:
                    data = json.loads(msg_text)
                    msg_type = data.get("type")
                    if msg_type == "welcome":
                        logger.info("Cloud Backend: %s", data.get("message"))
                        continue
                    if msg_type == "heartbeat_ack":
                        continue

                    # Command from Cloud Backend
                    cmd_id = data.get("id")
                    action = data.get("action")
                    params = data.get("params", {})

                    if cmd_id and action:
                        logger.info("Executing cloud command: %s (id: %s)...", action, cmd_id)
                        # Execute in thread executor so sync Playwright doesn't block async loop
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(None, worker.execute_command, action, params)
                        res["id"] = cmd_id
                        reply = {
                            "type": "result",
                            "id": cmd_id,
                            "command_id": cmd_id,
                            "result": res,
                        }
                        await ws.send(json.dumps(reply))
                        logger.info("Command %s (id: %s) completed successfully.", action, cmd_id)
                except Exception as inner_exc:
                    logger.warning("Error processing bridge message: %s", inner_exc)
        finally:
            hb_task.cancel()


async def run_http_polling_bridge(
    backend_url: str,
    agency_id: str,
    device_id: str,
    device_name: str,
    worker: LocalChromeWorker,
) -> None:
    """Fallback HTTP long-polling loop if WebSocket is blocked by network."""
    import httpx

    poll_url = f"{backend_url.rstrip('/')}/api/v1/agent/bridge/poll"
    result_url = f"{backend_url.rstrip('/')}/api/v1/agent/bridge/result"
    heartbeat_url = f"{backend_url.rstrip('/')}/api/v1/agent/bridge/heartbeat"

    logger.info("Running in HTTP fallback polling mode against %s", backend_url)

    last_hb = 0.0
    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            now = time.time()
            if now - last_hb > 10.0:
                li_auth, yt_auth, tabs, cur_url = worker.get_auth_status()
                try:
                    await client.post(
                        heartbeat_url,
                        json={
                            "agency_id": agency_id,
                            "device_id": device_id,
                            "device_name": device_name,
                            "linkedin_authenticated": li_auth,
                            "youtube_authenticated": yt_auth,
                            "tabs_count": tabs,
                            "current_url": cur_url,
                        },
                    )
                    last_hb = now
                except Exception as e:
                    logger.debug("Heartbeat error: %s", e)

            # Poll for command
            try:
                resp = await client.post(f"{poll_url}?agency_id={agency_id}&timeout=15.0")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("has_command"):
                        cmd = data.get("command") or {}
                        cmd_id = cmd.get("id")
                        action = cmd.get("action")
                        params = cmd.get("params", {})
                        if cmd_id and action:
                            logger.info("Executing polling command: %s (id: %s)...", action, cmd_id)
                            loop = asyncio.get_running_loop()
                            res = await loop.run_in_executor(None, worker.execute_command, action, params)
                            res["id"] = cmd_id
                            await client.post(
                                result_url,
                                json={"agency_id": agency_id, "command_id": cmd_id, "result": res},
                            )
            except Exception as poll_err:
                logger.debug("Polling tick error: %s", poll_err)
                await asyncio.sleep(2.0)


async def main_async():
    parser = argparse.ArgumentParser(description="YoursBuddy AI - Desktop Chrome Bridge Agent")
    parser.add_argument(
        "--backend",
        default="https://javis-backend-3pfy.onrender.com",
        help="Backend base URL (default: https://javis-backend-3pfy.onrender.com)",
    )
    parser.add_argument(
        "--agency-id",
        default="default",
        help="Workspace / Agency Tenant ID (default: default)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="Local Chrome CDP port (default: 9222)",
    )
    args = parser.parse_args()

    backend_url = args.backend.rstrip("/")
    agency_id = args.agency_id.strip() or "default"
    cdp_port = args.port
    device_id = f"win_{socket.gethostname()}"
    device_name = f"{platform.node()} ({platform.system()})"

    print("=" * 72)
    print("  YoursBuddy AI — Desktop Chrome Bridge Agent")
    print("=" * 72)
    print(f"  Cloud Backend:   {backend_url}")
    print(f"  Workspace:       {agency_id}")
    print(f"  Local Device:    {device_name} [{device_id}]")
    print(f"  Chrome CDP:      http://127.0.0.1:{cdp_port}")
    print("=" * 72)

    # 1. Ensure local Chrome is up
    if not is_cdp_available(cdp_port):
        launched = launch_local_chrome(cdp_port)
        if not launched:
            logger.error(
                "Desktop Chrome is not listening on port %d.\n"
                "Please start Chrome with:\n"
                "  chrome.exe --remote-debugging-port=%d --user-data-dir=%%LOCALAPPDATA%%\\Google\\Chrome\\AutomationData",
                cdp_port,
                cdp_port,
            )
            return

    # 2. Connect Playwright to Chrome
    worker = LocalChromeWorker(cdp_port=cdp_port)
    if not worker.connect():
        logger.error("Could not connect to desktop Chrome on port %d. Exiting.", cdp_port)
        return

    li_auth, yt_auth, tabs, cur_url = worker.get_auth_status()
    logger.info(
        "Desktop Chrome connected! Tabs: %d | LinkedIn: %s | YouTube: %s",
        tabs,
        "Signed in" if li_auth else "Sign in ready",
        "Signed in" if yt_auth else "Sign in ready",
    )

    # 3. Persistent outbound connection loop with auto-reconnect
    backoff = 2.0
    while True:
        try:
            logger.info("Attempting WebSocket bridge connection...")
            await run_websocket_bridge(backend_url, agency_id, device_id, device_name, worker)
            backoff = 2.0
        except Exception as ws_err:
            logger.warning("WebSocket bridge disconnected: %s. Falling back to HTTP polling...", ws_err)
            try:
                await run_http_polling_bridge(backend_url, agency_id, device_id, device_name, worker)
            except Exception as poll_err:
                logger.warning("Polling error: %s. Retrying in %.1fs...", poll_err, backoff)
                await asyncio.sleep(backoff)
                backoff = min(15.0, backoff * 1.5)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[YoursBuddy Bridge Agent stopped by user]")


if __name__ == "__main__":
    main()
