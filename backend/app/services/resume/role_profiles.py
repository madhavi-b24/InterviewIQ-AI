"""Internal InterviewIQ competency profiles (module §11).

These are InterviewIQ's own baseline for what a role generally involves —
explicitly NOT a claim about any specific employer's hiring bar. Kept as
a small maintainable data file (data/role_profiles.json), not scattered
across service code, so adding a 6th role later is a data change.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

_ROLE_PROFILES_PATH = Path(__file__).parent / "data" / "role_profiles.json"


class RoleProfile(BaseModel):
    key: str
    label: str
    required_skills: list[str]
    nice_to_have_skills: list[str] = []


@lru_cache
def load_role_profiles() -> dict[str, RoleProfile]:
    raw = json.loads(_ROLE_PROFILES_PATH.read_text(encoding="utf-8"))
    return {
        key: RoleProfile(key=key, **entry) for key, entry in raw.items() if not key.startswith("_")
    }


def get_role_profile(role_key: str) -> RoleProfile | None:
    return load_role_profiles().get(role_key)


def available_role_keys() -> list[str]:
    return sorted(load_role_profiles().keys())
