"""
GitHub profile lookup for candidate enrichment and cross-validation.

Pulls public repos, languages, commit activity, and authenticity signals.
Works without a token (60 req/hr) or with a token (5000 req/hr).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


async def _request_with_retry(
    client: httpx.AsyncClient, url: str, max_retries: int = 2, **kwargs
) -> httpx.Response:
    """GET with retry on rate-limit (403/429) responses."""
    for attempt in range(max_retries + 1):
        resp = await client.get(url, headers=_headers(), **kwargs)
        if resp.status_code in (403, 429) and attempt < max_retries:
            retry_after = int(resp.headers.get("Retry-After", str(2 * (attempt + 1))))
            await asyncio.sleep(min(retry_after, 10))
            continue
        return resp
    return resp


def _days_since(iso_date: str) -> int | None:
    """Return days since an ISO date string, or None if unparseable."""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, AttributeError):
        return None


def _is_low_effort_message(msg: str) -> bool:
    """Check if a commit message suggests low-effort or auto-generated work."""
    cleaned = msg.strip().lower().split("\n")[0]

    if len(cleaned) <= 3:
        return True

    low_effort_exact = {
        "update readme.md", "initial commit", "first commit",
        "update", "fix", "changes", "updated", "added files",
        "wip", "temp", "test", "asdf", "stuff", "minor",
        ".", "..", "no message", "commit", "save", "push",
        "add files via upload", "delete", "rename",
    }
    if cleaned in low_effort_exact:
        return True

    if cleaned.startswith("update ") and len(cleaned.split()) <= 3:
        return True

    return False


async def _get_recent_events(client: httpx.AsyncClient, username: str) -> dict:
    """Use GitHub Events API to get actual recent activity (last 90 days)."""
    try:
        resp = await _request_with_retry(
            client,
            f"{GITHUB_API}/users/{username}/events",
            params={"per_page": 100},
        )
        if resp.status_code != 200:
            return {}

        events = resp.json()
        now = datetime.now(timezone.utc)

        push_events = []
        recent_repos = set()
        for e in events:
            created = e.get("created_at", "")
            days_ago = _days_since(created)
            if days_ago is not None and days_ago <= 180:
                if e.get("type") == "PushEvent":
                    push_events.append(e)
                    recent_repos.add(e.get("repo", {}).get("name", ""))

        total_commits_pushed = 0
        for pe in push_events:
            commits = pe.get("payload", {}).get("commits", [])
            total_commits_pushed += len(commits)

        recent_event_types = {}
        for e in events:
            days_ago = _days_since(e.get("created_at", ""))
            if days_ago is not None and days_ago <= 180:
                etype = e.get("type", "unknown")
                recent_event_types[etype] = recent_event_types.get(etype, 0) + 1

        return {
            "push_events_6mo": len(push_events),
            "commits_pushed_6mo": total_commits_pushed,
            "active_repos_from_events": list(recent_repos),
            "event_types_6mo": recent_event_types,
            "total_events_6mo": sum(recent_event_types.values()),
        }
    except (httpx.HTTPStatusError, httpx.RequestError):
        return {}


async def _get_repo_commit_stats(client: httpx.AsyncClient, username: str, repo_name: str) -> dict:
    """Get commit activity for a single repo to assess authenticity."""
    try:
        commits_resp = await _request_with_retry(
            client,
            f"{GITHUB_API}/repos/{username}/{repo_name}/commits",
            params={"per_page": 30},
        )
        if commits_resp.status_code != 200:
            return {}

        commits = commits_resp.json()
        if not commits:
            return {"total_recent_commits": 0}

        authored_commits = [
            c for c in commits
            if c.get("author") and c["author"].get("login", "").lower() == username.lower()
        ]

        messages = [c.get("commit", {}).get("message", "") for c in authored_commits[:15]]
        low_effort = sum(1 for m in messages if _is_low_effort_message(m))
        substantive = len(messages) - low_effort

        commit_dates = []
        for c in authored_commits:
            date_str = c.get("commit", {}).get("author", {}).get("date", "")
            if date_str:
                commit_dates.append(date_str)

        span_days = 0
        if len(commit_dates) >= 2:
            try:
                first = datetime.fromisoformat(commit_dates[-1].replace("Z", "+00:00"))
                last = datetime.fromisoformat(commit_dates[0].replace("Z", "+00:00"))
                span_days = (last - first).days
            except ValueError:
                pass

        most_recent_days = _days_since(commit_dates[0]) if commit_dates else None

        return {
            "total_recent_commits": len(commits),
            "authored_by_user": len(authored_commits),
            "low_effort_messages": low_effort,
            "substantive_messages": substantive,
            "commit_span_days": span_days,
            "most_recent_commit_days_ago": most_recent_days,
        }
    except (httpx.HTTPStatusError, httpx.RequestError):
        return {}


async def search_github_by_email(email: str) -> dict | None:
    """Search GitHub for a user by their email address. Most reliable method."""
    if not email:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{GITHUB_API}/search/users",
                params={"q": f"{email} in:email", "per_page": 3},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            items = data.get("items", [])
            if items:
                return {
                    "username": items[0].get("login", ""),
                    "profile_url": items[0].get("html_url", ""),
                    "match_method": "email",
                    "confidence": "high",
                    "total_results": data.get("total_count", 0),
                }
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None


async def search_github_by_name(name: str, university: str = "", location: str = "") -> dict | None:
    """Search GitHub for a user by name + university/location. Less reliable, may return wrong person."""
    if not name:
        return None

    query_parts = [f"{name} in:name"]
    if university:
        uni_short = university.split(" of ")[-1].split(" University")[0].strip()
        query_parts.append(f"{uni_short} in:bio")

    query = " ".join(query_parts)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{GITHUB_API}/search/users",
                params={"q": query, "per_page": 5},
                headers=_headers(),
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            items = data.get("items", [])
            total = data.get("total_count", 0)

            if not items:
                return None

            if total == 1:
                return {
                    "username": items[0].get("login", ""),
                    "profile_url": items[0].get("html_url", ""),
                    "match_method": "name_search",
                    "confidence": "high",
                    "total_results": total,
                }

            # Multiple results — try to narrow down by checking bios
            for item in items[:3]:
                user_resp = await client.get(
                    f"{GITHUB_API}/users/{item['login']}",
                    headers=_headers(),
                )
                if user_resp.status_code != 200:
                    continue
                user_data = user_resp.json()
                bio = (user_data.get("bio") or "").lower()
                user_location = (user_data.get("location") or "").lower()
                user_name = (user_data.get("name") or "").lower()

                name_match = name.lower() in user_name or user_name in name.lower()
                uni_match = university and any(
                    word.lower() in bio for word in university.split() if len(word) > 3
                )
                loc_match = location and any(
                    word.lower() in user_location for word in location.split(",")[0].split() if len(word) > 3
                )

                if name_match and (uni_match or loc_match):
                    return {
                        "username": item.get("login", ""),
                        "profile_url": item.get("html_url", ""),
                        "match_method": "name_search",
                        "confidence": "medium" if uni_match else "low",
                        "total_results": total,
                        "matched_on": [s for s in ["name", "university" if uni_match else None, "location" if loc_match else None] if s],
                    }

            # No confident match
            return {
                "username": items[0].get("login", ""),
                "profile_url": items[0].get("html_url", ""),
                "match_method": "name_search",
                "confidence": "low",
                "total_results": total,
                "warning": f"Multiple results ({total}) — top result may not be the correct person",
            }

    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None


async def discover_github_profile(name: str, email: str = "", university: str = "", location: str = "") -> dict | None:
    """
    Try to find a candidate's GitHub profile using email (primary) then name search (fallback).
    Returns search result with confidence level, or None if not found.
    """
    # Method 1: email lookup (most reliable)
    if email:
        result = await search_github_by_email(email)
        if result:
            return result

    # Method 2: name + university/location search (less reliable)
    result = await search_github_by_name(name, university, location)
    return result


async def lookup_github_profile(github_url: str) -> dict | None:
    """
    Fetch a GitHub user's profile, top repos, and authenticity signals.
    Returns dict with user info + repos + quality assessment, or None on failure.
    """
    if not github_url:
        return None

    url = github_url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    username = url.rstrip("/").split("/")[-1]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            user_resp = await _request_with_retry(
                client, f"{GITHUB_API}/users/{username}"
            )
            if user_resp.status_code != 200:
                return None
            user_data = user_resp.json()

            repos_resp = await _request_with_retry(
                client,
                f"{GITHUB_API}/users/{username}/repos",
                params={"sort": "updated", "per_page": 10},
            )
            if repos_resp.status_code != 200:
                return None
            repos_data = repos_resp.json()

            # Get recent activity from Events API (most reliable for "active" check)
            recent_activity = await _get_recent_events(client, username)

            # Get commit stats for top 3 non-fork repos
            original_repos = [r for r in repos_data if not r.get("fork")]
            commit_stats = {}
            for repo in original_repos[:3]:
                stats = await _get_repo_commit_stats(client, username, repo["name"])
                if stats:
                    commit_stats[repo["name"]] = stats

    except (httpx.HTTPStatusError, httpx.RequestError):
        return None

    repos_summary = []
    for r in repos_data:
        if r.get("fork"):
            continue

        days_since_update = _days_since(r.get("updated_at", ""))
        repo_entry = {
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "language": r.get("language", ""),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "updated_at": r.get("updated_at", ""),
            "days_since_update": days_since_update,
            "size_kb": r.get("size", 0),
        }
        if r["name"] in commit_stats:
            repo_entry["commit_stats"] = commit_stats[r["name"]]
        repos_summary.append(repo_entry)

    languages = list({r["language"] for r in repos_summary if r["language"]})

    # Compute authenticity signals
    total_authored = sum(s.get("authored_by_user", 0) for s in commit_stats.values())
    total_low_effort = sum(s.get("low_effort_messages", 0) for s in commit_stats.values())
    total_substantive = sum(s.get("substantive_messages", 0) for s in commit_stats.values())
    total_stars = sum(r.get("stars", 0) for r in repos_summary)

    # Use Events API for activity — much more reliable than repo updated_at
    events_6mo = recent_activity.get("total_events_6mo", 0)
    commits_pushed_6mo = recent_activity.get("commits_pushed_6mo", 0)
    active_repos_from_events = recent_activity.get("active_repos_from_events", [])

    # Fallback: also check repo updated_at
    repos_with_recent_update = sum(1 for r in repos_summary if (r.get("days_since_update") or 999) < 180)
    is_active = events_6mo > 0 or repos_with_recent_update > 0

    authenticity = {
        "original_repo_count": len(repos_summary),
        "forked_repo_count": sum(1 for r in repos_data if r.get("fork")),
        "total_stars_received": total_stars,
        "is_active_last_6mo": is_active,
        "events_last_6mo": events_6mo,
        "commits_pushed_6mo": commits_pushed_6mo,
        "active_repos_from_events": active_repos_from_events,
        "commits_authored_in_top_repos": total_authored,
        "low_effort_commit_messages": total_low_effort,
        "substantive_commit_messages": total_substantive,
        "commit_quality_ratio": round(total_substantive / max(total_substantive + total_low_effort, 1), 2),
    }

    # Flag issues — use both events and repo data to avoid false positives
    flags = []
    if authenticity["original_repo_count"] == 0:
        flags.append("No original repos — all forks")
    if not is_active and repos_summary:
        flags.append("No activity in the last 6 months (checked events + repo timestamps)")
    if authenticity["commit_quality_ratio"] < 0.3 and total_substantive + total_low_effort > 5:
        flags.append("Majority of commit messages are low-effort (e.g. 'update', 'fix', 'asdf')")
    if total_authored == 0 and commit_stats:
        flags.append("No commits authored by this user in their top repos")
    if authenticity["forked_repo_count"] > len(repos_summary) * 2 and len(repos_summary) > 0:
        flags.append("Significantly more forks than original repos — may be collecting rather than building")

    authenticity["flags"] = flags

    account_age_days = _days_since(user_data.get("created_at", ""))

    return {
        "username": user_data.get("login", ""),
        "bio": user_data.get("bio", ""),
        "public_repos": user_data.get("public_repos", 0),
        "followers": user_data.get("followers", 0),
        "account_age_days": account_age_days,
        "repos": repos_summary,
        "languages": languages,
        "authenticity": authenticity,
    }
