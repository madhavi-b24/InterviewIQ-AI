"""MVP JobRunner implementation — wraps FastAPI's BackgroundTasks.

Runs in-process, after the response is sent. No handlers are registered
yet (that starts with Module 3's resume-parsing job); this file only
wires the mechanism so services can start depending on JobRunner today.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import BackgroundTasks

from app.core.logging import get_logger
from app.jobs.base import JobRunner

logger = get_logger(__name__)

JobHandler = Callable[..., Awaitable[None]]

# Populated by feature modules as they add background jobs, e.g.:
#   JOB_HANDLERS["parse_resume"] = parse_resume_job
JOB_HANDLERS: dict[str, JobHandler] = {}


class BackgroundTasksRunner(JobRunner):
    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def enqueue(self, job_name: str, payload: dict[str, Any]) -> str:
        handler = JOB_HANDLERS.get(job_name)
        if handler is None:
            raise NotImplementedError(f"no job handler registered for {job_name!r}")

        job_id = str(uuid4())
        logger.info("job.enqueued", job_name=job_name, job_id=job_id)
        self._background_tasks.add_task(handler, job_id=job_id, **payload)
        return job_id
