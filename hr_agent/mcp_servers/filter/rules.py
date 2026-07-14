"""
Deterministic filtering rules — location and graduation date checks.

Pure rule-based, no LLM needed, zero cost. Used by the Filter MCP server.
"""

from __future__ import annotations

import re


def _normalize_location(location: str) -> str:
    return re.sub(r"[,.\s]+", " ", location.lower().strip())


LOCATION_ALIASES = {
    "boston": {"boston", "boston ma", "boston massachusetts"},
    "raleigh": {"raleigh", "raleigh nc", "raleigh north carolina", "durham", "rtp", "research triangle"},
    "remote": {"remote", "remote us", "remote usa", "work from home", "anywhere"},
}


def check_location(location: str, target_locations: list[str]) -> str | None:
    """Returns a rejection reason if location doesn't match, else None."""
    if not location:
        return "No location found on resume"

    candidate_loc = _normalize_location(location)

    for target in target_locations:
        target_clean = target.strip().lower()

        if target_clean == "remote" and target_clean in candidate_loc:
            return None

        aliases = LOCATION_ALIASES.get(target_clean, {target_clean})
        for alias in aliases:
            if alias in candidate_loc:
                return None

    return f"Location '{location}' not in target areas: {target_locations}"


def check_graduation(graduation_date: str, earliest: str, latest: str) -> str | None:
    """Returns a rejection reason if graduation date is outside the window, else None."""
    if not graduation_date:
        return "No graduation date found on resume"

    if graduation_date < earliest:
        return f"Graduation date {graduation_date} is before window start {earliest} (already graduated)"

    if graduation_date > latest:
        return f"Graduation date {graduation_date} is after window end {latest} (too early in program)"

    return None
