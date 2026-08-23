"""Report Generation's LLM-backed seam (Module 7) — writes the narrative
half of a session report: section/overall explanations, `summary_text`,
weak/strong-area evidence text, and learning-roadmap resource content.
Mirrors app/services/code_evaluation/'s package shape exactly: a Protocol
(provider.py), the structured-output contract (schemas.py), a real Gemini
implementation (gemini_provider.py), a deterministic fake for tests
(fake_provider.py), and config-driven selection (factories.py).

Every score in a report — section scores, overall score, weak-area
severity — is computed deterministically in app/agents/policy.py before
this provider is ever called (module §11/§20's rule, extended from
Module 6's correctness/overall_code_score: "the LLM must never freely
decide a headline number"). This provider is given only the already
-computed scores plus per-answer explanation strings as grounding
context — never asked to produce or revise a score itself.
"""
