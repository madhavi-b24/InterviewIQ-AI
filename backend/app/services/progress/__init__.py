"""ProgressService — Module 8's post-report progress-aggregation use case.
Mirrors app/services/report/'s package shape: one file, one service
class, plain repository calls. No provider package here at all (unlike
every module since 5) — every number this service produces is a
deterministic aggregate or a straight read of an already-scored Module 7
value; nothing here calls Gemini or any other LLM.
"""
