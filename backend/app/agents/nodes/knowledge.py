"""Knowledge Agent (Architecture.md §5.1, module §10) — MVP implementation.

Deliberately **not an LLM call and not a graph node**. It assembles
grounding CONTEXT for whichever agent needs it (Evaluation, Question
Generator, Interview Agent) — it does not itself verify truth or generate
text. Two reasons this is the right MVP scope, documented rather than
silently simplified:

1. "Do not let the Knowledge Agent blindly hallucinate authoritative
   facts" (module §10) — the safest way to guarantee that for MVP is to
   not make it an LLM call at all. It only ever echoes back information
   that is already known to be true: the candidate's own resume evidence
   (already evidence-tagged by Module 3) and a small, curated,
   already-reviewed set of role-topic hints (role_profiles.json, already
   used by Module 3 for readiness scoring).
2. A real RAG lookup against `resume_embeddings`/a knowledge base isn't
   viable right now regardless — ChromaDB embedding indexing is currently
   broken against the real Gemini API (a documented, separate TODO from
   this session; see backend/README.md's "Known limitations").

`retrieve()` is the seam: a future real implementation (querying
ChromaDB/a curated fact store) can satisfy this exact same signature
without any caller changing. It's a plain function (not a Protocol) since
there's exactly one implementation today and no config-driven swap is
needed yet — promoting it to a Protocol is a mechanical follow-up once a
second implementation exists.
"""

from app.agents.state import PersonalizationContextState


def retrieve(
    *, topic: str | None, role_key: str | None, personalization: PersonalizationContextState | None
) -> str:
    """Returns a short grounding text block for the current topic/role —
    never more than a handful of lines, never a document dump (module §3's
    "do not put enormous duplicated documents into graph state" applies
    here too, even though this text is prompt-only and not persisted to
    graph state as-is).
    """
    if personalization is None:
        return ""

    lines: list[str] = []
    if personalization["skills"]:
        lines.append("Candidate's evidenced skills: " + ", ".join(personalization["skills"][:12]))
    if personalization["project_titles"]:
        lines.append("Candidate's projects: " + ", ".join(personalization["project_titles"][:5]))
    if topic:
        matching_evidence = [
            snippet
            for snippet in personalization["evidence_snippets"]
            if topic.lower() in snippet.lower()
        ]
        for snippet in matching_evidence[:3]:
            lines.append(f"Resume evidence for {topic!r}: {snippet}")

    return "\n".join(lines)
