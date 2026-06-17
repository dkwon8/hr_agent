"""
LLM-as-a-Judge scoring logic.

Evaluates candidates against Red Hat Global Engineering department
requirements. Uses 3-pass median scoring for reliability.
Used by the Scoring MCP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


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


def load_prompt() -> str:
    """Load tuned prompt if available, otherwise use default."""
    if os.path.exists(TUNED_PROMPT_PATH):
        with open(TUNED_PROMPT_PATH) as f:
            prompt = f.read().strip()
        if prompt:
            return prompt
    return JUDGE_SYSTEM_PROMPT


def build_candidate_summary(candidate: dict) -> str:
    """Build a text summary of a candidate for the LLM judge."""
    parts = [
        f"Name: {candidate.get('name', '')}",
        f"Location: {candidate.get('location', '')}",
        f"University: {candidate.get('university', '')}",
        f"Major: {candidate.get('major', '')}",
        f"Graduation: {candidate.get('graduation_date', '')}",
        f"Degree Level: {candidate.get('degree_level', '')}",
        f"Skills: {', '.join(candidate.get('skills', [])) or 'None listed'}",
        f"Experience: {candidate.get('experience_summary', '') or 'None listed'}",
        f"Education: {candidate.get('education_summary', '') or 'None listed'}",
    ]

    github_languages = candidate.get("github_languages", [])
    if github_languages:
        parts.append(f"GitHub Languages: {', '.join(github_languages)}")

    github_repos = candidate.get("github_repos", [])
    if github_repos:
        repo_names = [r.get("name", "") for r in github_repos[:5]]
        parts.append(f"GitHub Repos: {', '.join(repo_names)}")

    linkedin_headline = candidate.get("linkedin_headline", "")
    if linkedin_headline:
        parts.append(f"LinkedIn Headline: {linkedin_headline}")

    return "\n".join(parts)


def get_department_names(job_requirements: dict) -> list[str]:
    """Return the canonical list of department display names."""
    return [
        dept_info.get("name", dept_key)
        for dept_key, dept_info in job_requirements.get("departments", {}).items()
    ]


def build_departments_text(job_requirements: dict) -> str:
    """Build numbered department list for the LLM prompt."""
    departments = job_requirements.get("departments", {})
    lines = []
    for idx, (dept_key, dept_info) in enumerate(departments.items(), 1):
        name = dept_info.get("name", dept_key)
        skills = ", ".join(dept_info.get("required_skills", []))
        lines.append(f'{idx}. "{name}" — Required skills: {skills}')
    return "\n".join(lines)


def parse_llm_json(content: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown fences and trailing commas."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
    content = re.sub(r"\n?```\s*$", "", content.strip())

    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        raw = content[start:end]
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    return None


async def score_single_candidate(
    candidate: dict, job_requirements: dict, llm: ChatOpenAI,
    prompt: str | None = None,
) -> dict | None:
    """Score one candidate against all departments in a single LLM call."""
    candidate_summary = build_candidate_summary(candidate)
    departments_text = build_departments_text(job_requirements)
    scoring_prompt = prompt or JUDGE_SYSTEM_PROMPT

    response = await llm.ainvoke([
        SystemMessage(content=scoring_prompt),
        HumanMessage(content=(
            f"## Departments and Required Skills\n{departments_text}\n\n"
            f"## Candidate Information\n{candidate_summary}"
        )),
    ])

    return parse_llm_json(response.content)


def extract_top_departments(dept_scores: dict, top_n: int = 3) -> list[dict]:
    """Sort departments by score and return the top N."""
    ranked = sorted(
        [{"department": name, **scores} for name, scores in dept_scores.items()],
        key=lambda d: d.get("score", 0),
        reverse=True,
    )
    return ranked[:top_n]


async def score_with_median(
    candidate: dict, job_requirements: dict, llm: ChatOpenAI,
    prompt: str | None = None, passes: int = 3,
) -> dict:
    """Score a candidate multiple times and take the median for stability.

    Returns the candidate dict enriched with scoring results and confidence.
    """
    tasks = [score_single_candidate(candidate, job_requirements, llm, prompt) for _ in range(passes)]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    pass_results = [r for r in raw_results if isinstance(r, dict) and "departments" in r]

    if not pass_results:
        return {**candidate, "status": "scoring_failed", "error": "All scoring passes failed"}

    # For each department, take the median score across passes
    all_dept_names = set()
    for r in pass_results:
        all_dept_names.update(r["departments"].keys())

    median_dept_scores = {}
    for dept in all_dept_names:
        dept_pass_scores = [
            r["departments"][dept] for r in pass_results if dept in r["departments"]
        ]
        if not dept_pass_scores:
            continue

        scores_list = sorted([d.get("score", 0) for d in dept_pass_scores])
        median_idx = len(scores_list) // 2
        median_entry = dept_pass_scores[
            [d.get("score", 0) for d in dept_pass_scores].index(scores_list[median_idx])
        ]
        median_dept_scores[dept] = median_entry

    top_depts = extract_top_departments(median_dept_scores)

    scored_candidate = {**candidate, "department_scores": median_dept_scores}

    if top_depts:
        best = top_depts[0]
        scored_candidate["best_fit_department"] = best["department"]
        scored_candidate["quality_score"] = best.get("score", 0)
        scored_candidate["top_3_departments"] = top_depts
        scored_candidate["fit_breakdown"] = {
            "skills_match": best.get("skills_match", 0),
            "experience_relevance": best.get("experience_relevance", 0),
            "potential": best.get("potential", 0),
        }

        # Get overall reasoning from the median pass
        best_dept = best["department"]
        best_scores = sorted(
            [(r["departments"].get(best_dept, {}).get("score", 0), r) for r in pass_results],
            key=lambda x: x[0],
        )
        median_result = best_scores[len(best_scores) // 2][1]

        scored_candidate["quality_reasoning"] = (
            f"Best fit: {best['department']} ({best.get('score', 0)}/100). "
            f"{best.get('reasoning', '')} "
            f"{median_result.get('overall_reasoning', '')}"
        )

        # Confidence from multi-pass
        all_best_scores = [s[0] for s in best_scores]
        scored_candidate["score_confidence"] = {
            "min": min(all_best_scores),
            "max": max(all_best_scores),
            "median": scored_candidate["quality_score"],
            "range": max(all_best_scores) - min(all_best_scores),
            "passes": len(pass_results),
        }

    scored_candidate["status"] = "scored"
    return scored_candidate
