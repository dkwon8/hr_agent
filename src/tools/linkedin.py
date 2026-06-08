"""
LinkedIn profile lookup via RapidAPI wrapper.

Used in cross-validation to verify graduation dates and pull profile data.
Falls back gracefully when API is unavailable or rate-limited.
"""

from __future__ import annotations

import httpx

from config.settings import RAPIDAPI_KEY

RAPIDAPI_LINKEDIN_HOST = "linkedin-api8.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_LINKEDIN_HOST}"


async def lookup_linkedin_profile(linkedin_url: str) -> dict | None:
    """
    Fetch a LinkedIn profile via the RapidAPI LinkedIn wrapper.
    Returns parsed profile dict or None if lookup fails.
    """
    if not RAPIDAPI_KEY:
        return None

    if not linkedin_url:
        return None

    # Extract the profile identifier from the URL
    # e.g. "https://linkedin.com/in/johndoe" → "johndoe"
    profile_id = linkedin_url.rstrip("/").split("/")[-1]

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_LINKEDIN_HOST,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{RAPIDAPI_BASE_URL}/get-profile-data-by-url",
                params={"url": linkedin_url},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return {"error": "rate_limited"}
        return {"error": f"http_{e.response.status_code}"}
    except httpx.RequestError:
        return {"error": "connection_failed"}


def extract_graduation_from_linkedin(profile_data: dict) -> str:
    """
    Pull the most recent education end date from a LinkedIn profile response.
    Returns YYYY-MM format or empty string.
    """
    if not profile_data or "error" in profile_data:
        return ""

    education = profile_data.get("education", [])
    if not education:
        return ""

    latest = None
    latest_sort_key = (0, 0)

    for entry in education:
        end_date = entry.get("end", {})
        year = end_date.get("year")
        if not year:
            continue
        month = end_date.get("month", 5)
        if (year, month) > latest_sort_key:
            latest_sort_key = (year, month)
            latest = entry

    if latest:
        year, month = latest_sort_key
        return f"{year}-{int(month):02d}"
    return ""


def extract_headline(profile_data: dict) -> str:
    if not profile_data or "error" in profile_data:
        return ""
    return profile_data.get("headline", "")
