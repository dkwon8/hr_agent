"""
Resume sorting — moves resumes into accepted/rejected folders on Google Drive.

Candidates who pass the deterministic filter (location + graduation) are moved
to the Accepted folder. Candidates who fail are moved to the Rejected folder.
Scoring and GitHub details are attached as the file's description in Drive.
"""

from __future__ import annotations

import os


GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GDRIVE_RESUME_FOLDER_ID = os.getenv("GDRIVE_RESUME_FOLDER_ID", "")
GDRIVE_ACCEPTED_FOLDER_ID = os.getenv("GDRIVE_ACCEPTED_FOLDER_ID", "")
GDRIVE_REJECTED_FOLDER_ID = os.getenv("GDRIVE_REJECTED_FOLDER_ID", "")


def _get_drive_service():
    if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        return build("drive", "v3", credentials=creds)
    except Exception:
        return None


def _build_accepted_description(c: dict) -> str:
    lines = [
        f"Candidate: {c.get('name', '')}",
        f"University: {c.get('university', '')}",
        f"Major: {c.get('major', '')}",
        f"Location: {c.get('location', '')}",
        f"Graduation: {c.get('graduation_date', '')}",
        "",
        "STATUS: ACCEPTED",
    ]

    score = c.get("quality_score")
    if score is not None:
        lines.append(f"Overall Score: {score}/100")

    best_dept = c.get("best_fit_department", "")
    if best_dept:
        lines.append(f"Best Fit Department: {best_dept}")

    top_depts = c.get("top_3_departments", [])
    if top_depts:
        lines.append("")
        lines.append("Top Department Fits:")
        for i, d in enumerate(top_depts[:3], 1):
            lines.append(
                f"  {i}. {d.get('department', '?')}: {d.get('score', '?')}/100 "
                f"(Skills: {d.get('skills_match', '?')}/40, "
                f"Experience: {d.get('experience_relevance', '?')}/35, "
                f"Potential: {d.get('potential', '?')}/25)"
            )
            reasoning = d.get("reasoning", "")
            if reasoning:
                lines.append(f"     {reasoning[:200]}")

    github = c.get("github_url", "") or c.get("github_profile", "")
    if github:
        lines.append("")
        lines.append(f"GitHub: {github}")

    github_notes = c.get("cross_validation_notes", [])
    if github_notes:
        lines.append("GitHub Notes:")
        for note in github_notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def _build_rejected_description(c: dict) -> str:
    lines = [
        f"Candidate: {c.get('name', '')}",
        f"University: {c.get('university', '')}",
        f"Location: {c.get('location', '')}",
        f"Graduation: {c.get('graduation_date', '')}",
        "",
        "STATUS: REJECTED",
        f"Reason: {c.get('rejection_reason', 'No reason provided')}",
    ]
    return "\n".join(lines)


def _last_name_first(name: str) -> str:
    """Convert 'First Last' to 'Last, First' for alphabetical sorting."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


def sort_and_upload(candidates: list[dict]) -> dict:
    """Move resumes into accepted/rejected folders on Google Drive and add description."""
    service = _get_drive_service()
    if not service:
        return {"error": "Google Drive not configured"}

    if not GDRIVE_ACCEPTED_FOLDER_ID or not GDRIVE_REJECTED_FOLDER_ID:
        return {"error": "Drive folder IDs not set in .env"}

    candidates = sorted(
        candidates,
        key=lambda c: _last_name_first(c.get("name", "")).lower(),
    )

    results = {"accepted": [], "rejected": [], "errors": []}

    for c in candidates:
        file_id = c.get("file_id", "")
        status = c.get("status", "")

        if not file_id:
            results["errors"].append(f"{c.get('name', c.get('id', '?'))}: No file_id")
            continue

        if status == "rejected":
            target_folder = GDRIVE_REJECTED_FOLDER_ID
            description = _build_rejected_description(c)
        else:
            target_folder = GDRIVE_ACCEPTED_FOLDER_ID
            description = _build_accepted_description(c)

        try:
            current = service.files().get(
                fileId=file_id, fields="name, parents"
            ).execute()
            original_name = current.get("name", "")
            current_parents = ",".join(current.get("parents", []))

            candidate_name = c.get("name", "")
            if candidate_name:
                sorted_name = f"{_last_name_first(candidate_name)} - Resume.pdf"
            else:
                sorted_name = original_name

            moved = service.files().update(
                fileId=file_id,
                addParents=target_folder,
                removeParents=current_parents,
                body={"name": sorted_name, "description": description},
                fields="id, webViewLink",
            ).execute()

            entry = {
                "name": c.get("name", original_name),
                "file": sorted_name,
                "drive_id": moved["id"],
                "link": moved.get("webViewLink", ""),
            }

            if status == "rejected":
                entry["reason"] = c.get("rejection_reason", "")
                results["rejected"].append(entry)
            else:
                results["accepted"].append(entry)

        except Exception as e:
            results["errors"].append(f"{c.get('name', c.get('id', '?'))}: {e}")

    return results
