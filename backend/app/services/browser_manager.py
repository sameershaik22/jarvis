from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from app.config import get_settings
from app.services.browser_controller import AccessGateStatus, BrowserActionResult, MUTE_AUDIO_SCRIPT

logger = logging.getLogger(__name__)


@dataclass
class UserBrowserSession:
    agency_id: str
    device_id: str = "default_device"
    device_name: str = "Local Desktop"
    ws: WebSocket | None = None
    poll_queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    pending_futures: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.time)
    current_url: str | None = None
    last_screenshot_path: str | None = None
    linkedin_authenticated: bool = False
    youtube_authenticated: bool = False
    tabs_count: int = 0
    mode: str = "standby"  # "local_websocket" | "local_poll" | "cloud_headless" | "standby"

    @property
    def is_local_connected(self) -> bool:
        # Considered connected if active WebSocket or heartbeat within last 25 seconds
        if self.ws is not None:
            return True
        return (time.time() - self.last_heartbeat) < 25.0 and self.mode in ("local_websocket", "local_poll")

    async def dispatch_command(self, action: str, params: dict[str, Any], timeout_seconds: float = 35.0) -> dict[str, Any]:
        """Dispatch a browser automation command to the user's connected local agent."""
        if not self.is_local_connected:
            raise RuntimeError(
                f"Local browser agent for workspace '{self.agency_id}' is not connected. "
                "Please run 'start_agent.bat' on your computer to connect your desktop Chrome."
            )

        cmd_id = f"cmd_{uuid.uuid4().hex[:10]}"
        payload = {
            "id": cmd_id,
            "action": action,
            "params": params,
            "timestamp": time.time(),
        }

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_futures[cmd_id] = fut

        try:
            if self.ws is not None:
                await self.ws.send_text(json.dumps(payload))
            else:
                await self.poll_queue.put(payload)

            result = await asyncio.wait_for(fut, timeout=timeout_seconds)

            # Update session state from command result
            if "url" in result and result["url"]:
                self.current_url = result["url"]
            if "screenshot_base64" in result and result["screenshot_base64"]:
                settings = get_settings()
                settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                shot_path = settings.screenshots_dir / f"{self.agency_id}_{ts}_{action}.png"
                img_data = base64.b64decode(result["screenshot_base64"])
                shot_path.write_bytes(img_data)
                self.last_screenshot_path = str(shot_path)
                result["screenshot_path"] = str(shot_path)
            if action == "capture_video_frames" and "frames_base64" in result:
                settings = get_settings()
                settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
                frame_paths = []
                for idx, b64 in enumerate(result.get("frames_base64", [])):
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                    f_path = settings.screenshots_dir / f"{self.agency_id}_{ts}_frame_{idx}.png"
                    f_path.write_bytes(base64.b64decode(b64))
                    frame_paths.append(str(f_path))
                result["frame_paths"] = frame_paths

            return result
        except asyncio.TimeoutError:
            logger.warning("Command %s (%s) timed out on agent %s", cmd_id, action, self.agency_id)
            raise TimeoutError(f"Local agent did not respond to '{action}' command within {timeout_seconds}s.")
        finally:
            self.pending_futures.pop(cmd_id, None)

    async def open_url(self, url: str, wait_until: str = "domcontentloaded", screenshot_label: str = "nav") -> BrowserActionResult:
        res = await self.dispatch_command("open_url", {"url": url, "wait_until": wait_until, "label": screenshot_label})
        gate_data = res.get("gate") or {}
        gate = AccessGateStatus(
            restricted=bool(gate_data.get("restricted")),
            gate_type=gate_data.get("gate_type"),
            reason=gate_data.get("reason"),
            url=gate_data.get("url"),
        )
        return BrowserActionResult(
            success=bool(res.get("success")),
            url=res.get("url"),
            title=res.get("title"),
            screenshot_path=res.get("screenshot_path"),
            gate=gate,
            error=res.get("error"),
        )

    async def click(self, selector: str, timeout_ms: int = 8000) -> BrowserActionResult:
        res = await self.dispatch_command("click", {"selector": selector, "timeout_ms": timeout_ms})
        return BrowserActionResult(
            success=bool(res.get("success")),
            url=res.get("url"),
            title=res.get("title"),
            error=res.get("error"),
        )

    async def type_text(self, selector: str, text: str, clear: bool = True, press_enter: bool = False, timeout_ms: int = 8000) -> BrowserActionResult:
        res = await self.dispatch_command("type_text", {"selector": selector, "text": text, "clear": clear, "press_enter": press_enter, "timeout_ms": timeout_ms})
        return BrowserActionResult(
            success=bool(res.get("success")),
            url=res.get("url"),
            title=res.get("title"),
            error=res.get("error"),
        )

    async def scroll(self, direction: str = "down", pixels: int = 900) -> BrowserActionResult:
        res = await self.dispatch_command("scroll", {"direction": direction, "pixels": pixels})
        return BrowserActionResult(
            success=bool(res.get("success")),
            url=res.get("url"),
            title=res.get("title"),
            error=res.get("error"),
        )

    async def get_html(self) -> str:
        res = await self.dispatch_command("get_html", {})
        return str(res.get("html", ""))

    async def read_visible_text(self, max_chars: int = 15000) -> str:
        res = await self.dispatch_command("read_visible_text", {"max_chars": max_chars})
        return str(res.get("text", ""))

    async def capture_screenshot(self, label: str = "page") -> str | None:
        res = await self.dispatch_command("capture_screenshot", {"label": label})
        return res.get("screenshot_path")

    async def detect_access_gate(self) -> AccessGateStatus:
        res = await self.dispatch_command("detect_access_gate", {})
        return AccessGateStatus(
            restricted=bool(res.get("restricted")),
            gate_type=res.get("gate_type"),
            reason=res.get("reason"),
            url=res.get("url"),
        )

    async def capture_video_frames(self, max_frames: int = 3) -> dict[str, Any]:
        return await self.dispatch_command("capture_video_frames", {"max_frames": max_frames})

    async def cleanup_stray_tabs(self) -> int:
        if not self.is_local_connected:
            return 0
        try:
            res = await self.dispatch_command("cleanup_stray_tabs", {}, timeout_seconds=10.0)
            return int(res.get("closed_count", 0))
        except Exception:
            return 0

    async def check_platform_auth(self, platform: str) -> dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.is_local_connected:
            return {
                "status": "Local Agent Disconnected",
                "reason": "Please launch the local bridge agent to inspect desktop Chrome authentication.",
                "last_checked": now_iso,
                "url": None,
            }
        try:
            res = await self.dispatch_command("check_auth", {"platform": platform}, timeout_seconds=12.0)
            return {
                "status": res.get("status", "Unknown"),
                "reason": res.get("reason", "Auth inspected via local agent."),
                "last_checked": now_iso,
                "url": res.get("url"),
            }
        except Exception as exc:
            return {
                "status": "Check Error",
                "reason": str(exc),
                "last_checked": now_iso,
                "url": None,
            }

    async def start(self) -> dict[str, Any]:
        return {
            "channel": f"local_chrome ({self.device_name})",
            "url": self.current_url or "about:blank",
            "tabs": self.tabs_count,
        }

    async def stop(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return self.is_local_connected

    async def get_live_screenshot(self) -> str | None:
        return self.last_screenshot_path

    async def launch_external_browser(self, target: str = "linkedin") -> dict[str, Any]:
        target_url = "https://www.linkedin.com" if target == "linkedin" else "https://www.youtube.com"
        if not self.is_local_connected:
            return {
                "success": False,
                "message": (
                    f"Local desktop bridge is offline for workspace '{self.agency_id}'. "
                    "Please run 'start_agent.bat' on your Windows computer to connect desktop Chrome."
                ),
            }
        res = await self.open_url(target_url, screenshot_label=f"launch_{target}")
        return {
            "success": res.success,
            "channel": f"local_chrome ({self.device_name})",
            "url": res.url,
            "message": f"Opened {target} in your local desktop Chrome window.",
        }

    async def close_external_browser(self) -> dict[str, Any]:
        if not self.is_local_connected:
            return {"success": False, "message": "Local agent is not connected."}
        closed = await self.cleanup_stray_tabs()
        return {"success": True, "closed_tabs": closed, "message": "Local tabs cleaned up."}

    async def reconnect_external_browser(self, target: str = "linkedin") -> dict[str, Any]:
        return await self.launch_external_browser(target=target)

    async def compute_browser_status(self) -> dict[str, Any]:
        if not self.is_local_connected:
            return {
                "browser_status": "Local Agent Offline",
                "browser_active": False,
                "device_name": None,
                "linkedin_authenticated": False,
                "youtube_authenticated": False,
                "current_url": self.current_url,
                "mode": "standby",
            }
        return {
            "browser_status": "Local Chrome Connected",
            "browser_active": True,
            "device_name": self.device_name,
            "linkedin_authenticated": self.linkedin_authenticated,
            "youtube_authenticated": self.youtube_authenticated,
            "current_url": self.current_url,
            "mode": self.mode,
            "tabs_count": self.tabs_count,
        }


class MultiUserBrowserManager:
    """Registry maintaining isolated browser sessions per tenant/agency."""

    def __init__(self) -> None:
        self._sessions: dict[str, UserBrowserSession] = {}

    def get_session(self, agency_id: str = "default") -> UserBrowserSession:
        cleaned = agency_id.strip() if agency_id else "default"
        if cleaned not in self._sessions:
            self._sessions[cleaned] = UserBrowserSession(agency_id=cleaned)
        return self._sessions[cleaned]

    async def register_websocket(
        self, agency_id: str, websocket: WebSocket, device_id: str = "windows_pc", device_name: str = "Windows Desktop"
    ) -> UserBrowserSession:
        session = self.get_session(agency_id)
        if session.ws is not None and session.ws != websocket:
            try:
                await session.ws.close(code=1000, reason="New connection registered")
            except Exception:
                pass
        session.ws = websocket
        session.device_id = device_id
        session.device_name = device_name
        session.mode = "local_websocket"
        session.last_heartbeat = time.time()
        logger.info("Local agent WebSocket registered for agency '%s' (device: %s)", agency_id, device_name)
        return session

    def unregister_websocket(self, agency_id: str, websocket: WebSocket) -> None:
        if agency_id in self._sessions:
            session = self._sessions[agency_id]
            if session.ws == websocket:
                session.ws = None
                session.mode = "standby"
                logger.info("Local agent WebSocket unregistered for agency '%s'", agency_id)

    def handle_agent_heartbeat(
        self,
        agency_id: str,
        device_id: str = "default_device",
        device_name: str = "Windows Desktop",
        li_auth: bool = False,
        yt_auth: bool = False,
        tabs_count: int = 0,
        current_url: str | None = None,
    ) -> dict[str, Any]:
        session = self.get_session(agency_id)
        session.device_id = device_id
        session.device_name = device_name
        session.linkedin_authenticated = li_auth
        session.youtube_authenticated = yt_auth
        session.tabs_count = tabs_count
        if current_url:
            session.current_url = current_url
        session.last_heartbeat = time.time()
        if session.mode == "standby":
            session.mode = "local_poll"
        return {"status": "ok", "agency_id": agency_id, "timestamp": time.time()}

    def resolve_command_result(self, agency_id: str, command_id: str, result: dict[str, Any]) -> bool:
        session = self.get_session(agency_id)
        fut = session.pending_futures.get(command_id)
        if fut and not fut.done():
            fut.set_result(result)
            return True
        return False


browser_manager = MultiUserBrowserManager()
