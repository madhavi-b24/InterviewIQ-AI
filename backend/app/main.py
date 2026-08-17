"""FastAPI application entry point.

Run with: uvicorn app.main:app --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.checkpointer import get_checkpointer
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import get_engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("app.startup", environment=get_settings().ENVIRONMENT)
    # Module 5 — LangGraph's own checkpoint tables (separate from our
    # Alembic-managed schema, app/agents/checkpointer.py). `.setup()` is
    # idempotent ("creates tables if they don't already exist and runs
    # migrations" — verified directly against the installed
    # langgraph-checkpoint-postgres before relying on this), so running it
    # on every startup is safe, not just a first-run step.
    async with get_checkpointer() as checkpointer:
        await checkpointer.setup()
    logger.info("app.checkpointer_ready")
    yield
    await get_engine().dispose()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="InterviewIQ AI",
        description="AI Interview Coach — adaptive, multi-agent technical interviews",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
