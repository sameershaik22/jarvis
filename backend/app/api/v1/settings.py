from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_agency_id
from app.config import get_settings
from app.db.models import AppSetting
from app.db.session import get_database_status, get_db
from app.schemas.settings import SafeSettingsOut, SafeSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_runtime_overrides(db: Session, agency_id: str) -> dict:
    rows = db.query(AppSetting).filter(AppSetting.agency_id == agency_id).all()
    return {r.key: r.value_json.get("value") for r in rows if isinstance(r.value_json, dict)}


@router.get("", response_model=SafeSettingsOut)
def get_safe_settings(
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> SafeSettingsOut:
    """Return safe configuration & DB status. Never exposes API keys or DB credentials."""
    settings = get_settings()
    overrides = _get_runtime_overrides(db, agency_id)
    return SafeSettingsOut(
        openai_model=str(overrides.get("openai_model") or settings.openai_model),
        openai_configured=bool(settings.openai_api_key and settings.openai_api_key.strip()),
        gemini_model=str(overrides.get("gemini_model") or settings.gemini_model),
        gemini_configured=bool(settings.gemini_api_key and settings.gemini_api_key.strip()),
        tavily_configured=bool(settings.tavily_api_key and settings.tavily_api_key.strip()),
        apollo_configured=bool(settings.apollo_api_key and settings.apollo_api_key.strip()),
        n8n_configured=bool(settings.n8n_webhook_url and settings.n8n_webhook_url.strip()),
        browser_headless=bool(
            overrides["browser_headless"] if "browser_headless" in overrides else settings.browser_headless
        ),
        browser_channel=str(overrides.get("browser_channel") or settings.browser_channel),
        default_search_keyword=str(overrides.get("default_search_keyword") or settings.default_search_keyword),
        quality_threshold=int(
            overrides["quality_threshold"] if "quality_threshold" in overrides else settings.quality_threshold
        ),
        max_posts_per_run=int(
            overrides["max_posts_per_run"] if "max_posts_per_run" in overrides else settings.max_posts_per_run
        ),
        database_status=get_database_status(),
    )


@router.put("", response_model=SafeSettingsOut)
def update_safe_settings(
    payload: SafeSettingsUpdate,
    agency_id: str = Depends(get_agency_id),
    db: Session = Depends(get_db),
) -> SafeSettingsOut:
    settings = get_settings()
    updates = payload.model_dump(exclude_none=True)
    for k, v in updates.items():
        row = db.query(AppSetting).filter(AppSetting.agency_id == agency_id, AppSetting.key == k).first()
        if row:
            row.value_json = {"value": v}
        else:
            db.add(AppSetting(agency_id=agency_id, key=k, value_json={"value": v}))
        if agency_id == "default" and hasattr(settings, k):
            setattr(settings, k, v)
    db.commit()
    return get_safe_settings(agency_id=agency_id, db=db)
