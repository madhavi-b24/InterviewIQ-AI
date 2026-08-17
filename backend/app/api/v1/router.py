"""Aggregates every v1 router. Feature routers (auth, resumes, interview
sessions, ...) get added here as their modules are built — see API.md.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.planning import router as planning_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(resumes_router)
api_router.include_router(planning_router)
api_router.include_router(interviews_router)
