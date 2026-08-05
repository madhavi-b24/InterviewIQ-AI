"""Resume section detection (module §4).

Deterministic, header-line matching — no LLM involved. A resume's raw
text is split into named chunks by scanning for a standalone line that
matches a known section-header phrase (case/punctuation-insensitive).
Not every resume has every section; `detect_sections` only returns keys
that were actually found.

The alias list lives in code (not a data file) because, unlike skill
names, resume section headers are a small, closed, slowly-changing
vocabulary — no maintenance argument for externalizing it the way
skill_normalization.py's alias map earns one.
"""

import re

# Canonical section name -> phrases (normalized: lowercase, no trailing
# punctuation) that count as that section's header line.
SECTION_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "objective",
        "profile",
        "career objective",
        "about me",
    ),
    "education": ("education", "academic background", "educational qualifications", "academics"),
    "skills": (
        "skills",
        "technical skills",
        "skills & tools",
        "skills and tools",
        "core competencies",
        "technologies",
        "technical proficiencies",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "internships",
        "internship experience",
        "work history",
    ),
    "projects": (
        "projects",
        "academic projects",
        "personal projects",
        "key projects",
        "project experience",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses & certifications",
        "licenses and certifications",
    ),
    "achievements": (
        "achievements",
        "awards",
        "awards & achievements",
        "awards and achievements",
        "honors",
        "honors & awards",
    ),
    "publications": ("publications", "research publications"),
    "positions_of_responsibility": (
        "positions of responsibility",
        "leadership",
        "leadership & extracurricular",
        "leadership and extracurricular",
        "extracurricular activities",
        "positions of responsibility (por)",
    ),
}

_MAX_HEADER_LINE_LENGTH = 60


def detect_sections(full_text: str) -> dict[str, str]:
    """Returns {canonical_section_name: raw_text_chunk}. A resume with no
    detectable headers at all returns {} — callers must not assume any
    key is present.
    """
    lines = full_text.splitlines()
    variant_to_section = {
        variant: name for name, variants in SECTION_HEADER_ALIASES.items() for variant in variants
    }

    boundaries: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        normalized = _normalize_header_line(line)
        if not normalized or len(normalized) > _MAX_HEADER_LINE_LENGTH:
            continue
        section = variant_to_section.get(normalized)
        if section is not None:
            boundaries.append((index, section))

    sections: dict[str, str] = {}
    for position, (line_no, name) in enumerate(boundaries):
        start = line_no + 1
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if not chunk:
            continue
        # A section header repeated further down (rare, but seen in
        # multi-column resumes that got flattened) appends rather than
        # overwrites, so no text is silently discarded.
        sections[name] = f"{sections[name]}\n{chunk}" if name in sections else chunk

    return sections


def _normalize_header_line(line: str) -> str:
    stripped = re.sub(r"[:\-–—•*]+$", "", line.strip()).strip().lower()
    # Collapse internal whitespace so "Technical   Skills" still matches.
    return re.sub(r"\s+", " ", stripped)
