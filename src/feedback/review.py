"""
Human review interface — lets reviewers provide feedback on pipeline output.

Usage:
    python -m src.feedback.review --report data/report_20260604.json
    python -m src.feedback.review --report data/report_20260604.json --auto-tune
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from src.feedback.store import FeedbackStore, FeedbackEntry
from src.feedback.analyzer import analyze_patterns, generate_prompt_adjustments, apply_adjustments
from src.nodes.llm_judge import JUDGE_SYSTEM_PROMPT
from src.utils.helpers import TokenTracker


def load_report(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def review_candidates(report: dict, store: FeedbackStore, run_id: str = ""):
    """Interactive review of selected candidates."""
    candidates = report.get("selected_candidates", [])
    if not candidates:
        print("No selected candidates in report.")
        return

    print(f"\n{'='*60}")
    print(f"  CANDIDATE REVIEW — {len(candidates)} candidates")
    print(f"{'='*60}\n")

    for c in candidates:
        print(f"\n--- Candidate: {c['name']} (#{c['rank']}) ---")
        print(f"  Score: {c['quality_score']}/100")
        print(f"  Best fit: {c.get('best_fit_department', 'N/A')}")
        print(f"  Skills: {', '.join(c.get('skills', []))}")
        print(f"  Reasoning: {c.get('quality_reasoning', 'N/A')[:200]}")

        if c.get("was_flagged"):
            print(f"  ⚠ FLAGGED: {c.get('flag_reason', '')}")

        print()
        action = input("  Action [a]pprove / [r]eject / [s]core adjust / [n]ext / [q]uit: ").strip().lower()

        if action == "q":
            break
        elif action == "n":
            continue
        elif action in ("a", "approve"):
            store.add(FeedbackEntry(
                candidate_id=c["id"],
                candidate_name=c["name"],
                department=c.get("best_fit_department", ""),
                llm_score=c["quality_score"],
                human_score=c["quality_score"],
                action="approve",
                run_id=run_id,
            ))
            print("  → Approved")
        elif action in ("r", "reject"):
            reason = input("  Reason for rejection: ").strip()
            store.add(FeedbackEntry(
                candidate_id=c["id"],
                candidate_name=c["name"],
                department=c.get("best_fit_department", ""),
                llm_score=c["quality_score"],
                human_score=0,
                action="reject",
                reason=reason,
                run_id=run_id,
            ))
            print("  → Rejected")
        elif action in ("s", "score"):
            try:
                new_score = float(input("  Your score (0-100): ").strip())
                reason = input("  Reason for adjustment: ").strip()
                store.add(FeedbackEntry(
                    candidate_id=c["id"],
                    candidate_name=c["name"],
                    department=c.get("best_fit_department", ""),
                    llm_score=c["quality_score"],
                    human_score=new_score,
                    action="adjust",
                    reason=reason,
                    run_id=run_id,
                ))
                print(f"  → Adjusted: {c['quality_score']} → {new_score}")
            except ValueError:
                print("  → Invalid score, skipping")

    print(f"\n{'='*60}")
    summary = store.summary()
    print(f"  Feedback summary: {summary['total']} entries")
    print(f"  Approvals: {summary.get('approvals', 0)}")
    print(f"  Rejections: {summary.get('rejections', 0)}")
    print(f"  Adjustments: {summary.get('adjustments', 0)}")
    if summary.get("avg_score_adjustment"):
        print(f"  Avg adjustment: {summary['avg_score_adjustment']:+.1f} ({summary['bias_direction']})")
    print(f"{'='*60}\n")


async def auto_tune(store: FeedbackStore):
    """Analyze feedback patterns and generate prompt adjustments."""
    patterns = analyze_patterns(store)

    if not patterns.get("sufficient_data"):
        print(f"\n{patterns.get('message', 'Insufficient data')}")
        return

    print(f"\n{'='*60}")
    print("  FEEDBACK ANALYSIS")
    print(f"{'='*60}")

    if patterns.get("department_issues"):
        print("\n  Department issues detected:")
        for dept, info in patterns["department_issues"].items():
            print(f"    {dept}: {info['direction']} by ~{abs(info['avg_score_diff'])} pts "
                  f"(rejection rate: {info['rejection_rate']}%)")

    if patterns.get("skill_issues"):
        print("\n  Skill weighting issues:")
        for skill, info in patterns["skill_issues"].items():
            print(f"    {skill}: {info['direction']} (avg adjustment: {info['avg_adjustment']:+.1f})")

    if patterns.get("systematic_bias"):
        bias = patterns["systematic_bias"]
        print(f"\n  Systematic bias: {bias['direction']} by ~{bias['magnitude']:.1f} pts")

    print("\n  Generating prompt adjustments...")
    tracker = TokenTracker()
    adjustments = await generate_prompt_adjustments(JUDGE_SYSTEM_PROMPT, patterns, tracker)

    if adjustments.get("adjustments"):
        print(f"\n  Proposed adjustments ({len(adjustments['adjustments'])}):")
        for adj in adjustments["adjustments"]:
            print(f"    [{adj['type']}] {adj['instruction']}")
            print(f"      Why: {adj['reasoning']}")

        confirm = input("\n  Apply these adjustments? [y/n]: ").strip().lower()
        if confirm == "y":
            new_prompt = apply_adjustments(JUDGE_SYSTEM_PROMPT, adjustments["adjustments"])
            prompt_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "feedback", "tuned_prompt.txt"
            )
            os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
            with open(prompt_path, "w") as f:
                f.write(new_prompt)
            print(f"  → Tuned prompt saved to: {prompt_path}")
            print(f"  → The next pipeline run will use the tuned prompt.")
        else:
            print("  → Adjustments discarded.")
    else:
        print(f"  No adjustments needed: {adjustments.get('summary', '')}")

    print(f"\n  {tracker.summary('Auto-tune')}")
    print(f"{'='*60}\n")


import os


def main():
    parser = argparse.ArgumentParser(description="Review pipeline output and provide feedback")
    parser.add_argument("--report", required=True, help="Path to pipeline report JSON")
    parser.add_argument("--auto-tune", action="store_true", help="Analyze feedback and generate prompt adjustments")
    parser.add_argument("--summary", action="store_true", help="Show feedback summary only")
    parser.add_argument("--run-id", default="", help="MLflow run ID to associate feedback with")
    args = parser.parse_args()

    store = FeedbackStore()

    if args.summary:
        summary = store.summary()
        print(json.dumps(summary, indent=2))
        return

    if args.auto_tune:
        asyncio.run(auto_tune(store))
        return

    report = load_report(args.report)
    review_candidates(report, store, run_id=args.run_id)


if __name__ == "__main__":
    main()
