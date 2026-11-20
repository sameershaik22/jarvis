from __future__ import annotations

from fastapi import Header


def get_agency_id(x_agency_id: str | None = Header(default=None)) -> str:
    """Resolve current workspace/agency tenant ID (defaults to 'default' for single-agency mode)."""
    cleaned = (x_agency_id or "").strip()
    return cleaned if cleaned else "default"

