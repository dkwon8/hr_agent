"""
Shared state schema for the recruitment filtration pipeline.

This TypedDict flows through every node in the LangGraph.
Each node reads what it needs and writes back its results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, Annotated
from enum import Enum


class CandidateStatus(str, Enum):
    PENDING = "pending"
    PASSED_DETERMINISTIC = "passed_deterministic"
    PASSED_CROSS_VALIDATION = "passed_cross_validation"
    RANKED = "ranked"
    SELECTED = "selected"
    REJECTED = "rejected"
    FLAGGED = "flagged"


@dataclass
class Candidate:
    id: str
    raw_text: str = ""
    resume_path: str = ""

    # Extracted fields
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    graduation_date: str = ""  # YYYY-MM format
    degree_level: str = ""  # e.g. "junior", "senior", "masters", "phd"
    university: str = ""
    major: str = ""
    skills: list[str] = field(default_factory=list)
    experience_summary: str = ""
    education_summary: str = ""

    # External profile links (extracted from resume)
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""

    # Cross-validation results
    linkedin_graduation_date: str = ""
    linkedin_headline: str = ""
    github_repos: list[dict] = field(default_factory=list)
    github_languages: list[str] = field(default_factory=list)
    cross_validation_notes: list[str] = field(default_factory=list)
    graduation_verified: bool | None = None

    # LLM quality assessment
    quality_score: float = 0.0  # best department score
    quality_reasoning: str = ""
    fit_breakdown: dict = field(default_factory=dict)
    department_scores: dict = field(default_factory=dict)  # {dept_name: {score, reasoning, ...}}
    best_fit_department: str = ""
    top_3_departments: list[dict] = field(default_factory=list)

    # Pipeline tracking
    status: CandidateStatus = CandidateStatus.PENDING
    was_flagged: bool = False
    rejection_reason: str = ""
    current_phase: str = ""


def _replace_candidates(existing: list[Candidate], new: list[Candidate]) -> list[Candidate]:
    """Reducer: always take the latest candidate list (full replacement)."""
    return new


def _append_errors(existing: list[str], new: list[str]) -> list[str]:
    """Reducer: accumulate errors across nodes."""
    return existing + new


class PipelineState(TypedDict):
    candidates: Annotated[list[Candidate], _replace_candidates]
    job_requirements: dict
    resume_dir: str
    target_locations: list[str]
    graduation_earliest: str
    graduation_latest: str
    top_k: int
    current_phase: str
    errors: Annotated[list[str], _append_errors]
    summary: dict
