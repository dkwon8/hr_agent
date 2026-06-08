"""
Feedback pattern analyzer — identifies systematic scoring issues
from accumulated human feedback and generates prompt adjustments.

This is the "self-healing" core of the Closing the Loop system.
"""

from __future__ import annotations

import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.feedback.store import FeedbackStore, FeedbackEntry
from src.utils.helpers import TokenTracker
from config.settings import OPENAI_API_KEY


def analyze_patterns(store: FeedbackStore) -> dict:
    """Analyze feedback history for systematic patterns."""
    entries = store.get_all()
    if len(entries) < 3:
        return {"sufficient_data": False, "message": "Need at least 3 feedback entries to analyze patterns"}

    patterns = {
        "sufficient_data": True,
        "total_feedback": len(entries),
        "department_issues": {},
        "skill_issues": {},
        "systematic_bias": None,
    }

    # Per-department analysis
    departments = set(e.department for e in entries)
    for dept in departments:
        dept_entries = store.get_for_department(dept)
        if not dept_entries:
            continue

        diffs = [e.human_score - e.llm_score for e in dept_entries if e.human_score is not None]
        if not diffs:
            continue

        avg_diff = sum(diffs) / len(diffs)
        rejection_rate = sum(1 for e in dept_entries if e.action == "reject") / len(dept_entries)

        if abs(avg_diff) > 10 or rejection_rate > 0.3:
            patterns["department_issues"][dept] = {
                "avg_score_diff": round(avg_diff, 1),
                "direction": "overscoring" if avg_diff < 0 else "underscoring",
                "rejection_rate": round(rejection_rate * 100, 1),
                "sample_size": len(dept_entries),
            }

    # Skill-level analysis from overrides
    skill_adjustments: dict[str, list[float]] = {}
    for e in entries:
        for skill, adjustment in e.skill_overrides.items():
            if skill not in skill_adjustments:
                skill_adjustments[skill] = []
            skill_adjustments[skill].append(adjustment)

    for skill, adjustments in skill_adjustments.items():
        avg = sum(adjustments) / len(adjustments)
        if abs(avg) > 5 and len(adjustments) >= 2:
            patterns["skill_issues"][skill] = {
                "avg_adjustment": round(avg, 1),
                "direction": "overweighted" if avg < 0 else "underweighted",
                "occurrences": len(adjustments),
            }

    # Overall bias detection
    summary = store.summary()
    if summary["avg_score_adjustment"] != 0:
        patterns["systematic_bias"] = {
            "direction": summary["bias_direction"],
            "magnitude": abs(summary["avg_score_adjustment"]),
        }

    return patterns


PROMPT_TUNING_PROMPT = """You are an AI system optimizer. Based on human feedback patterns about an LLM recruiter's scoring, generate specific prompt adjustments.

You will receive:
1. The current scoring prompt
2. Patterns found in human feedback (departments being over/underscored, skills being over/underweighted, systematic biases)

Generate SPECIFIC, ACTIONABLE additions to the scoring prompt that address each pattern. These additions will be appended to the existing prompt.

Return ONLY valid JSON:
{
  "adjustments": [
    {
      "type": "department_calibration" | "skill_weighting" | "bias_correction" | "general",
      "target": "department or skill name, or 'general'",
      "instruction": "The specific text to add to the prompt",
      "reasoning": "Why this adjustment addresses the feedback pattern"
    }
  ],
  "confidence": "high/medium/low",
  "summary": "1-2 sentence summary of all adjustments"
}

Make adjustments precise and measurable. Instead of "score harder", say "reduce skills_match by 5-8 points when the candidate lists the skill but has no project demonstrating it"."""


async def generate_prompt_adjustments(
    current_prompt: str, patterns: dict, tracker: TokenTracker | None = None
) -> dict:
    """Use an LLM to generate prompt adjustments based on feedback patterns."""
    if not patterns.get("sufficient_data"):
        return {"adjustments": [], "summary": "Insufficient feedback data"}

    llm = ChatOpenAI(
        model="gpt-5.4",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )

    response = await llm.ainvoke([
        SystemMessage(content=PROMPT_TUNING_PROMPT),
        HumanMessage(content=(
            f"## Current Scoring Prompt\n{current_prompt}\n\n"
            f"## Feedback Patterns\n{json.dumps(patterns, indent=2)}"
        )),
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
        return {"adjustments": [], "summary": "Failed to parse adjustment response"}


def apply_adjustments(base_prompt: str, adjustments: list[dict]) -> str:
    """Append adjustment instructions to the base scoring prompt."""
    if not adjustments:
        return base_prompt

    additions = ["\n\nADDITIONAL CALIBRATION (from human feedback):"]
    for adj in adjustments:
        additions.append(f"- [{adj.get('type', 'general')}] {adj['instruction']}")

    return base_prompt + "\n".join(additions)
