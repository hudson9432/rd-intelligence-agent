"""Top-level API router."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.missions import router as missions_router
from app.api.research import router as research_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(missions_router)
api_router.include_router(research_router)
