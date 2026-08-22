# InterviewIQ AI — API Reference

Status: **Draft surface for MVP scope (see [Features.md](Features.md))**

Base URL: `/api/v1`. All authenticated routes require `Authorization: Bearer <access_token>`. This document defines the contract; implementation happens in a later module.

---

## 0. Conventions

- **Auth**: JWT access token (short-lived) in the `Authorization` header; refresh via `POST /auth/refresh` using an httpOnly refresh cookie or body token (finalized in the Auth module).
- **Errors**: uniform envelope —
  ```json
  { "error": { "code": "RESOURCE_NOT_FOUND", "message": "Interview session not found", "details": {} } }
  ```
- **Pagination**: cursor-free offset pagination for MVP — `?page=1&page_size=20`, response includes `{ "items": [...], "total": N, "page": 1, "page_size": 20 }`.
- **IDs**: all resource IDs are UUIDs, matching [Database.md](Database.md).
- **Scores**: always returned as `{ "score": number, "explanation": string }` pairs, never a bare number — mirrors the schema convention.

---

## 1. Auth

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/auth/register` | Email/password signup | none |
| POST | `/auth/login` | Email/password login → access + refresh token | none |
| POST | `/auth/refresh` | Rotate refresh token → new access token | refresh token |
| POST | `/auth/logout` | Revoke current refresh token | required |
| GET | `/auth/google/login` | Redirect to Google OAuth consent | none |
| GET | `/auth/google/callback` | OAuth callback → issues tokens | none |
| POST | `/auth/verify-email` | Confirm email via token | none |
| POST | `/auth/password-reset/request` | Send reset email | none |
| POST | `/auth/password-reset/confirm` | Set new password via token | none |
| GET | `/users/me` | Current user profile | required |
| PATCH | `/users/me` | Update profile (name, avatar) | required |

---

## 2. Resumes

**Status: implemented in Module 3** — see [backend/README.md](../backend/README.md)'s "Resume Intelligence (Module 3)" section for the full pipeline/design writeup.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/resumes` | Upload resume (`multipart/form-data`, field name `file`) → `parsed_status=pending`, kicks off the background processing job | required |
| GET | `/resumes` | List current user's resumes (all versions, newest first) | required |
| GET | `/resumes/{resume_id}` | Resume detail incl. `parsed_status`, `processing_error`, `is_active` | required |
| GET | `/resumes/{resume_id}/analysis` | Structured extraction: education, skills, projects, experience, certifications, achievements — each item includes an `evidence` field | required |
| POST | `/resumes/{resume_id}/gap-analysis` | Body: `{ "role_key": "backend_engineer" }` → role-readiness + explainable difficulty recommendation, returns the (single, replaced-on-recall) `resume_gap_analysis` row | required |
| DELETE | `/resumes/{resume_id}` | Delete a resume version. If it was the active one, the next-most-recent resume is promoted to active | required |

**Deviation from this document's original draft:** `POST /resumes/{resume_id}/gap-analysis`'s body is `{ "role_key": string }`, not `{ "target_role_id": uuid }` — Module 4 (`companies`/`roles`) isn't built yet, so there is no `roles` row to reference. `role_key` selects one of Module 3's internal InterviewIQ competency profiles (`software_engineer`, `backend_engineer`, `ai_engineer`, `ml_engineer`, `data_engineer` — see backend/README.md). `target_role_id` is still accepted in the request body for forward-compatibility but is not resolved to anything yet.

Every path above enforces resource ownership — a resume ID belonging to another user resolves as `404 RESOURCE_NOT_FOUND` on every method, never `403`, so a client can't distinguish "not yours" from "doesn't exist."

Resume parsing runs through the Job Runner (§8.1 of Architecture.md); `GET /resumes/{id}` is the poll target until `parsed_status = done` (or `failed`, with `processing_error` set — see backend/README.md for the state model and what "failed after partial success" means).

---

## 3. Interview Planning

**Status: implemented in Module 4** — companies/roles/templates are read-only, shared catalog data (not ownership-scoped); every route still requires authentication. See [backend/README.md](../backend/README.md)'s "Interview Planner (Module 4)" section for the full design writeup.

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/companies` | List active companies | required |
| GET | `/companies/{company_id}/roles` | Roles offered at a company (404 if the company is missing/inactive) | required |
| GET | `/roles` | List generic (company-agnostic) + all roles, filterable by `?level=` | required |
| GET | `/roles/{role_id}/templates` | Interview templates available for a role, filterable by `?company_id=` and `?mode=` | required |
| GET | `/templates/{template_id}` | Template detail including ordered `template_rounds` | required |

**Companies are InterviewIQ preparation profiles, not official company hiring-process specifications.** Each `CompanyOut.interview_style_notes` field says so explicitly (e.g. "InterviewIQ's preparation profile for Google-style loops, based on publicly discussed patterns... Not Google's official interview process and not affiliated with or endorsed by Google.") — this applies to every seeded company (Google, Microsoft, Amazon, Atlassian, OpenAI). Only `general` (company-agnostic) makes no company-likeness claim at all.

Inactive companies/roles/templates are excluded from every listing above and from `POST /interview-sessions` (§4) — `is_active` is how a catalog entry is retired without deleting history that existing interview sessions still reference (no soft-delete pattern needed here, matching [Database.md](Database.md) §0's "no soft-delete by default" convention).

---

## 4. Interview Sessions

**Status: fully implemented.** The planning subset (creation, listing, retrieval, plan snapshot) is Module 4; `/start`, `/current-turn`, `/answers`, `/abandon` are Module 5, backed by the LangGraph engine (Architecture.md §5). Coding rounds execute for real as of Module 6 — see §5 below for the coding-problem/code-submission endpoints, nested under this same `/interview-sessions/{id}` resource.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/interview-sessions` | Create an immutable interview plan. Body: `{ role_id, template_id, company_id?, mode?, difficulty?, resume_id? }` (see deviation note below) | required |
| GET | `/interview-sessions` | List current user's sessions, filterable by `?status=` | required |
| GET | `/interview-sessions/{id}` | Session detail (status, current round, current/starting/requested difficulty) | required |
| GET | `/interview-sessions/{id}/plan` | The full immutable plan snapshot: company/role/template labels, ordered rounds, difficulty resolution + reasons, resume-derived personalization (if any) | required |
| POST | `/interview-sessions/{id}/start` | *(Module 5)* `not_started → in_progress`; the Question Generator Agent produces the first question | required |
| GET | `/interview-sessions/{id}/current-turn` | *(Module 5)* Current pending question + round/difficulty context — pure read, zero LLM calls, safe to poll | required |
| POST | `/interview-sessions/{id}/answers` | *(Module 5)* Submit a text answer to a specific question — synchronous, returns evaluation + next question (§5.3 of Architecture.md) | required |
| POST | `/interview-sessions/{id}/abandon` | *(Module 5)* Mark session `abandoned` — only from `not_started`/`in_progress` | required |

**Deviations from this document's original draft body**, all documented inline in the relevant schema module:
- `difficulty_override` → `difficulty`, an enum of `easy`/`medium`/`hard`/`auto` (default `auto`) rather than a bare optional override (`app/schemas/interview.py`). `auto` resolves deterministically from the selected resume's already-computed `resume_gap_analysis.recommended_difficulty` (Module 3) when one is available and matches, or from the documented safe default (`medium`) otherwise — never via an LLM call. Both the raw request (`requested_difficulty`) and the resolved value (`starting_difficulty`) are persisted, distinct from `current_difficulty` (Module 5's Difficulty Agent mutates only this third field during the interview).
- Added optional `mode` (`full_mock`/`technical_only`/`coding_only`/`behavioral_only`/`resume_deep_dive`) — inherited from the selected template if omitted, and must match the template's own mode exactly if given.
- `resume_id` is optional and, if omitted, falls back to the candidate's active analyzed resume; required when the mode is `resume_deep_dive` or the template includes a `resume_discussion` round.
- **`POST .../answers`'s body is `{ question_id, answer_text }`** (`app/schemas/interview_turn.py::AnswerSubmitRequest`) — requiring `question_id` explicitly, rather than implicitly "the current question," makes staleness/idempotency unambiguous: a request naming a question that isn't the session's current pending one is a clean `409 STALE_QUESTION_ID`, and a request naming an already-answered question replays the recorded result rather than erroring or re-evaluating (module §5, §22 — "duplicate answer retry does not duplicate turns").
- **`next` has only two shapes, not three** — `{"type":"question","question":{...}}` or `{"type":"session_complete"}` (no `report_id` — Module 7's report generator doesn't exist yet, so it's omitted rather than fabricated). There is no separate `"round_complete"` pause state: the engine always eagerly generates the next round's opening question in the same turn, so the client never needs an extra round-trip just to learn what round it's now in — `GET .../current-turn` still reports the current round if the client wants to display a "round complete" transition.

Every path above enforces resource ownership the same way §2 Resumes does — a session ID belonging to another user resolves as `404 RESOURCE_NOT_FOUND` (specifically `code=INTERVIEW_NOT_FOUND`) on every method, never `403`.

### `POST /interview-sessions/{id}/start` — response shape

```json
{
  "interview_id": "uuid",
  "status": "in_progress",
  "current_round": "introduction",
  "current_difficulty": "medium",
  "question": { "id": "uuid", "question_text": "...", "topic": "...", "difficulty": "medium", "round_type": "introduction", "parent_question_id": null }
}
```

### `GET /interview-sessions/{id}/current-turn` — response shape

```json
{
  "interview_id": "uuid",
  "status": "in_progress",
  "current_round": "technical",
  "current_difficulty": "hard",
  "question": { "id": "uuid", "question_text": "...", "topic": "...", "difficulty": "hard", "round_type": "technical", "parent_question_id": null },
  "interview_complete": false
}
```

### `POST /interview-sessions/{id}/answers` — response shape

```json
{
  "interview_id": "uuid",
  "status": "in_progress",
  "evaluation": {
    "technical": { "score": 82, "explanation": "..." },
    "problem_solving": { "score": 75, "explanation": "..." },
    "communication": { "score": 90, "explanation": "..." },
    "confidence": { "score": 70, "explanation": "..." },
    "difficulty_signal": "increase"
  },
  "previous_difficulty": "medium",
  "current_difficulty": "hard",
  "next": { "type": "question", "question": { "...": "..." } }
  // OR "next": { "type": "session_complete" }
}
```

`evaluation.confidence` is the observable directness/assertiveness of the candidate's *phrasing* (hedging vs. decisive language) — never a psychological or personality inference (module §9, §11's explicit prohibition; see `app/services/interview_intelligence/schemas.py::CommunicationEvaluation`'s docstring). No field in any Module 5 response carries internal agent reasoning/chain-of-thought (module §20) — only scores, explanations, and structured flags a candidate would find useful.

### `POST /interview-sessions/{id}/abandon` — response shape

```json
{ "interview_id": "uuid", "status": "abandoned", "completed_at": "2026-01-01T00:00:00Z" }
```

`409 INVALID_STATE_TRANSITION` if the interview is already `completed`/`abandoned`.

---

## 5. Coding Rounds — Problem Retrieval & Code Submissions (Module 6)

**Status: implemented.** Matches the async Run-vs-Submit flow in Architecture.md §5.4, with two documented deviations from this section's original sketch (both explained inline below): every endpoint is nested under `/interview-sessions/{id}`, not top-level `/code-submissions/{id}`, for the same ownership-enforcement consistency every other sub-resource in this API follows; and resubmitting after a final attempt **replays the existing final submission** (idempotent, matching every other duplicate-request case in this API — module §22) rather than erroring.

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/interview-sessions/{id}/questions/{question_id}/coding-problem` | The candidate-facing problem statement: title, description, difficulty, constraints, expected complexity, starter code, supported languages, and **sample test cases only** — hidden test input/expected_output never appear here or anywhere else (module §8) | required |
| POST | `/interview-sessions/{id}/questions/{question_id}/code-submissions` | Body: `{ language, source_code, is_final }` (default `is_final: false`) → `202 Accepted`, a `CodeSubmissionOut` reflecting the just-created (still `queued`) attempt — see the polling note below | required |
| GET | `/interview-sessions/{id}/questions/{question_id}/code-submissions` | List all attempts for this question, most recent attempt_no first — powers an attempt-history view | required |
| GET | `/interview-sessions/{id}/code-submissions/{submission_id}` | Poll status/result for one attempt | required |
| GET | `/interview-sessions/{id}/code-submissions/{submission_id}/evaluation` | The final attempt's code-quality evaluation — `null` until `is_final=true` and grading has completed; always `null` for a non-final attempt | required |

Every call creates a new **attempt** (`attempt_no` assigned server-side); `is_final` distinguishes a "Run" from the one "Submit" that gets graded. Execution and (for a final attempt) LLM code-quality grading run in a background job (module §17 — never inline in the request), so **the POST response always reflects the pre-grading `queued` state, even though — under this project's synchronous test harness — the job may have already finished by the time the HTTP call returns.** A real client polls `GET .../code-submissions/{id}` for the graded result, same as `GET .../current-turn` polls text-round state.

- `is_final: false` ("Run") — executes against sample test cases only, no LLM call, fast.
- `is_final: true` ("Submit") — executes against **all** test cases (sample + hidden) and, once execution succeeds, triggers code-quality evaluation. A question can have at most one final attempt (`code_submissions` partial unique index on `(answer_id) WHERE is_final`, the real backstop for a concurrent double-Submit — module §22); calling Submit again after a final attempt exists **replays that same submission** (same `id`, same `202`) rather than creating a second one or erroring — unless it's still mid-grading, which is a `409 FINAL_SUBMISSION_IN_PROGRESS`. Once a final submission genuinely finishes grading (a real verdict — success, partial, or one of the granular failure statuses below), the interview automatically advances to its next round; a Run never does.
- `422 UNSUPPORTED_LANGUAGE` if `language` isn't one of the problem's `supported_languages` (Python, Java, C++ only for MVP — module §6's explicit instruction, a deliberate deviation from Features.md's stale "Python + JavaScript" MVP language list, corrected there too).

### `GET /interview-sessions/{id}/code-submissions/{submission_id}` — response shape

```json
{
  "id": "uuid",
  "question_id": "uuid",
  "attempt_no": 3,
  "is_final": true,
  "language": "python",
  "execution_status": "partial",
  "passed_test_count": 8,
  "total_test_count": 10,
  "total_runtime_ms": 94,
  "error_message": null,
  "sample_test_results": [
    { "input": "4\n2 7 11 15\n9\n", "expected_output": "0 1", "actual_output": "0 1", "passed": true, "runtime_ms": 12, "stderr": null }
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "graded_at": "2026-01-01T00:00:05Z"
}
```

`execution_status` progresses `queued → running →` one of `success | partial | compile_error | runtime_error | timeout | output_limit | error` (`error` is a genuine sandbox/provider infrastructure failure, never a candidate-code outcome — see Database.md §5's `code_submissions` note on when `is_final` gets released back to `false` for exactly this status). `sample_test_results` only ever itemizes the **sample** subset of whatever ran — for a Run, that's everything; for a Submit, hidden test outcomes are folded into `passed_test_count`/`total_test_count` only, never itemized individually (module §8).

### `GET /interview-sessions/{id}/code-submissions/{submission_id}/evaluation` — response shape

```json
{
  "correctness_score": 80.0,
  "correctness_explanation": "8/10 test cases passed (weighted).",
  "readability_score": 85.0,
  "readability_explanation": "...",
  "optimization_score": 60.0,
  "optimization_explanation": "O(n²) approach; O(n log n) possible via sorting first.",
  "edge_case_score": 70.0,
  "edge_case_explanation": "...",
  "time_complexity": "O(n²)",
  "space_complexity": "O(1)",
  "overall_code_score": 74.25,
  "strengths": ["Clear variable names", "Handles the empty-input case explicitly"],
  "weaknesses": ["Nested loop is more expensive than necessary"],
  "recommendations": ["Sort first, then use two pointers for O(n log n)"]
}
```

`correctness_score` and `overall_code_score` are both **computed, never LLM-guessed** (Database.md §6's `coding_evaluations` note); every other field is `CodeEvaluationProvider`'s judgment of qualities execution can't measure. No chain-of-thought ever appears here (module §20) — only scores, short evidence-citing explanations, and concrete, specific list items.

---

## 6. Reports

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/interview-sessions/{id}/report` | Full report for a completed session | required |
| GET | `/reports/{report_id}/roadmap` | Learning roadmap generated from this report | required |
| PATCH | `/roadmap-items/{id}` | Mark a roadmap item complete (`is_completed`) | required |

### `GET /interview-sessions/{id}/report` — response shape

```json
{
  "overall": { "score": 78, "explanation": "..." },
  "sections": {
    "technical": { "score": 80, "explanation": "..." },
    "coding": { "score": 75, "explanation": "..." },
    "communication": { "score": 88, "explanation": "..." },
    "problem_solving": { "score": 70, "explanation": "..." },
    "confidence": { "score": 82, "explanation": "..." }
  },
  "weak_areas": [{ "topic": "Dynamic Programming", "severity": "high", "evidence": "..." }],
  "strong_areas": [{ "topic": "SQL joins", "evidence": "..." }],
  "summary": "..."
}
```

Note `sections` only includes keys for sections that actually have a `report_section_scores` row — a session without a coding round has no `coding` key, not a null one.

---

## 7. Progress Dashboard

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/dashboard/overview` | Summary: interviews completed, avg overall score trend | required |
| GET | `/dashboard/skills` | `skill_progress` list with trend | required |
| GET | `/dashboard/company-readiness` | `company_readiness` per company the user has interviewed for | required |
| GET | `/dashboard/history` | Paginated session history with linked report summaries | required |

---

*Next: [Roadmap.md](Roadmap.md) — the module build order that implements this surface incrementally.*
