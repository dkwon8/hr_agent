"""
Phase 3 — Cross-Validation via External Sources

For candidates that passed deterministic filtering:
  1. If LinkedIn URL exists → look up profile, compare graduation date
  2. If GitHub URL exists → pull profile data for enrichment
  3. Flag candidates with graduation date mismatches

This is the heaviest tool-calling phase and the main technical bottleneck
(API rate limits, availability, etc.).
"""

from __future__ import annotations

import asyncio

from src.state import PipelineState, Candidate, CandidateStatus
from src.utils.tracing import get_tracer
from src.tools.linkedin import (
    lookup_linkedin_profile,
    extract_graduation_from_linkedin,
    extract_headline,
)
from src.tools.github import lookup_github_profile


async def _validate_single_candidate(candidate: Candidate) -> list[str]:
    """Run LinkedIn + GitHub lookups for one candidate. Returns error messages."""
    errors = []

    # LinkedIn cross-validation
    if candidate.linkedin_url:
        profile = await lookup_linkedin_profile(candidate.linkedin_url)

        if profile and "error" not in profile:
            linkedin_grad = extract_graduation_from_linkedin(profile)
            candidate.linkedin_graduation_date = linkedin_grad
            candidate.linkedin_headline = extract_headline(profile)

            if linkedin_grad and candidate.graduation_date:
                if linkedin_grad != candidate.graduation_date:
                    candidate.cross_validation_notes.append(
                        f"Graduation mismatch: resume says {candidate.graduation_date}, "
                        f"LinkedIn says {linkedin_grad}"
                    )
                    candidate.graduation_verified = False
                else:
                    candidate.graduation_verified = True
                    candidate.cross_validation_notes.append("Graduation date verified via LinkedIn")
            else:
                candidate.cross_validation_notes.append(
                    "Could not compare graduation dates (missing data)"
                )
        elif profile and profile.get("error") == "rate_limited":
            errors.append(f"[cross_val] {candidate.id}: LinkedIn rate limited")
            candidate.cross_validation_notes.append("LinkedIn lookup rate-limited, skipped")
        else:
            candidate.cross_validation_notes.append("LinkedIn lookup failed or no data returned")
    else:
        candidate.cross_validation_notes.append("No LinkedIn URL on resume")

    # GitHub enrichment
    if candidate.github_url:
        gh_data = await lookup_github_profile(candidate.github_url)
        if gh_data:
            candidate.github_repos = gh_data.get("repos", [])
            candidate.github_languages = gh_data.get("languages", [])
            candidate.cross_validation_notes.append(
                f"GitHub: {gh_data.get('public_repos', 0)} public repos, "
                f"languages: {', '.join(gh_data.get('languages', []))}"
            )
        else:
            candidate.cross_validation_notes.append("GitHub lookup failed or profile not found")
    else:
        candidate.cross_validation_notes.append("No GitHub URL on resume")

    return errors


async def cross_validate(state: PipelineState) -> dict:
    candidates = state["candidates"]

    active = [
        c for c in candidates
        if c.status == CandidateStatus.PASSED_DETERMINISTIC
    ]

    print(f"[Phase 3] Cross-validating {len(active)} candidates...")

    all_errors = []

    batch_size = 5
    for i in range(0, len(active), batch_size):
        batch = active[i : i + batch_size]
        tasks = [_validate_single_candidate(c) for c in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for c, result in zip(batch, results):
            if isinstance(result, Exception):
                all_errors.append(f"[cross_val] {c.id}: {result}")
                c.cross_validation_notes.append(f"Validation error: {result}")
            else:
                all_errors.extend(result)

        if i + batch_size < len(active):
            await asyncio.sleep(2)

    # Flag or reject candidates with confirmed mismatches
    flagged = 0
    verified = 0
    for c in active:
        if c.graduation_verified is False:
            c.status = CandidateStatus.FLAGGED
            c.was_flagged = True
            c.current_phase = "cross_validation"
            flagged += 1
        else:
            c.status = CandidateStatus.PASSED_CROSS_VALIDATION
            c.current_phase = "cross_validation"
            if c.graduation_verified is True:
                verified += 1

    unverified = len(active) - verified - flagged
    print(
        f"[Phase 3] Cross-validation done: {verified} verified, "
        f"{flagged} flagged, {unverified} unverified (passed)"
    )

    tracer = get_tracer()
    if tracer:
        tracer.log_phase_metrics("cross_validation", {
            "candidates_checked": len(active),
            "verified": verified,
            "flagged": flagged,
            "unverified": unverified,
            "api_errors": len(all_errors),
        })

    return {
        "candidates": candidates,
        "current_phase": "cross_validation_complete",
        "errors": all_errors,
    }
