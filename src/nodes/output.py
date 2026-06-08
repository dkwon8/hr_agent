"""
Phase 5 — Output & Reporting

Generates a ranked report of selected candidates and a pipeline summary.
Writes results to a JSON file for review.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime

from src.state import PipelineState, CandidateStatus
from src.utils.tracing import get_tracer


def _candidate_to_report_entry(c) -> dict:
    entry = {
        "rank": 0,
        "id": c.id,
        "name": c.name,
        "location": c.location,
        "university": c.university,
        "major": c.major,
        "graduation_date": c.graduation_date,
        "degree_level": c.degree_level,
        "quality_score": c.quality_score,
        "best_fit_department": c.best_fit_department,
        "top_3_departments": c.top_3_departments,
        "quality_reasoning": c.quality_reasoning,
        "fit_breakdown": c.fit_breakdown,
        "department_scores": c.department_scores,
        "skills": c.skills,
        "experience_summary": c.experience_summary,
        "linkedin_url": c.linkedin_url,
        "github_url": c.github_url,
        "cross_validation_notes": c.cross_validation_notes,
        "graduation_verified": c.graduation_verified,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
    }
    if c.was_flagged:
        entry["was_flagged"] = True
        entry["flag_reason"] = "Graduation date mismatch between resume and LinkedIn"
    return entry


async def generate_output(state: PipelineState) -> dict:
    candidates = state["candidates"]

    selected = sorted(
        [c for c in candidates if c.status == CandidateStatus.SELECTED],
        key=lambda c: c.quality_score,
        reverse=True,
    )

    rejected = [c for c in candidates if c.status == CandidateStatus.REJECTED]
    flagged = [c for c in candidates if c.status == CandidateStatus.FLAGGED]

    # Build the ranked report
    report_entries = []
    for rank, c in enumerate(selected, start=1):
        entry = _candidate_to_report_entry(c)
        entry["rank"] = rank
        report_entries.append(entry)

    summary = {
        "pipeline_run": datetime.now().isoformat(),
        "total_resumes": len(candidates),
        "passed_deterministic": len(
            [c for c in candidates if c.status in {
                CandidateStatus.PASSED_DETERMINISTIC,
                CandidateStatus.PASSED_CROSS_VALIDATION,
                CandidateStatus.FLAGGED,
                CandidateStatus.RANKED,
                CandidateStatus.SELECTED,
            }]
        ),
        "flagged_cross_validation": len(flagged),
        "total_scored": len(
            [c for c in candidates if c.status in {CandidateStatus.RANKED, CandidateStatus.SELECTED}]
        ),
        "total_selected": len(selected),
        "total_rejected": len(rejected),
        "top_score": selected[0].quality_score if selected else None,
        "bottom_selected_score": selected[-1].quality_score if selected else None,
        "errors": state.get("errors", []),
    }

    # Write report to file
    output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"report_{timestamp}.json")

    rejected_entries = []
    for c in rejected:
        rejected_entries.append({
            "id": c.id,
            "name": c.name,
            "location": c.location,
            "graduation_date": c.graduation_date,
            "rejection_reason": c.rejection_reason,
            "rejected_in_phase": c.current_phase,
        })

    report = {
        "summary": summary,
        "selected_candidates": report_entries,
        "rejected_candidates": rejected_entries,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Generate interview scheduling CSV
    schedule_path = os.path.join(output_dir, f"interview_schedule_{timestamp}.csv")
    with open(schedule_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Rank", "Name", "Email", "University", "Major",
            "Best Fit Department", "Score", "Also Fits",
            "Graduation", "Flagged", "LinkedIn", "GitHub",
        ])
        for c in selected:
            others = [d["department"] for d in c.top_3_departments if d["department"] != c.best_fit_department]
            writer.writerow([
                report_entries[selected.index(c)]["rank"],
                c.name,
                c.email,
                c.university,
                c.major,
                c.best_fit_department,
                c.quality_score,
                " | ".join(others) if others else "",
                c.graduation_date,
                "Yes" if c.was_flagged else "",
                c.linkedin_url,
                c.github_url,
            ])

    print(f"\n{'='*60}")
    print(f"[Phase 5] PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Total resumes processed: {len(candidates)}")
    print(f"  Selected for interview:  {len(selected)}")
    print(f"  Rejected:                {len(rejected)}")
    print(f"  Flagged:                 {len(flagged)}")
    if selected:
        print(f"  Top score:               {selected[0].quality_score} ({selected[0].best_fit_department})")
        print(f"  Cutoff score:            {selected[-1].quality_score} ({selected[-1].best_fit_department})")
        print(f"\n  Top candidates:")
        for i, c in enumerate(selected[:10], 1):
            others = [d["department"] for d in c.top_3_departments if d["department"] != c.best_fit_department]
            also_fits = ", ".join(others) if others else "N/A"
            print(f"    {i}. {c.name} — {c.quality_score}/100 — Best: {c.best_fit_department} | Also fits: {also_fits}")
    print(f"\n  Report saved to:         {report_path}")
    print(f"  Interview CSV saved to:  {schedule_path}")
    print(f"{'='*60}\n")

    tracer = get_tracer()
    if tracer:
        tracer.log_report(report, report_path)

    return {
        "candidates": candidates,
        "current_phase": "complete",
        "summary": summary,
        "errors": [],
    }
