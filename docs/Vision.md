# InterviewIQ AI — Vision

Status: **Approved direction — refine as the product learns**

---

## 1. Elevator Pitch

InterviewIQ AI is an AI Interview Coach, not an AI Interview Quiz. It conducts adaptive, multi-round technical interviews grounded in a candidate's actual resume, evaluates them with a team of specialized AI agents instead of one generic grader, executes their code for real instead of guessing whether it works, and turns every session into a concrete, prioritized plan for what to study next. It remembers every interview a candidate has taken and tracks whether they're actually getting better — at a specific skill, and for a specific company.

---

## 2. The Problem

| Existing interview-prep platforms | InterviewIQ AI |
|---|---|
| Same interview for everyone | Company + role + resume-aware question selection |
| Static question sets | Question Generator Agent produces questions grounded in RAG (company patterns + topic knowledge base) |
| Generic, one-line feedback | 5-dimension scored report (Technical, Coding, Communication, Problem Solving, Confidence), every score with a written explanation |
| Fixed difficulty | Difficulty Agent recalculates after every single answer |
| No follow-up questions | Interview Agent maintains conversational context within a round |
| No memory between sessions | Every session, skill trend, and company-readiness score persists and compounds over time |
| No AI mentor after the interview | Learning Agent generates a prioritized, topic-level roadmap from the candidate's actual weak areas |
| Resume ignored | Resume Intelligence extracts skills/projects/gaps and feeds them directly into question selection and difficulty |
| Coding and behavioral rounds live in separate tools | One session, one continuous multi-round flow, one unified report |
| No real progress tracking | Progress Dashboard: skill growth, weak topics, company readiness, trend over time |
| Coding correctness is often just an LLM guess | Candidate code actually executes against test cases in a sandbox; correctness is computed, not guessed (see [Architecture.md](Architecture.md) §5.4, §6) |

---

## 3. Target Users

| User | What they get |
|---|---|
| College students / job seekers | Realistic, adaptive practice against real companies/roles, with a study plan instead of just a score |
| Universities / placement cells | Aggregate visibility into cohort readiness by company/role (future: recruiter/admin views) |
| Recruiters | A consistent, explainable evaluation rubric instead of ad-hoc screening |
| EdTech companies | An embeddable interview-intelligence engine rather than a static question bank |

MVP is scoped to the first row (individual candidates). Placement-cell/recruiter aggregate views are explicitly a later phase — see [Roadmap.md](Roadmap.md).

---

## 4. Product Principles

1. **Every score has a reason.** No number appears in a report without an explanation attached to it — enforced at the database level ([Database.md](Database.md) §6–7), not just a prompting convention.
2. **Difficulty is earned, not chosen once.** The candidate doesn't pick "hard mode" — the Difficulty Agent moves them there based on demonstrated performance, every turn.
3. **Correctness is computed, not guessed.** Code executes in a real sandbox against real test cases; the LLM's job is to explain results and judge what execution can't measure (readability, optimization) — never to decide if code "works."
4. **The resume is an input, not a decoration.** Extracted skills and gaps actively shape which questions get asked and at what difficulty.
5. **Interviews are memory, not one-offs.** Every session updates a durable skill/company-readiness profile the candidate can see growing.

---

## 5. Explicit Non-Goals (MVP)

Staying honest about scope keeps the architecture from bloating before it's earned:

- **Not** a live video/audio proctoring system — text/code input only for MVP; voice is a future consideration, not assumed in the current architecture.
- **Not** an ATS or recruiter applicant-tracking workflow — recruiter-facing features are a later phase.
- **Not** a general-purpose coding judge for arbitrary contest problems — the coding round is interview-shaped (a handful of test cases per question, sandboxed execution), not a full competitive-programming judge.
- **Not** multi-tenant/white-label from day one — the schema doesn't currently model organizations; revisit if EdTech/university use cases move from "target user" to "committed customer."

---

## 6. Success Signals (directional, not KPIs yet)

- Candidates complete full sessions (all planned rounds) rather than abandoning mid-interview.
- Repeat usage: a candidate takes a second interview for the same company/role and their `company_readiness.readiness_score` measurably moves.
- Report explanations are specific enough that a candidate can act on them without re-reading the whole transcript.

---

*Next: [Features.md](Features.md) — concrete feature scope per module, MVP vs. later.*
