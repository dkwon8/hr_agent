"""
GitHub MCP Server — looks up, discovers, and validates GitHub profiles.

Provides tools for finding candidate GitHub profiles (even when not listed
on their resume), pulling repo/language data, and assessing work authenticity
via commit quality analysis and activity detection.

Run standalone:
    python -m mcp_servers.github.server                    # stdio mode
    python -m mcp_servers.github.server --transport sse    # HTTP mode

Tools:
    lookup_profile     — full profile + repos + authenticity from a GitHub URL
    discover_profile   — find GitHub profile by email or name + university
    check_authenticity — detailed commit quality and activity analysis
"""

from __future__ import annotations

import json
import logging
import os
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp_servers.github.client import (
    lookup_github_profile,
    discover_github_profile,
    search_github_by_email,
    search_github_by_name,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("github_mcp")

# ── Server Setup ──────────────────────────────────────────

mcp = FastMCP(
    "GitHub MCP Server",
    instructions=(
        "Provides tools for looking up and validating GitHub profiles. "
        "Can find profiles by URL, discover them by email or name, "
        "and assess the authenticity of a candidate's GitHub work."
    ),
)

# ── MCP Tools ─────────────────────────────────────────────


@mcp.tool()
async def lookup_profile(
    github_url: str,
) -> str:
    """Look up a GitHub profile by URL. Returns repos, languages, and authenticity signals.

    Authenticity signals include:
    - Original vs forked repo count
    - Recent activity (via Events API)
    - Commit quality ratio (substantive vs low-effort messages)
    - Flags for suspicious patterns

    Args:
        github_url: GitHub profile URL (e.g. "github.com/username" or "https://github.com/username")
    """
    result = await lookup_github_profile(github_url)

    if not result:
        return json.dumps({"error": f"Could not fetch profile: {github_url}"})

    auth = result.get("authenticity", {})

    summary = {
        "username": result.get("username", ""),
        "bio": result.get("bio", ""),
        "public_repos": result.get("public_repos", 0),
        "followers": result.get("followers", 0),
        "account_age_days": result.get("account_age_days"),
        "languages": result.get("languages", []),
        "authenticity": {
            "original_repos": auth.get("original_repo_count", 0),
            "forked_repos": auth.get("forked_repo_count", 0),
            "is_active_last_6mo": auth.get("is_active_last_6mo", False),
            "commits_pushed_6mo": auth.get("commits_pushed_6mo", 0),
            "commit_quality_ratio": auth.get("commit_quality_ratio", 0),
            "substantive_commits": auth.get("substantive_commit_messages", 0),
            "low_effort_commits": auth.get("low_effort_commit_messages", 0),
            "flags": auth.get("flags", []),
        },
        "top_repos": [
            {
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "language": r.get("language", ""),
                "stars": r.get("stars", 0),
                "days_since_update": r.get("days_since_update"),
            }
            for r in result.get("repos", [])[:5]
        ],
    }

    return json.dumps(summary)


@mcp.tool()
async def discover_profile(
    name: str,
    email: str = "",
    university: str = "",
    location: str = "",
) -> str:
    """Find a candidate's GitHub profile when it's not listed on their resume.

    Tries two methods in order:
    1. Email search (high confidence) — matches GitHub accounts by email
    2. Name + university search (lower confidence) — searches by name, cross-references bio

    Args:
        name: Candidate's full name
        email: Email address from resume (most reliable search method)
        university: University name (helps narrow name search results)
        location: City/state (additional signal for name search)
    """
    result = await discover_github_profile(name, email, university, location)

    if not result:
        return json.dumps({
            "found": False,
            "name": name,
            "message": "No GitHub profile found via email or name search",
        })

    return json.dumps({
        "found": True,
        "username": result.get("username", ""),
        "profile_url": result.get("profile_url", ""),
        "match_method": result.get("match_method", "unknown"),
        "confidence": result.get("confidence", "unknown"),
        "total_search_results": result.get("total_results", 0),
        "warning": result.get("warning", ""),
    })


@mcp.tool()
async def check_authenticity(
    github_url: str,
) -> str:
    """Run a detailed authenticity check on a GitHub profile.

    Analyzes commit patterns, message quality, activity timeline, and repo
    composition to assess whether the work is genuine, low-effort, or
    potentially AI-generated.

    Returns a detailed report with:
    - Commit quality breakdown (substantive vs low-effort messages)
    - Activity timeline (events in last 6 months)
    - Per-repo commit statistics
    - Red flags and warnings

    Args:
        github_url: GitHub profile URL
    """
    result = await lookup_github_profile(github_url)

    if not result:
        return json.dumps({"error": f"Could not fetch profile: {github_url}"})

    auth = result.get("authenticity", {})
    repos = result.get("repos", [])

    repo_details = []
    for r in repos[:5]:
        stats = r.get("commit_stats", {})
        repo_details.append({
            "name": r.get("name", ""),
            "language": r.get("language", ""),
            "stars": r.get("stars", 0),
            "size_kb": r.get("size_kb", 0),
            "days_since_update": r.get("days_since_update"),
            "commits_authored": stats.get("authored_by_user", 0),
            "substantive_messages": stats.get("substantive_messages", 0),
            "low_effort_messages": stats.get("low_effort_messages", 0),
            "commit_span_days": stats.get("commit_span_days", 0),
            "most_recent_commit_days_ago": stats.get("most_recent_commit_days_ago"),
        })

    report = {
        "username": result.get("username", ""),
        "account_age_days": result.get("account_age_days"),
        "overall_assessment": {
            "is_active": auth.get("is_active_last_6mo", False),
            "commit_quality_ratio": auth.get("commit_quality_ratio", 0),
            "original_repos": auth.get("original_repo_count", 0),
            "forked_repos": auth.get("forked_repo_count", 0),
            "total_stars": auth.get("total_stars_received", 0),
            "flags": auth.get("flags", []),
        },
        "activity_summary": {
            "events_last_6mo": auth.get("events_last_6mo", 0),
            "commits_pushed_6mo": auth.get("commits_pushed_6mo", 0),
            "active_repos": auth.get("active_repos_from_events", []),
        },
        "repo_details": repo_details,
    }

    return json.dumps(report)


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GitHub MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
    )
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--host", default="localhost")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
