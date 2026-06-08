"""
GitHub profile lookup for candidate enrichment and cross-validation.

Pulls public repos, languages, and contribution activity.
Works without a token (60 req/hr) or with a token (5000 req/hr).
"""

from __future__ import annotations

import httpx

from config.settings import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


async def lookup_github_profile(github_url: str) -> dict | None:
    """
    Fetch a GitHub user's profile and top repos.
    Returns dict with user info + repos, or None on failure.
    """
    if not github_url:
        return None

    username = github_url.rstrip("/").split("/")[-1]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            user_resp = await client.get(
                f"{GITHUB_API}/users/{username}", headers=_headers()
            )
            user_resp.raise_for_status()
            user_data = user_resp.json()

            repos_resp = await client.get(
                f"{GITHUB_API}/users/{username}/repos",
                params={"sort": "updated", "per_page": 10},
                headers=_headers(),
            )
            repos_resp.raise_for_status()
            repos_data = repos_resp.json()

    except (httpx.HTTPStatusError, httpx.RequestError):
        return None

    repos_summary = [
        {
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "language": r.get("language", ""),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "updated_at": r.get("updated_at", ""),
        }
        for r in repos_data
        if not r.get("fork")  # skip forks — we want original work
    ]

    languages = list({r["language"] for r in repos_summary if r["language"]})

    return {
        "username": user_data.get("login", ""),
        "bio": user_data.get("bio", ""),
        "public_repos": user_data.get("public_repos", 0),
        "followers": user_data.get("followers", 0),
        "repos": repos_summary,
        "languages": languages,
    }
