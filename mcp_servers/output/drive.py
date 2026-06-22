"""
Resume sorting — moves resumes into accepted/rejected folders on Google Drive.

Candidates who pass the deterministic filter (location + graduation) are moved
to the Accepted folder. Candidates who fail are moved to the Rejected folder.
Scoring and GitHub details are attached as the file's description in Drive.

Each pipeline run creates a timestamped folder (e.g. Run_2026-06-22_14-30)
with Accepted/, Rejected/, and Unfiltered/ subfolders. Original resumes are
copied to Unfiltered/ before being moved and modified.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("output_mcp")


GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GDRIVE_RESUME_FOLDER_ID = os.getenv("GDRIVE_RESUME_FOLDER_ID", "")
GDRIVE_RUNS_PARENT_FOLDER_ID = os.getenv("GDRIVE_RUNS_PARENT_FOLDER_ID", "")

LOCAL_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output")


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


def _create_drive_folder(service, name: str, parent_id: str) -> str:
    """Create a folder in Google Drive and return its ID."""
    folder = service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
    ).execute()
    return folder["id"]


def _create_run_folders(service, parent_folder_id: str) -> dict:
    """Create a timestamped run folder with Accepted/Rejected/Unfiltered subfolders."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    run_name = f"Run_{timestamp}"

    run_folder_id = _create_drive_folder(service, run_name, parent_folder_id)

    accepted_id = _create_drive_folder(service, "Accepted", run_folder_id)
    rejected_id = _create_drive_folder(service, "Rejected", run_folder_id)
    unfiltered_id = _create_drive_folder(service, "Unfiltered", run_folder_id)

    return {
        "run_name": run_name,
        "run_folder_id": run_folder_id,
        "accepted_folder_id": accepted_id,
        "rejected_folder_id": rejected_id,
        "unfiltered_folder_id": unfiltered_id,
    }


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
                f"(Experience: {d.get('experience', '?')}/40, "
                f"Projects: {d.get('projects', '?')}/35, "
                f"Learning Potential: {d.get('learning_potential', '?')}/25)"
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


def _sort_locally(candidates: list[dict]) -> dict:
    """Local fallback — save candidate metadata to local directories when Drive isn't configured."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    run_dir = os.path.join(LOCAL_OUTPUT_DIR, f"Run_{timestamp}")

    accepted_dir = os.path.join(run_dir, "Accepted")
    rejected_dir = os.path.join(run_dir, "Rejected")
    os.makedirs(accepted_dir, exist_ok=True)
    os.makedirs(rejected_dir, exist_ok=True)

    candidates = sorted(
        candidates,
        key=lambda c: _last_name_first(c.get("name", "")).lower(),
    )

    results = {"accepted": [], "rejected": [], "errors": [], "run_folder": run_dir}

    for c in candidates:
        candidate_name = c.get("name", c.get("id", "unknown"))
        status = c.get("status", "")

        if status == "rejected":
            target_dir = rejected_dir
            metadata = _build_rejected_description(c)
        else:
            target_dir = accepted_dir
            metadata = _build_accepted_description(c)

        safe_name = _last_name_first(candidate_name).replace("/", "-")
        meta_path = os.path.join(target_dir, f"{safe_name} - Summary.txt")

        try:
            with open(meta_path, "w") as f:
                f.write(metadata)

            entry = {"name": candidate_name, "file": meta_path}
            if status == "rejected":
                entry["reason"] = c.get("rejection_reason", "")
                results["rejected"].append(entry)
            else:
                results["accepted"].append(entry)
        except Exception as e:
            results["errors"].append(f"{candidate_name}: {e}")

    return results


def sort_and_upload(candidates: list[dict]) -> dict:
    """Sort resumes into per-run folders on Google Drive with descriptions.

    Creates a timestamped run folder (e.g. Run_2026-06-22_14-30) with
    Accepted/, Rejected/, and Unfiltered/ subfolders. Original resumes
    are copied to Unfiltered/ before being moved to their sorted folder.

    Falls back to local directories if Google Drive is not configured.
    """
    service = _get_drive_service()
    if not service:
        return _sort_locally(candidates)

    parent_folder = GDRIVE_RUNS_PARENT_FOLDER_ID or GDRIVE_RESUME_FOLDER_ID
    if not parent_folder:
        return _sort_locally(candidates)

    try:
        run_folders = _create_run_folders(service, parent_folder)
    except Exception as e:
        return {"error": f"Failed to create run folders: {e}"}

    accepted_folder_id = run_folders["accepted_folder_id"]
    rejected_folder_id = run_folders["rejected_folder_id"]
    unfiltered_folder_id = run_folders["unfiltered_folder_id"]

    candidates = sorted(
        candidates,
        key=lambda c: _last_name_first(c.get("name", "")).lower(),
    )

    results = {
        "accepted": [],
        "rejected": [],
        "errors": [],
        "run_folder": run_folders["run_name"],
        "run_folder_id": run_folders["run_folder_id"],
    }

    for c in candidates:
        file_id = c.get("file_id", "")
        status = c.get("status", "")

        if not file_id:
            results["errors"].append(f"{c.get('name', c.get('id', '?'))}: No file_id")
            continue

        if status == "rejected":
            target_folder = rejected_folder_id
            description = _build_rejected_description(c)
        else:
            target_folder = accepted_folder_id
            description = _build_accepted_description(c)

        try:
            current = service.files().get(
                fileId=file_id, fields="name, parents"
            ).execute()
            original_name = current.get("name", "")
            current_parents = ",".join(current.get("parents", []))

            # Copy original to Unfiltered before modifying
            service.files().copy(
                fileId=file_id,
                body={"name": original_name, "parents": [unfiltered_folder_id]},
                fields="id",
            ).execute()

            # Append PDF summary page
            try:
                from mcp_servers.output.pdf_summary import (
                    create_accepted_page, create_rejected_page, append_summary_to_pdf,
                )
                from googleapiclient.http import MediaInMemoryUpload

                pdf_bytes = service.files().get_media(fileId=file_id).execute()
                if status == "rejected":
                    summary_doc = create_rejected_page(c)
                else:
                    summary_doc = create_accepted_page(c)
                modified_pdf = append_summary_to_pdf(pdf_bytes, summary_doc)

                media = MediaInMemoryUpload(modified_pdf, mimetype="application/pdf")
                service.files().update(fileId=file_id, media_body=media).execute()
            except Exception as pdf_err:
                logger.warning(f"PDF append failed for {c.get('name', '?')}: {pdf_err}")

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
