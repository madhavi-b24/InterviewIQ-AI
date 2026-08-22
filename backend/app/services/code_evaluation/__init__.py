"""Code Evaluation's LLM-backed seam (Module 6) — judges what execution
can't measure (readability, optimization, edge-case handling, complexity
estimate) for a *final* code submission only. Mirrors
app/services/interview_intelligence/'s package shape exactly: a Protocol
(provider.py), the structured-output contract (schemas.py), a real Gemini
implementation (gemini_provider.py), a deterministic fake for tests
(fake_provider.py), and config-driven selection (factories.py).

correctness_score is never produced here — it's computed from
code_submission_test_results before this provider is ever called (module
§10: "the LLM must never override the execution result").
"""
