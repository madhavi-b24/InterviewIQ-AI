# InterviewIQ AI — Build Roadmap

Status: **Module 1 (this document) in progress**

We build exactly one module at a time. Each module below has an explicit exit criteria — implementation does not move to the next module until the current one is reviewed and approved. This is the operating rule for the whole project, not just a suggestion.

---

## Module 1 — Foundation (current)

**Goal:** lock the architecture, schema, and scope before any application code exists.

- [x] [Architecture.md](Architecture.md) — system design, layering, multi-agent design, execution/job runner abstractions
- [x] [Database.md](Database.md) — full Postgres schema
- [x] [Vision.md](Vision.md) — problem, users, principles, non-goals
- [x] [Features.md](Features.md) — MVP vs. later scope per module
- [x] [API.md](API.md) — REST surface for MVP scope
- [x] Final cross-doc consistency review
- [ ] Repo scaffolding: `backend/` FastAPI skeleton + `frontend/` React skeleton matching Architecture.md §3, `docker-compose.yml` for Postgres/Redis/ChromaDB/backend/frontend, Alembic initialized against the Database.md schema

**Exit criteria:** `docker-compose up` brings up an empty-but-wired stack (FastAPI health endpoint reachable, DB migrated, frontend renders a placeholder page). No feature logic yet.

---

## Module 2 — Authentication

**Scope:** all MVP rows from [Features.md](Features.md) §1.

- `users`, `refresh_tokens` tables live via Alembic migration
- Register, login, JWT + refresh rotation, Google OAuth, email verification, password reset
- Frontend: auth pages + `useAuthStore` Zustand slice + protected route handling

**Exit criteria:** a real user can register, verify email, log in (both local and Google), stay logged in across a token refresh, and log out — end to end, manually tested in the browser per this project's "test the golden path in a browser" rule.

---

## Module 3 — Resume Intelligence

**Scope:** [Features.md](Features.md) §2, MVP rows.

- Resume upload → storage → parsing job (Job Runner, §8.1) → structured extraction
- Skill/project/experience extraction, embedding generation into ChromaDB `resume_embeddings`
- Gap analysis against a target role

**Exit criteria:** upload a real PDF resume, see extracted skills/projects, request a gap analysis against a role, see missing skills + recommended difficulty.

---

## Module 4 — Interview Planning Data

**Scope:** [Features.md](Features.md) §3, MVP rows.

- `companies`, `roles`, `interview_templates`, `template_rounds` seeded via script (no admin UI yet, per Features.md)
- Seed at least 2–3 companies, a handful of roles, one template each with a realistic round plan
- Frontend: company/role/template selection flow

**Exit criteria:** a candidate can browse companies/roles and select a template that becomes the round plan for a new session.

---

## Module 5 — Core Interview Engine (Text Rounds)

**Scope:** [Features.md](Features.md) §4 MVP rows *except coding*, §7 (agents) MVP rows *except the coding path*.

- LangGraph graph: Supervisor, Question Generator, Knowledge Agent, Interview Agent, Evaluation Agent (technical/problem_solving only), Communication Agent, Difficulty Agent
- Postgres-backed checkpointing wired end to end
- Introduction, technical, behavioral, resume discussion rounds functional
- `POST /interview-sessions/{id}/answers` flow from API.md §4 fully working

**Exit criteria:** a candidate can run a full multi-round text-only interview session (no coding round in the template yet), see difficulty visibly change, and reach `status=completed`. This is the riskiest module — the whole multi-agent orchestration proves out here before coding execution adds complexity on top.

---

## Module 6 — Code Execution Subsystem + Coding Round

**Scope:** [Features.md](Features.md) §6, plus the coding portion of §4/§7.

- `CodeExecutor` protocol + `DockerSandboxExecutor` implementation with the security controls from Architecture.md §6
- `question_test_cases`, `code_submissions`, `code_submission_test_results` wired
- Async submit → job → grade → poll flow from API.md §5
- Evaluation Agent's coding path: computed correctness + LLM readability/optimization
- Start with Python + JavaScript only (per Features.md §6)

**Exit criteria:** a candidate can submit real code for a coding question, see it actually execute against sample + hidden test cases in an isolated sandbox, and get back a correctness score that is demonstrably tied to test results (not just plausible-sounding LLM text) plus readability/optimization feedback.

---

## Module 7 — Report Generator & Learning Roadmap

**Scope:** [Features.md](Features.md) §8, Learning Agent + Report Agent from §7.

- Report Agent aggregates `report_section_scores`, weak/strong areas, overall score
- Learning Agent produces `learning_roadmaps` / `roadmap_items`
- `GET /interview-sessions/{id}/report` and roadmap endpoints from API.md §6

**Exit criteria:** completing a full session (Modules 5+6) produces a real 5-section report with explanations and a roadmap the candidate can mark progress against.

---

## Module 8 — Progress Dashboard

**Scope:** [Features.md](Features.md) §9, MVP rows.

- `skill_progress`, `company_readiness`, `user_progress_snapshots` populated on report generation
- Dashboard endpoints from API.md §7 + frontend views (history, skill trends, company readiness)

**Exit criteria:** after 2+ completed sessions, the dashboard shows a real trend, not placeholder data.

---

## Module 9 — Hardening & Deployment

- Structured logging review, error handling audit, rate limiting on auth/interview endpoints
- CI (lint + typecheck + test on push)
- Production deployment topology decision (deferred intentionally in Architecture.md §9)
- Load-test the coding execution path specifically — it's the one subsystem with real resource cost per request

**Exit criteria:** the app runs reliably outside a developer's laptop.

---

## Later (post-MVP, tracked but not scheduled)

Pulled directly from the "Later" rows across [Features.md](Features.md): system design round rubric, recruiter/admin views, multi-resume versioning, resume rewrite suggestions, admin authoring UI, Judge0 backend swap, PDF export, shareable reports, cohort/placement-cell analytics.

---

*This roadmap is a living document — update it as modules complete or scope shifts, but don't skip a module's exit criteria to move faster. That's exactly the shortcut this project is explicitly trying to avoid.*
