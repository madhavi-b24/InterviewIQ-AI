"""ResumeIntelligenceProvider — the LLM-backed structured-extraction seam
(module §8), split out from app/services/resume/ (the deterministic
pipeline stages) because this is the one piece of the pipeline that talks
to an external model and needs its own timeout/retry/failure semantics.

    ResumeIntelligenceProvider (provider.py)  -- Protocol
      |-- GeminiResumeIntelligenceProvider (gemini_provider.py)  -- real
      `-- FakeResumeIntelligenceProvider (fake_provider.py)      -- tests only,
          wired via app.dependency_overrides, never by config (see
          Settings.RESUME_INTELLIGENCE_PROVIDER's docstring)

ResumeService depends only on the Protocol, never on google.genai directly.
"""
