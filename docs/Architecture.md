# InterviewIQ AI — System Architecture

Status: **Module 1 — locked pending final consistency pass**
Owner: Architecture module (Module 1)

This document defines the system architecture for InterviewIQ AI. [Database.md](Database.md) derives its entities from the domains defined here.

---

## 1. Design Goals

| Goal | Implication |
|---|---|
| Interviews must survive across HTTP requests | Interview state is a **resumable graph**, not in-memory session state |
| Multiple AI agents must collaborate, not just chain | Use an explicit orchestrator (Supervisor) over a shared state object, not a linear prompt pipeline |
| Difficulty adapts per-answer | Difficulty is a first-class piece of state, recalculated every turn, not just at report time |
| Resume must actually influence the interview | Resume-derived skills/gaps feed the Question Generator and Difficulty Agent as inputs, not just displayed in a report |
| Coding must be graded on real execution, not just LLM opinion | Candidate code runs against real test cases in a sandboxed executor; the LLM only judges what execution can't (readability, optimization) |
| Every module ships independently reviewable | Clean layering: API ⇄ Services ⇄ Agents/Repositories ⇄ Models. No layer reaches two levels down. |

---

## 2. High-Level System Diagram

```mermaid
flowchart LR
    subgraph Client
        FE[React SPA<br/>Tailwind + Monaco]
    end

    subgraph Backend[FastAPI Backend]
        API[API Layer<br/>REST, versioned /api/v1]
        SVC[Service Layer]
        AGENTS[LangGraph Agent Graph]
        JOBS[Job Runner<br/>BackgroundTasks → Celery-ready]
        EXEC[Code Execution Adapter]
        REPO[Repository Layer]
    end

    PG[(PostgreSQL)]
    REDIS[(Redis)]
    CHROMA[(ChromaDB)]
    GEMINI[[Gemini API]]
    SANDBOX[[Docker Sandbox<br/>→ Judge0 later]]

    FE -->|HTTPS/JSON| API
    API --> SVC
    SVC --> AGENTS
    SVC --> JOBS
    SVC --> REPO
    JOBS --> EXEC
    EXEC --> SANDBOX
    AGENTS -->|checkpoint state| PG
    AGENTS -->|hot cache| REDIS
    AGENTS -->|RAG retrieval| CHROMA
    AGENTS -->|LLM calls| GEMINI
    REPO --> PG
```

**Why FastAPI is stateless but interviews aren't:** each candidate answer is a separate HTTP request. The LangGraph state machine for a given `interview_session` is checkpointed to Postgres after every node executes, keyed by `langgraph_thread_id`. The next request resumes the graph from that checkpoint rather than reconstructing context from scratch.

---

## 3. Monorepo Layout

```
InterviewIQ-AI/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config, security (JWT), logging, exceptions
│   │   ├── api/v1/            # FastAPI routers — thin, no business logic
│   │   ├── schemas/           # Pydantic request/response DTOs
│   │   ├── services/          # use-case orchestration, framework-agnostic
│   │   ├── agents/            # LangGraph nodes, graph definition, agent state
│   │   ├── execution/         # CodeExecutor interface + adapters (docker sandbox, judge0)
│   │   ├── jobs/               # JobRunner interface + adapters (BackgroundTasks, celery-ready)
│   │   ├── repositories/      # DB access, one per aggregate root
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── db/                # session factory, Alembic migrations
│   │   ├── vectorstore/       # ChromaDB client wrapper
│   │   └── cache/             # Redis client wrapper
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                # routes / pages
│   │   ├── features/           # auth, resume, interview, dashboard, reports
│   │   │                        # each feature owns its own Zustand slice
│   │   ├── components/         # shared UI primitives
│   │   ├── lib/                 # api client, hooks
│   │   ├── store/               # Zustand store composition root only
│   │   └── editor/               # Monaco wrapper for coding rounds
│   └── Dockerfile
├── docs/
└── docker-compose.yml
```

**Rule:** `api/` never imports `repositories/` or `agents/` directly — it only calls `services/`. This keeps HTTP concerns out of business logic and makes services independently testable.

---

## 4. Backend Layering (Clean Architecture)

```mermaid
flowchart TD
    A[API Layer<br/>routers, request validation] --> S[Service Layer<br/>use cases: StartInterview, SubmitAnswer, SubmitCode, GenerateReport]
    S --> AG[Agent Layer<br/>LangGraph graph invocation]
    S --> J[Job Runner<br/>async code execution]
    S --> R[Repository Layer<br/>SQLAlchemy queries]
    J --> EX[Execution Adapter]
    R --> M[Models<br/>ORM entities]
    AG --> M
```

- **API layer**: FastAPI routers. Validates input, calls exactly one service method, returns a response schema. No SQL, no LLM calls, no execution logic here.
- **Service layer**: the use cases. Orchestrates repositories, agents, and the job runner. Owns transactions.
- **Agent layer**: LangGraph graph + nodes. Knows nothing about HTTP or raw SQL, only about repository/execution interfaces it's given.
- **Job Runner layer**: abstracts "run this later, possibly slowly" work (code execution, resume parsing/embeddings) behind one interface — see §8.1.
- **Repository layer**: one class per aggregate. Only place raw queries live.

---

## 5. Multi-Agent Interview Engine (LangGraph)

**Status (Module 5): §5.1–5.3 and §5.5 implemented for text rounds** (introduction, technical, behavioral, resume_discussion, system_design). **§5.4 (coding round) remains Module 6** — a `coding` round in a plan is cleanly skipped, never executed/faked (module §7/§15 of the Module 5 task; `interview_rounds.status=skipped`). Learning Agent and Report Agent (roster below) are Module 7, not built. See `app/agents/` (graph + nodes), `app/services/interview_intelligence/` (the Gemini-backed provider seam), and `app/services/interview/execution_service.py` (orchestration/persistence) for the actual implementation, and backend/README.md's "Interview Engine (Module 5)" section for the full design writeup including the deviations from this section's original sketch, called out inline below.

### 5.1 Agent Roster

| Agent | Responsibility | Produces |
|---|---|---|
| **Supervisor Agent** | Owns the graph. Decides round transitions, when to end the interview, routes control. | round/session transitions |
| **Question Generator Agent** | Produces the next question given role, company, difficulty, uncovered topics, resume context. | `questions` row |
| **Knowledge Agent** | RAG retrieval from ChromaDB — company patterns, canonical answers, topic reference material. Grounds question generation and evaluation. | retrieved context (not persisted) |
| **Interview Agent** | Manages conversational flow within a round (follow-ups, clarifying prompts). | conversational turns |
| **Evaluation Agent** | Scores **Technical** and **Problem Solving** for every answer. For coding questions, additionally invokes the Code Execution Adapter, then scores **Coding** correctness (execution-derived, not guessed), readability, and optimization. | `answer_evaluations`, `coding_evaluations` |
| **Communication Agent** | Scores **Communication** and **Confidence** — independent of technical correctness. | `answer_evaluations` fields |
| **Difficulty Agent** | Recomputes a rolling difficulty score after every answer; feeds it back into shared state for the next Question Generator call. | `answer_evaluations.difficulty_signal` |
| **Learning Agent** | Post-interview: maps weak areas to a learning roadmap. | `learning_roadmaps`, `roadmap_items` |
| **Report Agent** | Aggregates all evaluation output into the 5 report section scores (Technical, Coding, Communication, Problem Solving, Confidence) + overall score, each with an explanation. | `interview_reports`, `report_section_scores` |

Every score produced anywhere in this pipeline is stored with its explanation text alongside it — never a bare number. This is enforced at the schema level in [Database.md](Database.md) §6–7.

**Implementation note (Module 5):** the Knowledge Agent is not a ChromaDB RAG lookup for MVP — it's a deterministic in-process helper (resume evidence already surfaced by Module 3 + `role_profiles.json` topic hints), not a graph node at all (see `app/agents/nodes/knowledge.py`'s docstring for why: no LLM call, no I/O, cheap enough to be a plain function other nodes call inline). This is a real, documented seam a future RAG implementation can satisfy without touching callers — not a placeholder pretending to be the real thing.

### 5.2 Shared Graph State

```
InterviewState {
  session_id, user_id
  resume_context: { skills, projects, gaps }
  company, role, current_round, current_difficulty
  conversation_history: [ ... ]
  last_question, last_answer
  running_scores: { technical, coding, communication, problem_solving, confidence }
  round_plan: [ ordered round types, from template_rounds ]
}
```

**As actually implemented** (`app/agents/state.py::InterviewState`) — the same shape, refined: `conversation_history`/`running_scores` became `question_history`/`answer_history` (scoped to the *current round only* — durable full history lives in Postgres, module §3's "do not put enormous duplicated documents into graph state") and `interview_scores` (a running average, display-only, not the report's source of truth); explicit `previous_difficulty` alongside `current_difficulty` so a response can show the transition without a second read; `follow_up_count` and `rounds_to_skip` for the two Module-5-specific mechanics (§8, §7); a `trigger` (`START`/`SUBMIT_ANSWER`) driving deterministic routing instead of relying on LangGraph's `interrupt()`/`Command(resume=...)` (see the Decisions Log entry below for why). Every field carries a one-line "why this exists" comment in the source.

### 5.3 Turn-by-Turn Flow — Text Rounds (technical / behavioral / system design)

```mermaid
sequenceDiagram
    participant C as Candidate (FE)
    participant Sup as Supervisor
    participant QG as Question Generator
    participant K as Knowledge Agent
    participant Eval as Evaluation Agent
    participant Comm as Communication Agent
    participant Diff as Difficulty Agent

    C->>Sup: submit answer (HTTP request)
    Sup->>Eval: evaluate(answer) → technical, problem_solving
    Sup->>Comm: evaluate(answer) → communication, confidence
    Eval->>K: retrieve reference material
    Eval-->>Sup: scores + explanations
    Comm-->>Sup: scores + explanations
    Sup->>Diff: recompute difficulty
    Diff-->>Sup: new difficulty
    Sup->>QG: next question(difficulty, gaps)
    QG->>K: retrieve topic/company context
    QG-->>Sup: question
    Sup-->>C: question (HTTP response) + checkpoint saved
```

This turn is fully synchronous within one request — LLM calls only, no execution latency. **As implemented**, the LLM-call shape differs slightly for cost control (module §23's explicit call-budget instruction, verified live against real Gemini — see backend/README.md): Evaluation Agent and Communication Agent are each exactly one call (technical+problem_solving together; communication+confidence together), Difficulty Agent and the Supervisor's routing are pure Python (zero calls), and exactly one generation call fires per turn — Question Generator **or** Interview Agent (follow-up) **or** neither, if the interview just completed — never both. Budget: 2–3 Gemini calls per answer, 1 call for `/start`.

### 5.4 Turn-by-Turn Flow — Coding Round (asynchronous, Run vs. Submit)

Code execution is not instant, so the coding round cannot follow the synchronous request/response pattern above. It goes through the Job Runner. Every submission is one **attempt** (`code_submissions.attempt_no`); only the attempt marked `is_final` is graded — everything before that is a free "Run" against sample cases only, with no LLM involved:

```mermaid
sequenceDiagram
    participant C as Candidate (FE)
    participant API as API Layer
    participant J as Job Runner
    participant EX as Execution Adapter (sandbox)
    participant Eval as Evaluation Agent
    participant Sup as Supervisor

    C->>API: submit code (is_final: false → "Run")
    API->>API: persist code_submission (attempt_no=n, status=queued)
    API-->>C: 202 Accepted { submission_id, attempt_no }
    API->>J: enqueue execution job (sample test cases only)
    J->>EX: run source against question_test_cases WHERE is_sample
    EX-->>J: per-test-case pass/fail, runtime, memory
    Note over J,C: no Evaluation Agent call — execution-only, candidate polls and iterates

    C->>API: submit code (is_final: true → "Submit")
    API->>API: persist code_submission (is_final=true, status=queued)
    API->>J: enqueue execution job (ALL test cases)
    J->>EX: run source against every question_test_cases row
    EX-->>J: per-test-case pass/fail, runtime, memory
    J->>Eval: execution results (final attempt only)
    Eval->>Eval: correctness_score = f(weighted pass rate) — deterministic
    Eval->>Eval: readability_score, optimization_score — LLM judgment
    Eval-->>Sup: coding_evaluations row + explanations
    Sup-->>C: candidate polls GET /code-submissions/{id} until graded
```

`correctness_score` is **computed from test-case results, not from an LLM opinion** — the LLM only writes the human-readable explanation of *why* those results occurred. `readability_score` and `optimization_score` are the only LLM-judged numbers in this table, because execution alone can't measure them. This satisfies the "no LLM-only code evaluation" requirement structurally, not just by convention. Gating the Evaluation Agent (and its LLM calls) behind `is_final` also bounds LLM cost to exactly one evaluation per coding question, no matter how many times the candidate iterates.

### 5.5 Persistence of Agent State

- LangGraph checkpointer backed by **Postgres** — source of truth for `langgraph_thread_id`.
- **Redis** holds a hot read-through cache of the current turn's state for low-latency polling — never the source of truth.
- **ChromaDB** holds `question_bank`, `knowledge_base`, `resume_embeddings`.

**As implemented (Module 5):** the LangGraph Postgres checkpointer is real and verified working (`app/agents/checkpointer.py` — confirmed live by querying `checkpoints` after a real multi-turn interview; see Database.md §9). But `InterviewExecutionService` treats **Postgres tables, not the checkpoint, as the sole recoverability guarantee** — it rebuilds a complete `InterviewState` from `interview_sessions`/`interview_rounds`/`questions`/`answers`/`answer_evaluations` at the start of every turn rather than resuming a checkpointed mid-turn state, so "stop and resume later" (module §5/§6) works via the idempotent-retry design in `submit_answer` (an `Answer` row is durably committed *before* any LLM call), not via LangGraph's own resume mechanics. The Redis hot-state cache (`session:{id}:hot_state`) was not implemented — `GET .../current-turn` reads Postgres directly, fast enough at MVP scale. `question_bank`/`knowledge_base` were not implemented — see §5.1's Knowledge Agent note above.

---

## 6. Code Execution Subsystem

A pluggable execution boundary, because "how we run untrusted code" is exactly the kind of decision that should never leak into the agent/service logic that depends on it.

```python
class CodeExecutor(Protocol):
    def run(self, source_code: str, language: str, test_cases: list[TestCase]) -> list[TestCaseResult]: ...
```

| Backend | When | Notes |
|---|---|---|
| `DockerSandboxExecutor` | MVP | Spins one ephemeral, network-disabled container per submission from a small set of pinned language images. |
| `Judge0Executor` | Later, swap via config | Same interface, calls a self-hosted or managed Judge0 instance instead of local Docker. |

Selected via `CODE_EXECUTION_BACKEND=docker_sandbox|judge0` and dependency-injected — services and the Evaluation Agent only ever depend on the `CodeExecutor` protocol, never on a concrete backend. Swapping backends later is a config change, not a refactor.

**Sandbox security controls (MVP `DockerSandboxExecutor`):**
- `--network=none` — no outbound network access
- Hard CPU/memory/pids limits per run (`--memory`, `--cpus`, `--pids-limit`)
- Wall-clock timeout per test case, container killed on breach
- Read-only root filesystem; source code mounted read-only, scratch dir only for stdout/stderr capture
- One container per submission, destroyed immediately after

**MVP operational note:** running the sandbox from inside the `backend` container requires either Docker-outside-of-Docker (mount the host's `/var/run/docker.sock`) or a small sibling `execution-worker` service that exposes an internal HTTP endpoint the Job Runner calls. Deferred to the implementation module for this subsystem — flagged here so it isn't a surprise later.

---

## 7. Frontend Architecture

- **Feature-sliced** structure (`features/auth`, `features/resume`, `features/interview`, `features/dashboard`) — each owns its API calls, components, and local state.
- **Zustand**, one store slice per feature (`useAuthStore`, `useInterviewStore`, `useDashboardStore`...), composed at `store/index.ts`. No single monolithic global store — a feature never reaches into another feature's slice directly, it goes through that feature's exported hooks. Redux is not introduced unless a slice genuinely needs middleware/time-travel debugging that Zustand can't give us.
- **Monaco Editor** mounted only inside the coding round feature; submissions poll `GET /submissions/{id}` per §5.4 until graded.
- API client in `lib/` wraps fetch with auth token injection + refresh handling.

---

## 8. Cross-Cutting Concerns

### 8.1 Job Runner Abstraction

```python
class JobRunner(Protocol):
    def enqueue(self, job_name: str, payload: dict) -> str: ...  # returns job id
```

| Backend | When |
|---|---|
| `BackgroundTasksRunner` | MVP — wraps FastAPI's `BackgroundTasks`, runs in-process |
| `CeleryRunner` | Later — same interface, backed by Celery + Redis broker |

Used for: coding-round execution jobs (§5.4), resume parsing/embedding generation. Services depend on `JobRunner`, never on FastAPI's `BackgroundTasks` directly — this is what makes the Celery migration a config/DI change instead of a rewrite.

### 8.2 Other Concerns

| Concern | Approach |
|---|---|
| Auth | JWT access token (short-lived) + rotating refresh token (stored hashed in Postgres). Google OAuth via Authorization Code flow. |
| Config/secrets | `.env` per environment, loaded via Pydantic Settings; never committed. |
| Observability | Structured JSON logging from day one; defer full tracing/metrics stack until post-MVP. |
| Testing | Pytest for backend (services/agents tested with repositories and `CodeExecutor`/`JobRunner` mocked at the interface); Vitest + RTL for frontend. |

---

## 9. Deployment Topology (Docker Compose, local/dev)

```mermaid
flowchart LR
    subgraph docker-compose
        FE[frontend:5173]
        BE[backend:8000]
        PG[(postgres:5432)]
        RD[(redis:6379)]
        CH[(chromadb:8001)]
    end
    FE --> BE
    BE --> PG
    BE --> RD
    BE --> CH
```

The execution sandbox and (later) Celery worker are intentionally left off this diagram until the modules that implement them — adding them here now would lock in details (Docker-socket mount vs. sibling service) that §6 explicitly deferred.

---

## 10. Decisions Log

| # | Decision | Rationale |
|---|---|---|
| 1 | Frontend state: **Zustand**, one slice per feature | Less boilerplate than Redux for a single-team codebase; Redux only if a slice needs middleware Zustand can't provide |
| 2 | Background jobs: **FastAPI BackgroundTasks for MVP**, behind a `JobRunner` interface | Avoids standing up Celery/broker infra before it's needed, without blocking the later migration |
| 3 | Coding round: **real sandboxed execution against test cases**, LLM judges only readability/optimization | Correctness must be objectively verifiable, not LLM opinion; `CodeExecutor` interface keeps Judge0 swap-in cheap |
| 4 | Scoring: **0–100** scale, 5 named sections (Technical, Coding, Communication, Problem Solving, Confidence), every score paired with an explanation | Matches product's reporting taxonomy; enforced at schema level |
| 5 | Interview templates: **normalized relational schema** (`interview_templates` + `template_rounds`), not jsonb | Enables company-specific templates and per-round-type queries without JSON parsing |
| 6 | Code submissions are **multi-attempt** (`attempt_no`/`is_final`); only the final attempt is graded | Candidates need to test against sample cases before committing; gating LLM evaluation behind `is_final` bounds cost and keeps iterative "Run" fast |
| 7 | Interview plan snapshot: **`interview_rounds` stays normalized** (as decision #5 already established for `template_rounds`); a companion `interview_sessions.plan_snapshot` **JSONB** column carries only the denormalized company/role/template labels, difficulty-resolution reasons, and resume-derived personalization — never round order/weights (Module 4) | Round data needs per-round-type queries; label/personalization data is only ever read back whole, so normalizing it would just add snapshot tables with no query benefit. Keeps the "editing a template must never retroactively change a past plan" guarantee (decision reused from `interview_rounds`) without duplicating the whole domain into JSON |
| 8 | `app/services/interview/execution_context.py::build_execution_context()` is the sole Module 4 → Module 5 boundary, reading only `plan_snapshot` + `interview_rounds` (Module 4) | Mirrors Module 3's `app/services/resume/interview_context.py` seam. A LangGraph agent that only ever calls this one function is structurally unable to reach `companies`/`roles`/`interview_templates`/`resumes` directly — the "don't let agents query many unrelated repositories" principle enforced by construction, not convention |
| 9 | Interview graph: **one `ainvoke()` per HTTP request**, driven by an explicit `trigger` field, not LangGraph's `interrupt()`/`Command(resume=...)` (Module 5) | The pinned `langgraph==0.2.76` interrupt API was newer/less battle-tested at the time; a full-state-in, full-state-out invocation per turn maps directly onto API.md's documented "synchronous, returns evaluation + next question" contract and keeps recoverability entirely in Postgres (decision #10), not dependent on resuming a specific graph node |
| 10 | Recoverability for "stop mid-question, resume later" comes from **Postgres + idempotent retry**, not from resuming a LangGraph checkpoint (Module 5) | `InterviewExecutionService` rebuilds `InterviewState` fresh from `interview_sessions`/`interview_rounds`/`questions`/`answers` every turn; the LangGraph Postgres checkpointer is real and verified working (Database.md §9) but is defense-in-depth, not the load-bearing recovery mechanism — simpler to reason about and test than mid-node graph resume, and already sufficient for the stated requirement |
| 11 | Adaptive difficulty is a **pure deterministic function** of `technical_score`/`problem_solving_score` (`app/agents/policy.py`), never LLM-proposed (Module 5) | `>=80` increase / `<=40` decrease / else maintain, clamped at `easy`/`hard`. The wide 40–80 dead zone is the anti-oscillation mechanism. Matches the explicit instruction that an LLM must never freely decide difficulty |
| 12 | Follow-up decision (FOLLOW_UP/NEXT_QUESTION/NEXT_ROUND/COMPLETE) is the Supervisor's **deterministic threshold logic** over a structured `follow_up_worthy` flag the Evaluation Agent sets; only the follow-up's *question text* is LLM-generated (Module 5) | Keeps "should we probe deeper" auditable and bounded (`MAX_FOLLOW_UPS_PER_QUESTION`) without an LLM choosing its own graph transition |
| 13 | Round length (target question count per round type) is a **Module-5-owned policy constant** (`app/agents/policy.py::DEFAULT_QUESTIONS_PER_ROUND`), not a `template_rounds` column (Module 5) | Module 4's schema (approved, not reopened) has no such column; treating round length as an execution-engine policy rather than a plan attribute avoids touching an already-shipped table for a Module 5-only need |

---

*Next: [Database.md](Database.md) — schema derived from the domains above.*
