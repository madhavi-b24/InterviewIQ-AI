"""JobRunner abstraction — Architecture.md §8.1.

Services depend on this Protocol, never on FastAPI's BackgroundTasks or
Celery directly. Swapping MVP's BackgroundTasksRunner for a CeleryRunner
later is a config/DI change (see app/api/deps.py), not a refactor.
"""

from typing import Any, Protocol


class JobRunner(Protocol):
    def enqueue(self, job_name: str, payload: dict[str, Any]) -> str:
        """Schedule `job_name` to run with `payload`. Returns a job id."""
        ...
