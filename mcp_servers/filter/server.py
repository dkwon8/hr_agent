"""
Filter MCP Server — applies deterministic rules to filter candidates.

Pure rule-based filtering, no LLM calls, zero API cost. Checks candidate
location against target areas and graduation date against hiring window.

Run standalone:
    python -m mcp_servers.filter.server                    # stdio mode
    python -m mcp_servers.filter.server --transport sse    # HTTP mode

Tools:
    check_location    — verify candidate location matches target areas
    check_graduation  — verify graduation date is within hiring window
    filter_candidates — apply all rules to a list of candidates
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp_servers.filter.rules import check_location, check_graduation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("filter_mcp")

# ── Server Setup ──────────────────────────────────────────

mcp = FastMCP(
    "Filter MCP Server",
    instructions=(
        "Provides deterministic filtering tools for candidate screening. "
        "Checks location (Boston, Raleigh, Remote) and graduation date "
        "against the hiring window. No LLM needed — instant, zero cost."
    ),
)

# Default config from environment
DEFAULT_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "Boston,Raleigh,Remote").split(",")
]
DEFAULT_GRAD_EARLIEST = os.getenv("GRADUATION_EARLIEST", "2025-12")
DEFAULT_GRAD_LATEST = os.getenv("GRADUATION_LATEST", "2026-08")

# ── MCP Tools ─────────────────────────────────────────────


@mcp.tool()
async def check_candidate_location(
    location: str,
    target_locations: Optional[str] = None,
) -> str:
    """Check if a candidate's location matches the target hiring areas.

    Uses location aliases to handle variations (e.g. "Boston, MA" matches
    "Boston", "Boston MA", "Boston Massachusetts"). Handles "Remote" as
    a special case.

    Args:
        location: Candidate's location from their resume
        target_locations: Comma-separated target areas (default: from .env)
    """
    targets = (
        [t.strip().lower() for t in target_locations.split(",")]
        if target_locations
        else DEFAULT_LOCATIONS
    )

    result = check_location(location, targets)

    return json.dumps({
        "location": location,
        "target_areas": targets,
        "passed": result is None,
        "reason": result or "Location matches target areas",
    })


@mcp.tool()
async def check_candidate_graduation(
    graduation_date: str,
    earliest: Optional[str] = None,
    latest: Optional[str] = None,
) -> str:
    """Check if a candidate's graduation date falls within the hiring window.

    Graduation date should be in YYYY-MM format (e.g. "2026-05").

    Args:
        graduation_date: Candidate's graduation date in YYYY-MM format
        earliest: Window start in YYYY-MM (default: from .env)
        latest: Window end in YYYY-MM (default: from .env)
    """
    grad_earliest = earliest or DEFAULT_GRAD_EARLIEST
    grad_latest = latest or DEFAULT_GRAD_LATEST

    result = check_graduation(graduation_date, grad_earliest, grad_latest)

    return json.dumps({
        "graduation_date": graduation_date,
        "window": f"{grad_earliest} to {grad_latest}",
        "passed": result is None,
        "reason": result or "Graduation date is within hiring window",
    })


@mcp.tool()
async def filter_candidates(
    candidates_json: str,
    target_locations: Optional[str] = None,
    graduation_earliest: Optional[str] = None,
    graduation_latest: Optional[str] = None,
) -> str:
    """Apply all deterministic filters to a list of candidates.

    Checks each candidate's location and graduation date. Returns
    separate lists of passed and rejected candidates with reasons.

    Args:
        candidates_json: JSON string of candidate list (each with "location" and "graduation_date" fields)
        target_locations: Comma-separated target areas (default: from .env)
        graduation_earliest: Window start YYYY-MM (default: from .env)
        graduation_latest: Window end YYYY-MM (default: from .env)
    """
    candidates = json.loads(candidates_json)
    targets = (
        [t.strip().lower() for t in target_locations.split(",")]
        if target_locations
        else DEFAULT_LOCATIONS
    )
    earliest = graduation_earliest or DEFAULT_GRAD_EARLIEST
    latest = graduation_latest or DEFAULT_GRAD_LATEST

    passed = []
    rejected = []

    for c in candidates:
        reasons = []

        loc_result = check_location(c.get("location", ""), targets)
        if loc_result:
            reasons.append(loc_result)

        grad_result = check_graduation(c.get("graduation_date", ""), earliest, latest)
        if grad_result:
            reasons.append(grad_result)

        if reasons:
            rejected.append({
                **c,
                "status": "rejected",
                "rejection_reason": "; ".join(reasons),
            })
        else:
            passed.append({
                **c,
                "status": "passed_deterministic",
            })

    return json.dumps({
        "total": len(candidates),
        "passed": len(passed),
        "rejected": len(rejected),
        "passed_candidates": passed,
        "rejected_candidates": rejected,
    })


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Filter MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
    )
    parser.add_argument("--port", type=int, default=3003)
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
