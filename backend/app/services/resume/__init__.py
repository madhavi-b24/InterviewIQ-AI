"""Resume Intelligence domain services — Module 3.

Deterministic pipeline stages (PDF validation/extraction, section
detection, skill normalization, role-readiness/difficulty scoring) live
here as plain functions/classes with no FastAPI or SQLAlchemy imports, so
they're unit-testable in isolation. The LLM-backed stage lives in the
sibling app/services/resume_intelligence/ package behind its own
provider abstraction — see that package's docstring for why it's split
out separately.
"""
