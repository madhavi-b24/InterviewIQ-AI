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

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/resumes` | Upload resume (`multipart/form-data`) → `parsed_status=pending`, kicks off parsing job | required |
| GET | `/resumes` | List current user's resumes | required |
| GET | `/resumes/{resume_id}` | Resume detail incl. `parsed_status` | required |
| GET | `/resumes/{resume_id}/analysis` | Extracted skills, projects, experience | required |
| POST | `/resumes/{resume_id}/gap-analysis` | Body: `{ "target_role_id": uuid }` → runs gap analysis, returns `resume_gap_analysis` | required |

Resume parsing runs through the Job Runner (§8.1 of Architecture.md); `GET /resumes/{id}` is the poll target until `parsed_status = done`.

---

## 3. Interview Planning

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/companies` | List companies | required |
| GET | `/companies/{company_id}/roles` | Roles offered at a company | required |
| GET | `/roles` | List generic (company-agnostic) + all roles, filterable by `?level=` | required |
| GET | `/roles/{role_id}/templates` | Interview templates available for a role (optionally filter `?company_id=`) | required |
| GET | `/templates/{template_id}` | Template detail including ordered `template_rounds` | required |

---

## 4. Interview Sessions

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/interview-sessions` | Create a session. Body: `{ resume_id, company_id?, role_id, template_id, difficulty_override? }` | required |
| GET | `/interview-sessions` | List current user's sessions, filterable by `?status=` | required |
| GET | `/interview-sessions/{id}` | Session detail (status, current round, current difficulty) | required |
| POST | `/interview-sessions/{id}/start` | Transitions `not_started → in_progress`, Supervisor emits the first question | required |
| GET | `/interview-sessions/{id}/current-turn` | Current question + round context (what the candidate should see right now) | required |
| POST | `/interview-sessions/{id}/answers` | Submit a text answer to the current question — synchronous, returns evaluation + next question (§5.3 of Architecture.md) | required |
| POST | `/interview-sessions/{id}/abandon` | Mark session `abandoned` | required |

### `POST /interview-sessions/{id}/answers` — response shape

```json
{
  "evaluation": {
    "technical": { "score": 82, "explanation": "..." },
    "problem_solving": { "score": 75, "explanation": "..." },
    "communication": { "score": 90, "explanation": "..." },
    "confidence": { "score": 70, "explanation": "..." }
  },
  "difficulty_signal": "increase",
  "next": { "type": "question", "question": { "...": "..." } }
  // OR "next": { "type": "round_complete" } / { "type": "session_complete", "report_id": "..." }
}
```

---

## 5. Coding Submissions (Asynchronous, Multi-Attempt)

Matches the async Run-vs-Submit flow in Architecture.md §5.4. Every call creates a new **attempt** (`attempt_no` assigned server-side); `is_final` distinguishes a "Run" from the one "Submit" that gets graded.

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/interview-sessions/{id}/code-submissions` | Body: `{ language, source_code, is_final }` (default `is_final: false`) → `202 Accepted { submission_id, attempt_no, is_final }` | required |
| GET | `/code-submissions/{id}` | Poll status/result for one attempt | required |
| GET | `/interview-sessions/{id}/questions/{question_id}/code-submissions` | List all attempts for this question, most recent first — powers an attempt-history view | required |

- `is_final: false` ("Run") — executes against sample test cases only, no LLM call, fast. Response never includes an `evaluation` block.
- `is_final: true` ("Submit") — executes against **all** test cases (sample + hidden) and triggers the Evaluation Agent. A question can have at most one final attempt (`code_submissions` partial unique index on `(answer_id) WHERE is_final`); resubmitting after a final attempt is rejected with `409 SUBMISSION_ALREADY_FINALIZED`.

### `GET /code-submissions/{id}` — response shape

```json
{
  "id": "uuid",
  "attempt_no": 3,
  "is_final": true,
  "execution_status": "success",
  "passed_test_count": 8,
  "total_test_count": 10,
  "test_results": [
    { "sequence_no": 1, "passed": true, "runtime_ms": 12, "is_sample": true }
  ],
  "evaluation": {
    "coding": {
      "correctness": { "score": 80, "explanation": "8/10 test cases passed; fails on empty-array edge case." },
      "readability": { "score": 85, "explanation": "..." },
      "optimization": { "score": 60, "explanation": "O(n²) approach; O(n log n) possible via sorting first." }
    }
  }
}
```

`execution_status` progresses `queued → running → success|partial|error|timeout`. `evaluation` is only present when `is_final = true` and grading has completed. For non-final attempts, only sample (`is_sample = true`) test results are ever returned; a final attempt's response includes pass/fail + timing for hidden cases too, but never their input/expected output.

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
