from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def search_tavily(
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search Google / Web via Tavily Search API for reliable, anti-bot-safe agent discovery."""
    settings = get_settings()
    if not settings.tavily_api_key or not settings.tavily_api_key.strip():
        return []

    payload: dict[str, Any] = {
        "api_key": settings.tavily_api_key.strip(),
        "query": query.strip(),
        "search_depth": "basic",
        "max_results": max_results,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                logger.info("Tavily search for '%s' returned %d results", query, len(results))
                return results
            logger.warning("Tavily search returned status %d: %s", resp.status_code, resp.text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tavily search failed for query '%s': %s", query, exc)
    return []

