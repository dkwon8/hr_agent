"""
Resume sorting and upload — sorts results into accepted/rejected folders.

Supports two modes:
  1. Local: copies resumes into data/output/accepted/ and data/output/rejected/
  2. Google Drive: uploads to shared Drive folders (when credentials are configured)

For rejected resumes, appends a page explaining the rejection reason.
For accepted resumes, appends a page with scoring summary.
"""

from __future__ import annotations

import os

import fitz  # PyMuPDF


OUTPUT_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output")

GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GDRIVE_ACCEPTED_FOLDER_ID = os.getenv("GDRIVE_ACCEPTED_FOLDER_ID", "")
GDRIVE_REJECTED_FOLDER_ID = os.getenv("GDRIVE_REJECTED_FOLDER_ID", "")


def _ensure_local_dirs():
    os.makedirs(os.path.join(OUTPUT_BASE, "accepted"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_BASE, "rejected"), exist_ok=True)


def append_rejection_page(src_path: str, dst_path: str, candidate: dict):
    """Copy a PDF and append a page with rejection details."""
    doc = fitz.open(src_path)
    new_page = doc.new_page(width=612, height=792)

    text = (
        f"RECRUITMENT PIPELINE — REJECTION SUMMARY\n"
        f"{'=' * 50}\n\n"
        f"Candidate: {candidate.get('name', '')}\n"
        f"Location: {candidate.get('location', '')}\n"
        f"University: {candidate.get('university', '')}\n"
        f"Major: {candidate.get('major', '')}\n"
        f"Graduation: {candidate.get('graduation_date', '')}\n\n"
        f"Status: REJECTED\n"
        f"Rejected in phase: {candidate.get('current_phase', candidate.get('rejected_in_phase', ''))}\n\n"
        f"Reason:\n{candidate.get('rejection_reason', 'No reason provided')}\n"
    )

    cross_notes = candidate.get("cross_validation_notes", [])
    if cross_notes:
        text += f"\n{'=' * 50}\nCROSS-VALIDATION NOTES:\n"
        for note in cross_notes:
            text += f"  - {note}\n"

    rect = fitz.Rect(50, 50, 562, 742)
    new_page.insert_textbox(rect, text, fontsize=11, fontname="helv")
    doc.save(dst_path)
    doc.close()


def append_acceptance_page(src_path: str, dst_path: str, candidate: dict):
    """Copy a PDF and append a page with scoring details."""
    doc = fitz.open(src_path)
    new_page = doc.new_page(width=612, height=792)

    top_depts = ""
    for i, d in enumerate(candidate.get("top_3_departments", [])[:3], 1):
        top_depts += (
            f"  {i}. {d.get('department', '?')}: {d.get('score', '?')}/100\n"
            f"     Skills: {d.get('skills_match', '?')}/40 | "
            f"Experience: {d.get('experience_relevance', '?')}/35 | "
            f"Potential: {d.get('potential', '?')}/25\n"
            f"     {d.get('reasoning', '')[:150]}\n\n"
        )

    text = (
        f"RECRUITMENT PIPELINE — CANDIDATE SUMMARY\n"
        f"{'=' * 50}\n\n"
        f"Candidate: {candidate.get('name', '')}\n"
        f"Location: {candidate.get('location', '')}\n"
        f"University: {candidate.get('university', '')}\n"
        f"Major: {candidate.get('major', '')}\n"
        f"Graduation: {candidate.get('graduation_date', '')}\n\n"
        f"Status: SELECTED FOR INTERVIEW\n"
        f"Overall Score: {candidate.get('quality_score', 0)}/100\n"
        f"Best Fit Department: {candidate.get('best_fit_department', '')}\n\n"
        f"TOP DEPARTMENT FITS:\n"
        f"{top_depts}"
    )

    cross_notes = candidate.get("cross_validation_notes", [])
    if cross_notes:
        text += f"{'=' * 50}\nCROSS-VALIDATION NOTES:\n"
        for note in cross_notes:
            text += f"  - {note}\n"

    rect = fitz.Rect(50, 50, 562, 742)
    new_page.insert_textbox(rect, text, fontsize=10, fontname="helv")
    doc.save(dst_path)
    doc.close()


def sort_resumes_locally(candidates: list[dict]) -> dict:
    """Sort resumes into accepted/rejected local folders."""
    _ensure_local_dirs()

    accepted_dir = os.path.join(OUTPUT_BASE, "accepted")
    rejected_dir = os.path.join(OUTPUT_BASE, "rejected")

    results = {"accepted": [], "rejected": [], "errors": []}

    for c in candidates:
        resume_path = c.get("resume_path", "")
        if not resume_path or not os.path.exists(resume_path):
            results["errors"].append(f"{c.get('name', c.get('id', '?'))}: Resume file not found")
            continue

        filename = os.path.basename(resume_path)
        status = c.get("status", "")

        if status in {"selected", "scored", "ranked"}:
            dst = os.path.join(accepted_dir, filename)
            try:
                append_acceptance_page(resume_path, dst, c)
                results["accepted"].append({"name": c.get("name", ""), "file": dst})
            except Exception as e:
                results["errors"].append(f"{c.get('name', '')}: {e}")

        elif status == "rejected":
            dst = os.path.join(rejected_dir, filename)
            try:
                append_rejection_page(resume_path, dst, c)
                results["rejected"].append({
                    "name": c.get("name", ""),
                    "file": dst,
                    "reason": c.get("rejection_reason", ""),
                })
            except Exception as e:
                results["errors"].append(f"{c.get('name', '')}: {e}")

    return results


def _get_drive_service():
    if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        return build("drive", "v3", credentials=creds)
    except Exception:
        return None


def upload_to_drive(candidates: list[dict]) -> dict:
    """Upload sorted resumes to Google Drive folders."""
    service = _get_drive_service()
    if not service:
        return {"error": "Google Drive not configured"}

    if not GDRIVE_ACCEPTED_FOLDER_ID or not GDRIVE_REJECTED_FOLDER_ID:
        return {"error": "Drive folder IDs not set in .env"}

    from googleapiclient.http import MediaFileUpload

    local_results = sort_resumes_locally(candidates)
    drive_results = {"accepted": [], "rejected": [], "errors": local_results["errors"]}

    for item in local_results["accepted"]:
        try:
            file_metadata = {"name": os.path.basename(item["file"]), "parents": [GDRIVE_ACCEPTED_FOLDER_ID]}
            media = MediaFileUpload(item["file"], mimetype="application/pdf")
            uploaded = service.files().create(body=file_metadata, media_body=media, fields="id,webViewLink").execute()
            drive_results["accepted"].append({**item, "drive_id": uploaded["id"], "link": uploaded.get("webViewLink", "")})
        except Exception as e:
            drive_results["errors"].append(f"Drive upload failed for {item['name']}: {e}")

    for item in local_results["rejected"]:
        try:
            file_metadata = {"name": os.path.basename(item["file"]), "parents": [GDRIVE_REJECTED_FOLDER_ID]}
            media = MediaFileUpload(item["file"], mimetype="application/pdf")
            uploaded = service.files().create(body=file_metadata, media_body=media, fields="id,webViewLink").execute()
            drive_results["rejected"].append({**item, "drive_id": uploaded["id"], "link": uploaded.get("webViewLink", "")})
        except Exception as e:
            drive_results["errors"].append(f"Drive upload failed for {item['name']}: {e}")

    return drive_results


def sort_and_upload(candidates: list[dict]) -> dict:
    """Sort resumes and upload to Drive if configured, otherwise local only."""
    service = _get_drive_service()
    if service and GDRIVE_ACCEPTED_FOLDER_ID and GDRIVE_REJECTED_FOLDER_ID:
        return upload_to_drive(candidates)
    else:
        return sort_resumes_locally(candidates)
