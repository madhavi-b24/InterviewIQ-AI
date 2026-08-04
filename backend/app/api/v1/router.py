"""Aggregates every v1 router. Feature routers (auth, resumes, interview
sessions, ...) get added here as their modules are built — see API.md.
"""

from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
