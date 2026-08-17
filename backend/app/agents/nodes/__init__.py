"""One module per node/agent responsibility (Architecture.md §5.1, Module
5). Each function is a thin adapter between InterviewState and the
provider/policy layer — no node does its own Gemini SDK calls or its own
database access (see app/agents/state.py's module docstring and
app/services/interview/execution_service.py for why: nodes are pure
functions over state, Postgres reads/writes happen in the service, before
and after the graph runs).
"""
