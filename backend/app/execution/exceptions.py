"""CodeExecutor error hierarchy — mirrors every other provider seam in this
codebase (ResumeIntelligenceError, InterviewIntelligenceError): one base,
a timeout leaf, a "reachable but failed" leaf. Callers catch these, never
a raw httpx/network exception, so swapping the execution backend
(docker_sandbox -> judge0) never changes calling code's error handling.
"""


class CodeExecutionError(Exception):
    """Base for every failure mode a CodeExecutor implementation can raise."""


class CodeExecutionTimeoutError(CodeExecutionError):
    """The executor didn't respond within CODE_EXECUTION_TIMEOUT_SECONDS —
    distinct from a per-test-case TIME_LIMIT status (module §7), which is a
    normal, successfully-reported outcome, not a failure of the execution
    subsystem itself.
    """


class CodeExecutionProviderError(CodeExecutionError):
    """The executor was reachable but the request itself failed — a
    malformed response, a connection refused, an unexpected 5xx from the
    sibling `executor` container, or an unsupported language it rejected.
    """
