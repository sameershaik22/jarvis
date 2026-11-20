from __future__ import annotations

import logging
from typing import Any, Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base

logger = logging.getLogger(__name__)


def normalize_database_url(raw_url: str | None) -> str:
    """Normalize PostgreSQL/Neon connection strings for SQLAlchemy + psycopg2."""
    settings = get_settings()
    if not raw_url or not raw_url.strip():
        # Local dev fallback file inside javis/data so the app remains inspectable
        # before the user provides their Neon DATABASE_URL in .env.
        fallback_path = (settings.data_dir / "yoursbuddy_dev.sqlite3").resolve()
        return f"sqlite:///{fallback_path.as_posix()}"

    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def build_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    normalized = normalize_database_url(database_url if database_url is not None else settings.database_url)
    if normalized.startswith("sqlite"):
        return create_engine(
            normalized,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return create_engine(
        normalized,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_size=5,
        max_overflow=10,
        future=True,
        connect_args={"connect_timeout": 15},
    )


engine: Engine = build_engine()
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, expire_on_commit=False, bind=engine, future=True
)


def reconfigure_engine(database_url: str | None = None) -> Engine:
    global engine
    engine = build_engine(database_url)
    SessionLocal.configure(bind=engine)
    return engine


def init_db(target_engine: Engine | None = None) -> None:
    # Ensure all models are imported before create_all
    import app.db.models  # noqa: F401
    import time

    active_engine = target_engine or engine
    for attempt in range(1, 4):
        try:
            Base.metadata.create_all(bind=active_engine)
            logger.info("Database schema verified successfully on attempt %d", attempt)
            return
        except Exception as exc:
            logger.warning("Database init attempt %d failed: %s. Retrying in 2s...", attempt, exc)
            time.sleep(2)
    logger.error("Database init could not complete all tables, proceeding with available schema.")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_database_status() -> dict[str, Any]:
    settings = get_settings()
    raw_url = settings.database_url
    is_neon_configured = bool(raw_url and raw_url.strip() and not raw_url.strip().startswith("sqlite"))
    provider = "sqlite_local_fallback"
    masked_host = "local_sqlite"

    if is_neon_configured and raw_url:
        parsed = urlparse(raw_url.strip())
        hostname = parsed.hostname or "unknown"
        provider = "neon_postgresql" if "neon" in hostname.lower() else "postgresql"
        masked_host = hostname

    connected = False
    error: str | None = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        connected = True
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    return {
        "configured": is_neon_configured,
        "provider": provider,
        "host": masked_host,
        "connected": connected,
        "error": error,
    }

