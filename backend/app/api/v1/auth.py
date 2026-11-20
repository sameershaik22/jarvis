from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.services.browser_controller import browser_controller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
async def get_auth_status(force: bool = False) -> dict[str, Any]:
    """Check authentication status for both LinkedIn and YouTube."""
    li_status = await browser_controller.check_platform_auth("linkedin", force_navigate=force)
    yt_status = await browser_controller.check_platform_auth("youtube", force_navigate=force)
    return {
        "linkedin": li_status,
        "youtube": yt_status,
    }


@router.post("/linkedin/connect")
async def connect_linkedin() -> dict[str, Any]:
    """Launch visible browser navigating to LinkedIn login for user manual login."""
    res = await browser_controller.open_platform_login("linkedin")
    return {
        "status": "browser_opened",
        "message": "Chrome has opened to LinkedIn login on your screen. Enter credentials manually.",
        "details": res,
    }


@router.post("/youtube/connect")
async def connect_youtube() -> dict[str, Any]:
    """Launch visible browser navigating to Google/YouTube login for user manual login."""
    res = await browser_controller.open_platform_login("youtube")
    return {
        "status": "browser_opened",
        "message": "Chrome has opened to Google/YouTube sign-in on your screen. Enter credentials manually.",
        "details": res,
    }


@router.post("/linkedin/disconnect")
async def disconnect_linkedin() -> dict[str, Any]:
    """Clear LinkedIn cookies from browser profile."""
    ok = await browser_controller.disconnect_platform("linkedin")
    return {"success": ok, "platform": "linkedin"}


@router.post("/youtube/disconnect")
async def disconnect_youtube() -> dict[str, Any]:
    """Clear YouTube/Google cookies from browser profile."""
    ok = await browser_controller.disconnect_platform("youtube")
    return {"success": ok, "platform": "youtube"}


@router.post("/session/reset")
async def reset_session() -> dict[str, Any]:
    """Safely reset all browser sessions and clear profile directory."""
    ok = await browser_controller.reset_browser_session()
    return {"success": ok, "message": "Browser profile reset."}

