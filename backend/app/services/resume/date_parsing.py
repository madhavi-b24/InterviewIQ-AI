"""Best-effort parsing of the free-text dates an LLM extraction returns
("Jan 2022", "2021", "2019 - Present" already split into "2019"/"Present"
by the caller). Never guesses — an unparseable or open-ended ("Present")
value returns None rather than inventing a date, matching module §5's
"never invent information" rule.
"""

import re
from datetime import date

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_OPEN_ENDED = {"present", "current", "ongoing", "now", "till date", "till now"}


def parse_loose_date(text: str | None) -> date | None:
    if not text:
        return None
    normalized = text.strip().lower()
    if normalized in _OPEN_ENDED:
        return None

    if match := re.match(r"^(\d{4})$", normalized):
        return date(int(match.group(1)), 1, 1)

    if match := re.match(r"^(\d{4})-(\d{1,2})$", normalized):
        month = int(match.group(2))
        if 1 <= month <= 12:
            return date(int(match.group(1)), month, 1)

    if match := re.match(r"^([a-z]{3,9})\.?\s+(\d{4})$", normalized):
        month = _MONTHS.get(match.group(1)[:3])
        if month:
            return date(int(match.group(2)), month, 1)

    if match := re.match(r"^(\d{1,2})/(\d{4})$", normalized):
        month = int(match.group(1))
        if 1 <= month <= 12:
            return date(int(match.group(2)), month, 1)

    return None
