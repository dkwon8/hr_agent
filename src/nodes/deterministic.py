"""
Phase 2 — Deterministic Filtering

Pure rule-based filtering (no LLM):
  1. Location check: candidate must be in one of the target locations
  2. Graduation date check: must fall within the target window (i.e. junior standing)

Candidates that fail get status=REJECTED with a reason.
Candidates that pass get status=PASSED_DETERMINISTIC.
"""

from __future__ import annotations

import re

from src.state import PipelineState, Candidate, CandidateStatus
from src.utils.tracing import get_tracer


def _normalize_location(location: str) -> str:
    return re.sub(r"[,.\s]+", " ", location.lower().strip())


LOCATION_ALIASES = {
    "boston": {"boston", "boston ma", "boston massachusetts"},
    "raleigh": {"raleigh", "raleigh nc", "raleigh north carolina", "durham", "rtp", "research triangle"},
    "remote": {"remote", "remote us", "remote usa", "work from home", "anywhere"},
}


def _check_location(candidate: Candidate, target_locations: list[str]) -> str | None:
    """Returns a rejection reason if location doesn't match, else None."""
    if not candidate.location:
        return "No location found on resume"

    candidate_loc = _normalize_location(candidate.location)

    for target in target_locations:
        target_clean = target.strip().lower()

        if target_clean == "remote" and target_clean in candidate_loc:
            return None

        aliases = LOCATION_ALIASES.get(target_clean, {target_clean})
        for alias in aliases:
            if alias in candidate_loc:
                return None

    return f"Location '{candidate.location}' not in target areas: {target_locations}"


def _check_graduation(
    candidate: Candidate, earliest: str, latest: str
) -> str | None:
    """Returns a rejection reason if graduation date is outside the window, else None."""
    if not candidate.graduation_date:
        return "No graduation date found on resume"

    grad = candidate.graduation_date  # YYYY-MM format

    if grad < earliest:
        return f"Graduation date {grad} is before window start {earliest} (already graduated)"

    if grad > latest:
        return f"Graduation date {grad} is after window end {latest} (too early in program)"

    return None


async def deterministic_filter(state: PipelineState) -> dict:
    candidates = state["candidates"]
    target_locations = state["target_locations"]
    earliest = state["graduation_earliest"]
    latest = state["graduation_latest"]

    passed = 0
    rejected = 0
    errors = []

    for candidate in candidates:
        if candidate.status == CandidateStatus.REJECTED:
            rejected += 1
            continue

        location_issue = _check_location(candidate, target_locations)
        graduation_issue = _check_graduation(candidate, earliest, latest)

        reasons = []
        if location_issue:
            reasons.append(location_issue)
        if graduation_issue:
            reasons.append(graduation_issue)

        if reasons:
            candidate.status = CandidateStatus.REJECTED
            candidate.rejection_reason = "; ".join(reasons)
            candidate.current_phase = "deterministic"
            rejected += 1
        else:
            candidate.status = CandidateStatus.PASSED_DETERMINISTIC
            candidate.current_phase = "deterministic"
            passed += 1

    print(f"[Phase 2] Deterministic filter: {passed} passed, {rejected} rejected")

    tracer = get_tracer()
    if tracer:
        tracer.log_phase_metrics("deterministic", {
            "passed": passed,
            "rejected": rejected,
            "rejection_rate": round(rejected / max(len(candidates), 1) * 100, 1),
        })

    return {
        "candidates": candidates,
        "current_phase": "deterministic_complete",
        "errors": errors,
    }
