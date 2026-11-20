from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import get_agency_id
from app.services.browser_manager import browser_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/bridge", tags=["agent-bridge"])


class BridgeHeartbeatPayload(BaseModel):
    agency_id: str = "default"
    device_id: str = "windows_pc"
    device_name: str = "Windows Desktop"
    linkedin_authenticated: bool = False
    youtube_authenticated: bool = False
    tabs_count: int = 0
    current_url: str | None = None


class BridgeCommandResultPayload(BaseModel):
    agency_id: str = "default"
    command_id: str
    result: dict[str, Any]


@router.websocket("/ws")
async def bridge_websocket_endpoint(
    websocket: WebSocket,
    agency_id: str = Query(default="default"),
    device_id: str = Query(default="windows_pc"),
    device_name: str = Query(default="Windows Desktop"),
):
    """Secure outbound WebSocket connection from a user's desktop local agent."""
    await websocket.accept()
    session = await browser_manager.register_websocket(
        agency_id=agency_id,
        websocket=websocket,
        device_id=device_id,
        device_name=device_name,
    )

    try:
        # Send initial confirmation
        await websocket.send_text(
            json.dumps({
                "type": "welcome",
                "agency_id": agency_id,
                "message": f"YoursBuddy local bridge connected for workspace '{agency_id}'.",
            })
        )

        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
                msg_type = data.get("type", "result")

                if msg_type == "heartbeat":
                    browser_manager.handle_agent_heartbeat(
                        agency_id=agency_id,
                        device_id=data.get("device_id", device_id),
                        device_name=data.get("device_name", device_name),
                        li_auth=bool(data.get("linkedin_authenticated")),
                        yt_auth=bool(data.get("youtube_authenticated")),
                        tabs_count=int(data.get("tabs_count", 0)),
                        current_url=data.get("current_url"),
                    )
                    await websocket.send_text(json.dumps({"type": "heartbeat_ack", "timestamp": data.get("timestamp")}))

                elif msg_type == "result":
                    cmd_id = data.get("id") or data.get("command_id")
                    if cmd_id:
                        browser_manager.resolve_command_result(
                            agency_id=agency_id,
                            command_id=cmd_id,
                            result=data.get("result", data),
                        )
            except Exception as exc:
                logger.warning("Error parsing bridge message: %s", exc)

    except WebSocketDisconnect:
        logger.info("Local agent WebSocket disconnected for agency '%s'", agency_id)
        browser_manager.unregister_websocket(agency_id, websocket)
    except Exception as exc:
        logger.warning("Bridge WebSocket exception for agency '%s': %s", agency_id, exc)
        browser_manager.unregister_websocket(agency_id, websocket)


@router.get("/status")
async def get_bridge_status(agency_id: str = Depends(get_agency_id)) -> dict[str, Any]:
    """Get the current user's local browser bridge connection status."""
    session = browser_manager.get_session(agency_id)
    return {
        "agency_id": agency_id,
        "connected": session.is_local_connected,
        "device_id": session.device_id,
        "device_name": session.device_name,
        "mode": session.mode,
        "linkedin_authenticated": session.linkedin_authenticated,
        "youtube_authenticated": session.youtube_authenticated,
        "tabs_count": session.tabs_count,
        "current_url": session.current_url,
        "last_heartbeat": session.last_heartbeat,
    }


@router.post("/heartbeat")
async def post_bridge_heartbeat(payload: BridgeHeartbeatPayload) -> dict[str, Any]:
    """HTTP heartbeat endpoint for agents operating in polling mode."""
    return browser_manager.handle_agent_heartbeat(
        agency_id=payload.agency_id,
        device_id=payload.device_id,
        device_name=payload.device_name,
        li_auth=payload.linkedin_authenticated,
        yt_auth=payload.youtube_authenticated,
        tabs_count=payload.tabs_count,
        current_url=payload.current_url,
    )


@router.post("/poll")
async def poll_bridge_commands(
    agency_id: str = Query(default="default"),
    timeout: float = Query(default=15.0),
) -> dict[str, Any]:
    """Long-poll endpoint for commands when WebSocket is blocked."""
    session = browser_manager.get_session(agency_id)
    session.mode = "local_poll"
    try:
        cmd = await asyncio.wait_for(session.poll_queue.get(), timeout=min(timeout, 25.0))
        return {"has_command": True, "command": cmd}
    except asyncio.TimeoutError:
        return {"has_command": False}


@router.post("/result")
async def post_bridge_result(payload: BridgeCommandResultPayload) -> dict[str, Any]:
    """Submit command execution result for polling mode."""
    ok = browser_manager.resolve_command_result(
        agency_id=payload.agency_id,
        command_id=payload.command_id,
        result=payload.result,
    )
    return {"accepted": ok, "command_id": payload.command_id}
