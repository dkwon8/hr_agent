"""
Scoring MCP Server — LLM-as-a-Judge for candidate evaluation.

Scores candidates against all 12 Red Hat Global Engineering departments
using GPT-5.4. Uses 3-pass median scoring for reliability.

Run standalone:
    python -m mcp_servers.scoring.server                    # stdio mode
    python -m mcp_servers.scoring.server --transport sse    # HTTP mode

Tools:
    score_candidate          — score one candidate against all departments
    score_all_candidates     — batch score and rank candidates, select top K
    get_department_requirements — return the 12 GE departments and their skills
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp_servers.scoring.judge import (
    score_with_median,
    load_prompt,
    get_department_names,
)


def load_job_requirements_from_dir(directory: str) -> dict:
    """Load the first .json file found in the job requirements directory."""
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Job requirements directory not found: {directory}")
    json_files = [f for f in os.listdir(directory) if f.endswith(".json")]
    if not json_files:
        raise FileNotFoundError(f"No job requirements JSON found in {directory}")
    with open(os.path.join(directory, json_files[0])) as f:
        return json.load(f)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("scoring_mcp")

# ── Server Setup ──────────────────────────────────────────

mcp = FastMCP(
    "Scoring MCP Server",
    instructions=(
        "Provides LLM-as-a-Judge scoring for recruitment candidates. "
        "Scores candidates against 12 Red Hat Global Engineering departments "
        "on experience, projects, and learning potential. "
        "Uses 3-pass median scoring for stable, reliable results."
    ),
)

JOB_REQUIREMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "job_requirements")


def _get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL_NAME", "gpt-5.4"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0,
    )


def _load_job_requirements() -> dict:
    return load_job_requirements_from_dir(JOB_REQUIREMENTS_DIR)


# ── MCP Tools ─────────────────────────────────────────────


@mcp.tool()
async def score_candidate(
    candidate_json: str,
) -> str:
    """Score a single candidate against all 12 Global Engineering departments.

    Uses 3-pass median scoring for stability (±1-3 points variance).
    Returns department scores, best fit, top 3 departments, and confidence range.

    Scoring dimensions per department:
    - experience (0-40): evidence of required skills in work experience
    - projects (0-35): relevant personal/academic/open-source projects
    - learning_potential (0-25): growth trajectory and learning signals

    Args:
        candidate_json: JSON string with candidate data (name, skills, experience, etc.)
    """
    candidate = json.loads(candidate_json)
    job_requirements = _load_job_requirements()
    llm = _get_llm()
    prompt = load_prompt()

    result = await score_with_median(candidate, job_requirements, llm, prompt, passes=3)

    return json.dumps(result)


@mcp.tool()
async def score_all_candidates(
    candidates_json: str,
    top_k: int = 100,
) -> str:
    """Score a list of candidates and return them ranked by best-fit department score.

    Each candidate is scored against all 12 departments using 3-pass median.
    Candidates are ranked by their highest department score and the top K
    are marked as selected.

    Args:
        candidates_json: JSON string with list of candidate dicts
        top_k: Number of top candidates to select (default: 100)
    """
    candidates = json.loads(candidates_json)
    job_requirements = _load_job_requirements()
    llm = _get_llm()
    prompt = load_prompt()

    scored = []
    errors = []

    # Process in batches of 10
    batch_size = 10
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        tasks = [score_with_median(c, job_requirements, llm, prompt, passes=3) for c in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for c, result in zip(batch, results):
            if isinstance(result, Exception):
                errors.append({"candidate": c.get("name", c.get("id", "?")), "error": str(result)})
            elif result.get("status") == "scoring_failed":
                errors.append({"candidate": c.get("name", "?"), "error": result.get("error", "unknown")})
            else:
                scored.append(result)

    # Rank by quality score (best department fit)
    ranked = sorted(scored, key=lambda c: c.get("quality_score", 0), reverse=True)

    # Mark top K as selected
    selected = ranked[:top_k]
    for c in selected:
        c["status"] = "selected"
    for c in ranked[top_k:]:
        c["status"] = "ranked"

    return json.dumps({
        "total_scored": len(ranked),
        "selected": len(selected),
        "errors": len(errors),
        "top_score": selected[0]["quality_score"] if selected else None,
        "cutoff_score": selected[-1]["quality_score"] if selected else None,
        "candidates": ranked,
        "error_details": errors,
    })


@mcp.tool()
async def get_department_requirements() -> str:
    """Return the 12 Global Engineering departments and their required skills.

    Each department has a name and a list of required skills used for scoring.
    """
    job_requirements = _load_job_requirements()
    departments = job_requirements.get("departments", {})

    dept_list = []
    for key, info in departments.items():
        dept_list.append({
            "name": info.get("name", key),
            "required_skills": info.get("required_skills", []),
        })

    return json.dumps({
        "organization": job_requirements.get("organization", ""),
        "role": job_requirements.get("role", ""),
        "department_count": len(dept_list),
        "departments": dept_list,
    })


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scoring MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
    )
    parser.add_argument("--port", type=int, default=3004)
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
