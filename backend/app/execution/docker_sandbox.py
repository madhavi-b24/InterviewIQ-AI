"""MVP CodeExecutor backend — not implemented yet.

Real implementation lands in Module 6 (Code Execution Subsystem +
Coding Round): one ephemeral, network-disabled container per submission,
with the resource limits and read-only filesystem controls specified in
Architecture.md §6. This stub exists so the rest of the app can depend on
the CodeExecutor Protocol and be wired via dependency injection today.
"""

from app.execution.base import CodeExecutor, TestCase, TestCaseResult


class DockerSandboxExecutor(CodeExecutor):
    async def run(
        self, *, source_code: str, language: str, test_cases: list[TestCase]
    ) -> list[TestCaseResult]:
        raise NotImplementedError(
            "DockerSandboxExecutor is scaffolded but not implemented — see Roadmap.md Module 6"
        )
