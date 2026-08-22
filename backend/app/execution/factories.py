"""Config-driven factory for the CodeExecutor seam — plain function, not a
FastAPI `Depends`, mirroring app/services/resume/factories.py and
app/services/interview_intelligence/factories.py exactly (same
`_reject_fake_in_production` guard, same shape).
"""

from app.core.config import Settings
from app.execution.base import CodeExecutor
from app.execution.docker_sandbox import DockerSandboxExecutor
from app.execution.fake_executor import get_fake_code_executor


def _reject_fake_in_production(settings: Settings, *, what: str) -> None:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"fake {what} must not be used in production; configure a real backend before deploying"
        )


def build_code_executor(settings: Settings) -> CodeExecutor:
    if settings.CODE_EXECUTION_BACKEND == "docker_sandbox":
        return DockerSandboxExecutor(settings)
    if settings.CODE_EXECUTION_BACKEND == "fake":
        _reject_fake_in_production(settings, what="CodeExecutor")
        return get_fake_code_executor()
    raise NotImplementedError(
        f"code execution backend {settings.CODE_EXECUTION_BACKEND!r} not wired yet"
    )
