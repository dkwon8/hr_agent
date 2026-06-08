"""
Phase 4 — LLM-as-a-Judge Quality Assessment

Evaluates each candidate against ALL Red Hat Global Engineering departments.
Instead of generic keyword matching, the LLM scores how well a candidate
fits each department's skill requirements, then identifies the top 3 best-fit
departments per candidate.
"""

from __future__ import annotations

import asyncio
import json
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import PipelineState, Candidate, CandidateStatus
from src.utils.helpers import TokenTracker
from src.utils.tracing import get_tracer
from config.settings import OPENAI_API_KEY

TUNED_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback", "tuned_prompt.txt")


JUDGE_SYSTEM_PROMPT = """You are a senior technical recruiter at Red Hat evaluating internship candidates for the Global Engineering organization.

You will receive:
1. A list of departments, each with their required skills
2. A candidate's resume information

For EACH department, score the candidate on:
- **skills_match** (0-40): How well do the candidate's skills align with this department's required skills? Evidence of actual use matters more than listing buzzwords.
- **experience_relevance** (0-35): Do their projects/internships/contributions demonstrate capability relevant to this department?
- **potential** (0-25): Growth trajectory, learning ability, and overall promise for this specific team.

Return ONLY valid JSON with this structure:
{
  "departments": {
    "<department_name>": {
      "score": <0-100 total>,
      "skills_match": <0-40>,
      "experience_relevance": <0-35>,
      "potential": <0-25>,
      "reasoning": "1-2 sentence explanation"
    }
  },
  "overall_reasoning": "2-3 sentences on the candidate's general strengths and weaknesses"
}

IMPORTANT: Use the EXACT department names as listed in the input (e.g. "OCTO (Office of the CTO)", not "OCTO"). The department names must match exactly.

Scoring guidelines:
- 0-30: Poor fit — missing most required skills, no relevant experience
- 31-50: Weak fit — some overlap but significant gaps
- 51-70: Moderate fit — has several required skills with some evidence
- 71-85: Strong fit — clear alignment with demonstrated experience
- 86-100: Exceptional fit — deep expertise with strong evidence across all dimensions

Be rigorous. Penalize candidates who list skills without evidence of using them."""


def _load_prompt() -> str:
    if os.path.exists(TUNED_PROMPT_PATH):
        with open(TUNED_PROMPT_PATH) as f:
            prompt = f.read().strip()
        if prompt:
            print("  [LLM Judge] Using tuned prompt from feedback loop")
            return prompt
    return JUDGE_SYSTEM_PROMPT


def _build_candidate_summary(c: Candidate) -> str:
    parts = [
        f"Name: {c.name}",
        f"Location: {c.location}",
        f"University: {c.university}",
        f"Major: {c.major}",
        f"Graduation: {c.graduation_date}",
        f"Degree Level: {c.degree_level}",
        f"Skills: {', '.join(c.skills) if c.skills else 'None listed'}",
        f"Experience: {c.experience_summary or 'None listed'}",
        f"Education: {c.education_summary or 'None listed'}",
    ]

    if c.github_languages:
        parts.append(f"GitHub Languages: {', '.join(c.github_languages)}")
    if c.github_repos:
        repo_names = [r.get("name", "") for r in c.github_repos[:5]]
        parts.append(f"GitHub Repos: {', '.join(repo_names)}")
    if c.linkedin_headline:
        parts.append(f"LinkedIn Headline: {c.linkedin_headline}")

    return "\n".join(parts)


def _get_department_names(job_requirements: dict) -> list[str]:
    """Return the canonical list of department display names."""
    return [
        dept_info.get("name", dept_key)
        for dept_key, dept_info in job_requirements.get("departments", {}).items()
    ]


def _build_departments_text(job_requirements: dict) -> str:
    departments = job_requirements.get("departments", {})
    lines = []
    for idx, (dept_key, dept_info) in enumerate(departments.items(), 1):
        name = dept_info.get("name", dept_key)
        skills = ", ".join(dept_info.get("required_skills", []))
        lines.append(f"{idx}. \"{name}\" — Required skills: {skills}")
    return "\n".join(lines)


async def _score_candidate(
    candidate: Candidate, job_requirements: dict, llm: ChatOpenAI,
    tracker: TokenTracker | None = None, prompt: str | None = None
) -> dict | None:
    candidate_summary = _build_candidate_summary(candidate)
    departments_text = _build_departments_text(job_requirements)
    scoring_prompt = prompt or JUDGE_SYSTEM_PROMPT

    response = await llm.ainvoke([
        SystemMessage(content=scoring_prompt),
        HumanMessage(
            content=(
                f"## Departments and Required Skills\n{departments_text}\n\n"
                f"## Candidate Information\n{candidate_summary}"
            )
        ),
    ])

    if tracker:
        tracker.add(response)

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        return None


def _extract_top_departments(dept_scores: dict, top_n: int = 3) -> list[dict]:
    """Sort departments by score and return the top N."""
    ranked = sorted(
        [
            {"department": name, **scores}
            for name, scores in dept_scores.items()
        ],
        key=lambda d: d.get("score", 0),
        reverse=True,
    )
    return ranked[:top_n]


async def llm_judge(state: PipelineState) -> dict:
    candidates = state["candidates"]
    job_requirements = state["job_requirements"]
    top_k = state["top_k"]

    llm = ChatOpenAI(
        model="gpt-5.4",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )

    eligible_statuses = {
        CandidateStatus.PASSED_CROSS_VALIDATION,
        CandidateStatus.FLAGGED,
    }
    eligible = [c for c in candidates if c.status in eligible_statuses]
    tracker = TokenTracker()
    active_prompt = _load_prompt()

    valid_dept_names = set(_get_department_names(job_requirements))
    print(f"[Phase 4] Scoring {len(eligible)} candidates against {len(valid_dept_names)} departments...")

    errors = []

    async def _score_and_assign(candidate: Candidate) -> str | None:
        try:
            result = await _score_candidate(candidate, job_requirements, llm, tracker, active_prompt)
            if not result or "departments" not in result:
                return f"[llm_judge] {candidate.id}: LLM returned unparseable response"

            dept_scores = result["departments"]
            unknown = set(dept_scores.keys()) - valid_dept_names
            warning = None
            if unknown:
                warning = f"[llm_judge] {candidate.id}: LLM returned unknown department names: {unknown}"

            candidate.department_scores = dept_scores

            top_depts = _extract_top_departments(dept_scores)
            candidate.top_3_departments = top_depts

            if top_depts:
                best = top_depts[0]
                candidate.best_fit_department = best["department"]
                candidate.quality_score = best.get("score", 0)
                candidate.quality_reasoning = (
                    f"Best fit: {best['department']} ({best.get('score', 0)}/100). "
                    f"{best.get('reasoning', '')} "
                    f"{result.get('overall_reasoning', '')}"
                )
                candidate.fit_breakdown = {
                    "skills_match": best.get("skills_match", 0),
                    "experience_relevance": best.get("experience_relevance", 0),
                    "potential": best.get("potential", 0),
                }

            candidate.status = CandidateStatus.RANKED
            candidate.current_phase = "llm_judge"
            return warning
        except Exception as e:
            return f"[llm_judge] {candidate.id}: {e}"

    batch_size = 10
    for i in range(0, len(eligible), batch_size):
        batch = eligible[i : i + batch_size]
        results = await asyncio.gather(*[_score_and_assign(c) for c in batch])
        errors.extend([r for r in results if r is not None])

    ranked = sorted(
        [c for c in candidates if c.status == CandidateStatus.RANKED],
        key=lambda c: c.quality_score,
        reverse=True,
    )

    selected = ranked[:top_k]
    for c in selected:
        c.status = CandidateStatus.SELECTED

    print(f"[Phase 4] Scored {len(ranked)} candidates.")
    if selected:
        print(f"  Selected {len(selected)} of {top_k} target (top-k).")
        print(f"  Highest score:  {selected[0].quality_score} ({selected[0].best_fit_department})")
        print(f"  Cutoff score:   {selected[-1].quality_score} ({selected[-1].best_fit_department})")
    else:
        print("  No candidates were scored.")
    print(f"  {tracker.summary('LLM Judge')}")

    tracer = get_tracer()
    if tracer:
        tracer.log_token_usage("llm_judge", tracker)
        tracer.log_phase_metrics("llm_judge", {
            "candidates_scored": len(ranked),
            "candidates_selected": len(selected),
            "highest_score": selected[0].quality_score if selected else 0,
            "cutoff_score": selected[-1].quality_score if selected else 0,
        })

    return {
        "candidates": candidates,
        "current_phase": "llm_judge_complete",
        "errors": errors,
    }
