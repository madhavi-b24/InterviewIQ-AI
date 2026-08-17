"""Interview Engine's LLM-backed seam (Module 5) — question generation,
follow-ups, and per-answer evaluation. Mirrors
app/services/resume_intelligence/'s package shape exactly: a Protocol
(provider.py), the structured-output contracts (schemas.py), a real Gemini
implementation (gemini_provider.py), a deterministic fake for tests
(fake_provider.py), and config-driven selection (factories.py).
"""
