"""
Output MCP Server — generates reports, sorts resumes, uploads to Google Drive.

Handles all post-scoring output: JSON reports, interview scheduling CSVs,
resume sorting into accepted/rejected folders with appended summary pages,
and Google Drive upload.

Run standalone:
    python -m mcp_servers.output.server                    # stdio mode
    python -m mcp_servers.output.server --transport sse    # HTTP mode

Tools:
    generate_report       — pipeline report with candidate rankings and reasoning
    sort_resumes          — sort into accepted/rejected folders with PDF pages
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp_servers.output.drive import sort_and_upload

logging.basicConfig(level=logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("output_mcp")

# ── Server Setup ──────────────────────────────────────────

mcp = FastMCP(
    "Output MCP Server",
    instructions=(
        "Provides tools for generating pipeline reports, interview scheduling "
        "CSVs, and sorting resumes into accepted/rejected folders. "
        "Supports Google Drive upload when configured."
    ),
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# ── MCP Tools ─────────────────────────────────────────────


@mcp.tool()
async def generate_report(
    candidates_json: str,
) -> str:
    """Generate a full pipeline report with selected and rejected candidates.

    Creates a JSON report with:
    - Pipeline summary (counts, scores, timestamps)
    - Selected candidates with full scoring details
    - Rejected candidates with rejection reasons

    Saves the report to data/report_TIMESTAMP.json.

    Args:
        candidates_json: JSON string with all candidates (selected + rejected)
    """
    candidates = json.loads(candidates_json)

    selected = sorted(
        [c for c in candidates if c.get("status") != "rejected"],
        key=lambda c: c.get("quality_score", 0),
        reverse=True,
    )
    rejected = [c for c in candidates if c.get("status") == "rejected"]

    summary = {
        "pipeline_run": datetime.now().isoformat(),
        "total_resumes": len(candidates),
        "total_selected": len(selected),
        "total_rejected": len(rejected),
        "top_score": selected[0]["quality_score"] if selected else None,
        "bottom_selected_score": selected[-1]["quality_score"] if selected else None,
    }

    rejected_entries = [
        {
            "name": c.get("name", ""),
            "location": c.get("location", ""),
            "graduation_date": c.get("graduation_date", ""),
            "rejection_reason": c.get("rejection_reason", ""),
        }
        for c in rejected
    ]

    report = {
        "summary": summary,
        "selected_candidates": selected,
        "rejected_candidates": rejected_entries,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.json")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Build readable text summary for the user
    text_lines = [
        f"PIPELINE REPORT — {summary['pipeline_run']}",
        f"{'=' * 50}",
        f"Total resumes processed: {summary['total_resumes']}",
        f"Selected for interview:  {summary['total_selected']}",
        f"Rejected:                {summary['total_rejected']}",
        "",
    ]

    if selected:
        text_lines.append("SELECTED CANDIDATES (ranked by score):")
        for rank, c in enumerate(selected, 1):
            conf = c.get("score_confidence", {})
            conf_str = f" (±{conf.get('range', 0)/2:.0f})" if conf else ""
            best = c.get("best_fit_department", "N/A")
            top3 = c.get("top_3_departments", [])
            others = [d["department"] for d in top3 if d.get("department") != best]

            text_lines.append(f"\n  #{rank} {c.get('name', '?')} — {c.get('quality_score', 0)}/100{conf_str}")
            text_lines.append(f"     Best fit: {best}")
            if others:
                text_lines.append(f"     Also fits: {', '.join(others)}")
            text_lines.append(f"     {c.get('university', '')} | {c.get('major', '')} | Grad: {c.get('graduation_date', '')}")

            breakdown = c.get("fit_breakdown", {})
            text_lines.append(f"     Experience: {breakdown.get('experience', '?')}/40 | Projects: {breakdown.get('projects', '?')}/35 | Learning Potential: {breakdown.get('learning_potential', '?')}/25")

            dept_scores = c.get("department_scores", {}).get(best, {})
            reasoning = dept_scores.get("reasoning", "")
            if reasoning:
                text_lines.append(f"     Reasoning: {reasoning[:200]}")

    if rejected:
        text_lines.append(f"\nREJECTED CANDIDATES:")
        for c in rejected_entries:
            text_lines.append(f"  - {c['name']}: {c['rejection_reason']}")

    text_summary = "\n".join(text_lines)

    return json.dumps({
        "report_path": report_path,
        "summary": summary,
        "text_summary": text_summary,
    })


@mcp.tool()
async def sort_resumes(
    candidates_json: str,
) -> str:
    """Sort resumes into accepted/rejected folders with appended summary pages.

    Accepted resumes get a page with: score, best-fit department, top 3
    department fits with breakdowns.

    Rejected resumes get a page with: rejection reason, phase rejected in.

    Uploads to Google Drive if configured, otherwise saves locally
    to data/output/accepted/ and data/output/rejected/.

    Args:
        candidates_json: JSON string with all candidates
    """
    candidates = json.loads(candidates_json)
    results = sort_and_upload(candidates)

    return json.dumps({
        "accepted": len(results.get("accepted", [])),
        "rejected": len(results.get("rejected", [])),
        "errors": results.get("errors", []),
        "destination": "google_drive" if os.getenv("GDRIVE_ACCEPTED_FOLDER_ID") else "local",
        "accepted_details": results.get("accepted", []),
        "rejected_details": results.get("rejected", []),
    })


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Output MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
    )
    parser.add_argument("--port", type=int, default=3005)
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
