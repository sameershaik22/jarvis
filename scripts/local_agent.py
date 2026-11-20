#!/usr/bin/env python3
"""
YoursBuddy AI - Local Desktop Chrome Bridge Agent

Connects your local Google Chrome browser (running on port 9222 with remote debugging)
to your cloud-deployed YoursBuddy backend on Render, enabling desktop browser automation
and live tab interaction from the cloud dashboard.

Usage:
    python scripts/local_agent.py [--backend BACKEND_URL] [--port CDP_PORT]

Example:
    python scripts/local_agent.py --backend https://javis-backend-3pfy.onrender.com
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("yoursbuddy-bridge")


def check_local_chrome_cdp(cdp_port: int = 9222) -> dict[str, Any] | None:
    """Verify that desktop Chrome is actively listening with CDP on localhost."""
    url = f"http://127.0.0.1:{cdp_port}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YoursBuddyBridge/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def get_open_tabs(cdp_port: int = 9222) -> list[dict[str, Any]]:
    """Retrieve list of active tabs in local Chrome."""
    url = f"http://127.0.0.1:{cdp_port}/json/list"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YoursBuddyBridge/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    return []


def ping_cloud_backend(backend_url: str, cdp_info: dict[str, Any], open_tabs: list[dict[str, Any]]) -> bool:
    """Send heartbeat from local agent to cloud backend."""
    target_url = f"{backend_url.rstrip('/')}/api/v1/agent/status"
    try:
        req = urllib.request.Request(target_url, headers={"User-Agent": "YoursBuddyBridge/1.0"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.debug("Backend status check error: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="YoursBuddy AI Desktop Chrome Bridge Agent")
    parser.add_argument(
        "--backend",
        default="https://javis-backend-3pfy.onrender.com",
        help="Backend base URL (default: https://javis-backend-3pfy.onrender.com)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="Local Chrome CDP port (default: 9222)",
    )
    args = parser.parse_args()

    backend_url = args.backend.rstrip("/")
    cdp_port = args.port

    print("=" * 70)
    print("  YoursBuddy AI - Desktop Chrome Bridge Agent")
    print("=" * 70)
    print(f"  Cloud Backend:  {backend_url}")
    print(f"  Chrome CDP:     http://127.0.0.1:{cdp_port}")
    print("=" * 70)

    # 1. Check local Chrome
    cdp_info = check_local_chrome_cdp(cdp_port)
    if not cdp_info:
        logger.error(
            "Local Chrome is NOT running on port %d.\n"
            "  Please start Chrome with remote debugging:\n"
            "  chrome.exe --remote-debugging-port=%d --user-data-dir=\"...\"\n"
            "  or run 'Launch Chrome for YoursBuddy.bat' on your Desktop.",
            cdp_port,
            cdp_port,
        )
        sys.exit(1)

    browser_name = cdp_info.get("Browser", "Google Chrome")
    logger.info("Found local browser: %s", browser_name)

    tabs = get_open_tabs(cdp_port)
    li_open = any("linkedin.com" in t.get("url", "") for t in tabs)
    yt_open = any("youtube.com" in t.get("url", "") for t in tabs)
    logger.info(
        "Open tabs: %d total (LinkedIn tab: %s, YouTube tab: %s)",
        len(tabs),
        "Detected" if li_open else "None",
        "Detected" if yt_open else "None",
    )

    # 2. Check Cloud Backend
    logger.info("Connecting to cloud backend at %s...", backend_url)
    backend_ok = ping_cloud_backend(backend_url, cdp_info, tabs)
    if backend_ok:
        logger.info("Successfully connected to cloud backend!")
    else:
        logger.warning("Could not reach cloud backend status. Retrying in background...")

    print("\nBridge is active! Leave this terminal running while using the cloud dashboard.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(10)
            cur_tabs = get_open_tabs(cdp_port)
            li_active = any("linkedin.com" in t.get("url", "") for t in cur_tabs)
            yt_active = any("youtube.com" in t.get("url", "") for t in cur_tabs)
            ok = ping_cloud_backend(backend_url, cdp_info, cur_tabs)
            status_str = "Synced" if ok else "Syncing..."
            logger.info("Heartbeat [%s] - Local tabs: %d (LinkedIn: %s, YouTube: %s)", status_str, len(cur_tabs), li_active, yt_active)
    except KeyboardInterrupt:
        print("\nStopping YoursBuddy bridge agent. Goodbye!")


if __name__ == "__main__":
    main()
