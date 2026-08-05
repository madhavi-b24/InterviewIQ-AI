"""Skill normalization (module §7): "JS" -> "JavaScript", "Postgres" ->
"PostgreSQL", "Fast API" -> "FastAPI".

The alias table lives in data/skill_aliases.json, not in this file — the
maintainable part of this problem is the alias list growing over time,
never the matching logic. A skill with no known alias is NOT dropped and
NOT forced into a guessed canonical form: it's kept as-is with
category=None and matched=False, so normalization never fabricates
information or silently merges two genuinely different technologies
(there is no fuzzy/similarity matching here on purpose — only exact,
curated aliases).
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.models.enums import SkillCategory

_ALIASES_PATH = Path(__file__).parent / "data" / "skill_aliases.json"


@dataclass(frozen=True, slots=True)
class NormalizedSkill:
    canonical: str
    category: SkillCategory | None
    matched: bool  # True if found in the curated alias table


@lru_cache
def _alias_table() -> dict[str, tuple[str, SkillCategory]]:
    raw = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    table: dict[str, tuple[str, SkillCategory]] = {}
    for key, entry in raw.items():
        if key.startswith("_"):
            continue
        table[key] = (entry["canonical"], SkillCategory(entry["category"]))
    return table


def normalize_for_lookup(text: str) -> str:
    """Lookup-key normalization: lowercase, drop periods (so "Node.js" and
    "nodejs" collide), collapse whitespace, strip trailing punctuation.
    Symbols that are semantically load-bearing for a handful of aliases
    ("C++", "C#") are deliberately left alone.
    """
    normalized = text.strip().lower().replace(".", "")
    normalized = re.sub(r"[,;:]+$", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_skill(raw_text: str) -> NormalizedSkill:
    raw_text = raw_text.strip()
    lookup_key = normalize_for_lookup(raw_text)
    hit = _alias_table().get(lookup_key)
    if hit is not None:
        canonical, category = hit
        return NormalizedSkill(canonical=canonical, category=category, matched=True)

    # No curated alias — keep the candidate's own wording rather than
    # inventing a canonical form. Light cosmetic cleanup only (collapse
    # whitespace, trim); never merged with another unmatched skill.
    return NormalizedSkill(
        canonical=re.sub(r"\s+", " ", raw_text).strip(),
        category=SkillCategory.OTHER,
        matched=False,
    )
