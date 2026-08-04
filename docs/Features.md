# InterviewIQ AI — Features

Status: **Scoped — MVP vs. Later marked per feature**

Organized by the modules defined in [Architecture.md](Architecture.md). Each feature notes the schema ([Database.md](Database.md)) and/or agent it depends on, so scope and data model stay traceable to each other.

Legend: **MVP** = required for first working product · **Later** = designed for, not built yet

---

## 1. Authentication

| Feature | Scope | Depends on |
|---|---|---|
| Email/password signup + login | MVP | `users` |
| JWT access + refresh token rotation | MVP | `refresh_tokens` |
| Google OAuth login | MVP | `users.auth_provider/google_id` |
| Email verification | MVP | `users.is_verified` |
| User profile view/edit | MVP | `users` |
| Password reset flow | MVP | `users` |
| Role-based access (recruiter/admin views) | Later | `users.role` (column exists now, no UI/authorization logic yet) |

---

## 2. Resume Intelligence

| Feature | Scope | Depends on |
|---|---|---|
| Upload resume (PDF) | MVP | `resumes` |
| Parse text + structured extraction (skills, projects, experience) | MVP | `resume_skills`, `resume_projects`, `resume_experience` |
| Embed resume chunks for similarity search | MVP | ChromaDB `resume_embeddings` |
| Gap analysis against a target role | MVP | `resume_gap_analysis` |
| Recommended starting difficulty from gap analysis | MVP | feeds `interview_sessions.current_difficulty` at session start |
| Multi-resume support (versioning per user) | Later | schema already allows multiple `resumes` rows per user |
| Resume improvement suggestions (rewrite bullet points) | Later | net-new agent, not scoped yet |

---

## 3. Interview Planner

| Feature | Scope | Depends on |
|---|---|---|
| Browse companies + roles | MVP | `companies`, `roles` |
| Select an interview template (e.g. "Onsite Loop" vs "Phone Screen") | MVP | `interview_templates`, `template_rounds` |
| Manual difficulty override at session start | MVP | `interview_sessions.current_difficulty` |
| Admin authoring UI for companies/roles/templates | Later | seed via script for MVP; UI is a later module |
| Community-contributed / crowdsourced templates | Later | — |

---

## 4. AI Interview Engine

| Feature | Scope | Depends on |
|---|---|---|
| Introduction round | MVP | `interview_rounds`, Interview Agent |
| Technical round | MVP | Question Generator + Knowledge Agent |
| Coding round with real execution | MVP | `question_test_cases`, `code_submissions`, Code Execution Adapter |
| Behavioral round | MVP | Question Generator (STAR-aware prompting) |
| System design round | Later | question type exists (`questions.question_type = system_design`); no dedicated evaluation rubric yet — grouped under generic technical evaluation for MVP |
| Resume discussion round | MVP | Question Generator using `resume_context` |
| Final questions ("ask us anything") round | Later | conversational only, no scoring — low priority for MVP |
| Follow-up questions within a round | MVP | Interview Agent, conversational history in graph state |
| Session pause/resume | MVP | LangGraph checkpointing makes this close to free — exposing it in the UI is the actual scope item |

---

## 5. Adaptive Difficulty

| Feature | Scope | Depends on |
|---|---|---|
| Per-answer difficulty recalculation | MVP | Difficulty Agent, `answer_evaluations.difficulty_signal` |
| Resume-informed starting difficulty | MVP | `resume_gap_analysis.recommended_difficulty` |
| Difficulty trend visible to candidate mid-interview | Later | UI-only addition once MVP flow is stable |
| Per-topic (not just global) difficulty modeling | Later | would require a `topic_difficulty_state` structure not yet in graph state |

---

## 6. Coding Evaluation

| Feature | Scope | Depends on |
|---|---|---|
| Real sandboxed code execution against test cases | MVP | `question_test_cases`, `code_submissions`, `code_submission_test_results`, `DockerSandboxExecutor` |
| "Run" against sample cases before final "Submit" (multi-attempt, only final graded) | MVP | `code_submissions.attempt_no/is_final` |
| Correctness score computed from execution (not LLM) | MVP | `coding_evaluations.correctness_score` |
| Readability + optimization scoring (LLM) | MVP | `coding_evaluations.readability_score/optimization_score` |
| Time/space complexity estimate | MVP | `coding_evaluations.time_complexity/space_complexity` |
| Multi-language support | MVP (start with Python + JavaScript, expand later) | `code_submissions.language` is free text already |
| Judge0 backend swap | Later | `CodeExecutor` interface designed for this from day one |
| Live syntax/error hints while typing | Later | pure frontend/Monaco feature, no backend dependency |

---

## 7. Multi-Agent Evaluation

| Feature | Scope | Depends on |
|---|---|---|
| Supervisor-orchestrated LangGraph | MVP | see [Architecture.md](Architecture.md) §5 |
| Question Generator + Knowledge Agent (RAG) | MVP | ChromaDB `question_bank`, `knowledge_base` |
| Evaluation Agent (technical, problem solving, coding) | MVP | `answer_evaluations`, `coding_evaluations` |
| Communication Agent (communication, confidence) | MVP | `answer_evaluations` |
| Difficulty Agent | MVP | see above |
| Learning Agent | MVP | `learning_roadmaps`, `roadmap_items` |
| Report Agent | MVP | `interview_reports`, `report_section_scores` |
| Agent self-critique / re-evaluation pass | Later | quality improvement, not launch-blocking |

---

## 8. Report Generator

| Feature | Scope | Depends on |
|---|---|---|
| 5-section scored report (Technical, Coding, Communication, Problem Solving, Confidence), each with explanation | MVP | `report_section_scores` |
| Overall score with explanation | MVP | `interview_reports.overall_score/overall_explanation` |
| Weak areas with evidence | MVP | `report_weak_areas` |
| Strong areas with evidence | MVP | `report_strong_areas` |
| Learning roadmap (prioritized topics + resources) | MVP | `learning_roadmaps`, `roadmap_items` |
| Exportable PDF report | Later | rendering-only addition once report data model is stable |
| Shareable report link (for recruiters) | Later | needs an access-control decision first |

---

## 9. Progress Dashboard

| Feature | Scope | Depends on |
|---|---|---|
| Interview history list | MVP | `interview_sessions`, `interview_reports` |
| Skill growth over time | MVP | `skill_progress` |
| Weak topics aggregated across sessions | MVP | derived from `report_weak_areas` across a user's reports |
| Company readiness score | MVP | `company_readiness` |
| Trend charts (score over time) | MVP | `user_progress_snapshots` |
| Cohort/placement-cell aggregate analytics | Later | needs an organization/cohort model not in the current schema |
| Recruiter-facing candidate comparison view | Later | needs access-control + the above cohort model |

---

*Next: [API.md](API.md) — the REST surface that implements the MVP rows above.*
