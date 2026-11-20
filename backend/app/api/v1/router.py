from fastapi import APIRouter

from app.api.v1 import agent, auth, dashboard, export, research, settings, verification

api_router = APIRouter()
api_router.include_router(agent.router)
api_router.include_router(auth.router)
api_router.include_router(research.router)
api_router.include_router(verification.router)
api_router.include_router(dashboard.router)
api_router.include_router(export.router)
api_router.include_router(settings.router)

