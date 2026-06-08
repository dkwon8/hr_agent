"""
Phase 6 — IBM CLEAR-style Evaluation

Audits the LLM judge's scoring for quality issues:
  1. Correctness: Do scores align with actual candidate skills/experience?
  2. Groundedness: Is the reasoning supported by resume content?
  3. Consistency: Are similar candidates scored similarly?

Runs AFTER the main pipeline as a quality gate. Results are logged to MLflow
and surfaced in the report for human review.
"""

from __future__ import annotations

import asyncio
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import PipelineState, Candidate, CandidateStatus
from src.utils.helpers import TokenTracker
from src.utils.tracing import get_tracer
from config.settings import OPENAI_API_KEY


CORRECTNESS_PROMPT = """You are an AI evaluation auditor. Your job is to verify whether an LLM recruiter's scoring of a candidate is CORRECT.

You will receive:
1. The candidate's actual resume data (skills, experience, education)
2. The LLM's scoring breakdown and reasoning for a specific department
3. That department's required skills

Check for these errors:
- **Inflated scores**: Did the LLM give high skills_match for skills the candidate doesn't actually have?
- **Missed skills**: Did the LLM give low scores despite the candidate clearly having relevant skills?
- **Reasoning errors**: Does the reasoning contradict the scores?
- **Score math**: Does skills_match(0-40) + experience_relevance(0-35) + potential(0-25) = total score(0-100)?

Return ONLY valid JSON:
{
  "is_correct": true/false,
  "issues": ["list of specific issues found, or empty if correct"],
  "suggested_score_adjustment": 0,
  "confidence": "high/medium/low",
  "explanation": "1-2 sentence summary"
}

Be strict. Flag any score that doesn't match the evidence."""


GROUNDEDNESS_PROMPT = """You are an AI evaluation auditor checking whether an LLM recruiter's reasoning is GROUNDED in actual resume content.

You will receive:
1. The candidate's raw resume text
2. The LLM's reasoning about the candidate

Check:
- Does the reasoning reference skills/experiences actually present in the resume?
- Did the LLM hallucinate qualifications, projects, or experiences not in the resume?
- Is there any fabricated or assumed information?

Return ONLY valid JSON:
{
  "is_grounded": true/false,
  "hallucinations": ["list of claims not supported by resume, or empty"],
  "unsupported_claims": 0,
  "confidence": "high/medium/low",
  "explanation": "1-2 sentence summary"
}"""


CONSISTENCY_PROMPT = """You are an AI evaluation auditor checking whether an LLM recruiter scored two similar candidates CONSISTENTLY.

You will receive two candidates with similar profiles and their scores.

Check:
- Do candidates with similar skills get similar skills_match scores?
- Are there unexplained large score gaps (>15 points) between similar candidates?
- Is there evidence of positional bias (earlier candidates scored differently than later ones)?

Return ONLY valid JSON:
{
  "is_consistent": true/false,
  "score_gap": <number>,
  "issues": ["list of consistency issues, or empty"],
  "explanation": "1-2 sentence summary"
}"""


async def _check_correctness(
    candidate: Candidate, dept_name: str, dept_scores: dict,
    dept_required_skills: list[str], llm: ChatOpenAI, tracker: TokenTracker
) -> dict:
    candidate_data = {
        "name": candidate.name,
        "skills": candidate.skills,
        "experience": candidate.experience_summary,
        "education": candidate.education_summary,
        "github_languages": candidate.github_languages,
    }

    scoring_data = {
        "department": dept_name,
        "scores": dept_scores,
        "required_skills": dept_required_skills,
    }

    response = await llm.ainvoke([
        SystemMessage(content=CORRECTNESS_PROMPT),
        HumanMessage(content=(
            f"## Candidate Data\n{json.dumps(candidate_data, indent=2)}\n\n"
            f"## LLM Scoring\n{json.dumps(scoring_data, indent=2)}"
        )),
    ])
    tracker.add(response)

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        return {"is_correct": None, "issues": ["Failed to parse evaluation response"]}


async def _check_groundedness(
    candidate: Candidate, llm: ChatOpenAI, tracker: TokenTracker
) -> dict:
    resume_text = candidate.raw_text[:3000]
    reasoning = candidate.quality_reasoning

    response = await llm.ainvoke([
        SystemMessage(content=GROUNDEDNESS_PROMPT),
        HumanMessage(content=(
            f"## Resume Text\n{resume_text}\n\n"
            f"## LLM Reasoning\n{reasoning}"
        )),
    ])
    tracker.add(response)

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        return {"is_grounded": None, "hallucinations": ["Failed to parse evaluation response"]}


async def _check_consistency(
    candidate_a: Candidate, candidate_b: Candidate,
    llm: ChatOpenAI, tracker: TokenTracker
) -> dict:
    def _summarize(c: Candidate) -> dict:
        return {
            "name": c.name,
            "skills": c.skills,
            "major": c.major,
            "degree_level": c.degree_level,
            "quality_score": c.quality_score,
            "best_fit_department": c.best_fit_department,
            "fit_breakdown": c.fit_breakdown,
        }

    response = await llm.ainvoke([
        SystemMessage(content=CONSISTENCY_PROMPT),
        HumanMessage(content=(
            f"## Candidate A\n{json.dumps(_summarize(candidate_a), indent=2)}\n\n"
            f"## Candidate B\n{json.dumps(_summarize(candidate_b), indent=2)}"
        )),
    ])
    tracker.add(response)

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        return {"is_consistent": None, "issues": ["Failed to parse evaluation response"]}


def _find_similar_pairs(candidates: list[Candidate], max_pairs: int = 5) -> list[tuple[Candidate, Candidate]]:
    """Find pairs of candidates with similar skills for consistency checking."""
    pairs = []
    scored = [c for c in candidates if c.quality_score > 0]

    for i, a in enumerate(scored):
        for b in scored[i + 1:]:
            if len(pairs) >= max_pairs:
                return pairs

            shared_skills = set(s.lower() for s in a.skills) & set(s.lower() for s in b.skills)
            if len(shared_skills) >= 3:
                pairs.append((a, b))

    return pairs


async def evaluate_pipeline(state: PipelineState) -> dict:
    candidates = state["candidates"]
    job_requirements = state["job_requirements"]
    tracker = TokenTracker()
    tracer = get_tracer()

    llm = ChatOpenAI(
        model="gpt-5.4",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )

    scored = [c for c in candidates if c.status in {CandidateStatus.RANKED, CandidateStatus.SELECTED}]

    if not scored:
        print("[Phase 6] No scored candidates to evaluate.")
        return {"candidates": candidates, "current_phase": "evaluation_complete", "errors": []}

    sample_size = min(len(scored), 10)
    sample = scored[:sample_size]

    print(f"[Phase 6] CLEAR Evaluation — auditing {sample_size} candidates...")

    departments = job_requirements.get("departments", {})
    dept_skills = {
        info.get("name", key): info.get("required_skills", [])
        for key, info in departments.items()
    }

    # 1. Correctness checks — evaluate each sampled candidate's best-fit score
    correctness_results = []
    async def _correctness_task(c: Candidate) -> dict:
        dept = c.best_fit_department
        dept_score = c.department_scores.get(dept, {})
        skills = dept_skills.get(dept, [])
        result = await _check_correctness(c, dept, dept_score, skills, llm, tracker)
        return {"candidate_id": c.id, "candidate_name": c.name, "department": dept, **result}

    correctness_results = await asyncio.gather(*[_correctness_task(c) for c in sample])

    # 2. Groundedness checks
    groundedness_results = []
    async def _groundedness_task(c: Candidate) -> dict:
        result = await _check_groundedness(c, llm, tracker)
        return {"candidate_id": c.id, "candidate_name": c.name, **result}

    groundedness_results = await asyncio.gather(*[_groundedness_task(c) for c in sample])

    # 3. Consistency checks
    pairs = _find_similar_pairs(scored)
    consistency_results = []
    if pairs:
        async def _consistency_task(pair: tuple) -> dict:
            a, b = pair
            result = await _check_consistency(a, b, llm, tracker)
            return {"candidate_a": a.id, "candidate_b": b.id, **result}

        consistency_results = await asyncio.gather(*[_consistency_task(p) for p in pairs])

    # Compute summary metrics
    correctness_pass = sum(1 for r in correctness_results if r.get("is_correct"))
    groundedness_pass = sum(1 for r in groundedness_results if r.get("is_grounded"))
    consistency_pass = sum(1 for r in consistency_results if r.get("is_consistent"))

    total_hallucinations = sum(r.get("unsupported_claims", 0) for r in groundedness_results)

    eval_summary = {
        "candidates_evaluated": sample_size,
        "correctness": {
            "passed": correctness_pass,
            "failed": sample_size - correctness_pass,
            "pass_rate": round(correctness_pass / max(sample_size, 1) * 100, 1),
            "details": correctness_results,
        },
        "groundedness": {
            "passed": groundedness_pass,
            "failed": sample_size - groundedness_pass,
            "pass_rate": round(groundedness_pass / max(sample_size, 1) * 100, 1),
            "total_hallucinations": total_hallucinations,
            "details": groundedness_results,
        },
        "consistency": {
            "pairs_checked": len(pairs),
            "passed": consistency_pass,
            "failed": len(pairs) - consistency_pass,
            "pass_rate": round(consistency_pass / max(len(pairs), 1) * 100, 1) if pairs else None,
            "details": consistency_results,
        },
    }

    # Print summary
    print(f"\n{'='*60}")
    print(f"[Phase 6] CLEAR EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"  Candidates audited:    {sample_size}")
    print(f"  Correctness pass rate: {eval_summary['correctness']['pass_rate']}%")
    print(f"  Groundedness pass rate:{eval_summary['groundedness']['pass_rate']}%")
    print(f"  Hallucinations found:  {total_hallucinations}")
    if pairs:
        print(f"  Consistency pass rate: {eval_summary['consistency']['pass_rate']}%")
    else:
        print(f"  Consistency:           No similar pairs found to compare")
    print(f"  {tracker.summary('Evaluation')}")
    print(f"{'='*60}\n")

    # Log to MLflow
    if tracer:
        tracer.log_token_usage("evaluation", tracker)
        tracer.log_phase_metrics("evaluation", {
            "candidates_audited": sample_size,
            "correctness_pass_rate": eval_summary["correctness"]["pass_rate"],
            "groundedness_pass_rate": eval_summary["groundedness"]["pass_rate"],
            "total_hallucinations": total_hallucinations,
            "consistency_pairs_checked": len(pairs),
        })
        if pairs:
            tracer.log_phase_metrics("evaluation", {
                "consistency_pass_rate": eval_summary["consistency"]["pass_rate"],
            })

    # Add eval summary to pipeline state
    current_summary = state.get("summary", {})
    current_summary["evaluation"] = eval_summary

    return {
        "candidates": candidates,
        "current_phase": "evaluation_complete",
        "summary": current_summary,
        "errors": [],
    }
