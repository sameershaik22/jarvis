from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.db.session import get_database_status, init_db
from app.services.browser_controller import browser_controller


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    init_db()
    yield
    await browser_controller.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="YoursBuddy AI — Podcast Host Research Agent",
        version="1.0.0",
        description="Jarvis-like autonomous browser research agent for real estate podcast discovery, host research, verification, and Excel/CSV reporting.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Export-Record-Count", "X-Export-Id"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def health():
        return {"status": "ok", "database": get_database_status()}

    return app


app = create_app()

