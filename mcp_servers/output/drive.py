"""
Resume sorting and upload — sorts pipeline results into accepted/rejected folders.

Supports two modes:
  1. Local: copies resumes into data/output/accepted/ and data/output/rejected/
  2. Google Drive: uploads to shared Drive folders (when credentials are configured)

For rejected resumes, appends a page explaining the rejection reason.
"""

from __future__ import annotations

import os
import shutil

import fitz  # PyMuPDF

from src.state import Candidate, CandidateStatus


OUTPUT_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "output")

# Google Drive config — set these in .env to enable Drive uploads
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GDRIVE_ACCEPTED_FOLDER_ID = os.getenv("GDRIVE_ACCEPTED_FOLDER_ID", "")
GDRIVE_REJECTED_FOLDER_ID = os.getenv("GDRIVE_REJECTED_FOLDER_ID", "")


def _ensure_local_dirs():
    os.makedirs(os.path.join(OUTPUT_BASE, "accepted"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_BASE, "rejected"), exist_ok=True)


def _append_rejection_page(src_path: str, dst_path: str, candidate: Candidate):
    """Copy a PDF and append a page with rejection details."""
    doc = fitz.open(src_path)

    new_page = doc.new_page(width=612, height=792)

    rejection_text = (
        f"RECRUITMENT PIPELINE — REJECTION SUMMARY\n"
        f"{'=' * 50}\n\n"
        f"Candidate: {candidate.name}\n"
        f"Location: {candidate.location}\n"
        f"University: {candidate.university}\n"
        f"Major: {candidate.major}\n"
        f"Graduation: {candidate.graduation_date}\n\n"
        f"Status: REJECTED\n"
        f"Rejected in phase: {candidate.current_phase}\n\n"
        f"Reason:\n{candidate.rejection_reason}\n"
    )

    if candidate.quality_score > 0:
        rejection_text += (
            f"\n{'=' * 50}\n"
            f"SCORING (if scored before rejection):\n"
            f"  Best fit department: {candidate.best_fit_department}\n"
            f"  Score: {candidate.quality_score}/100\n"
            f"  Reasoning: {candidate.quality_reasoning[:300]}\n"
        )

    if candidate.cross_validation_notes:
        rejection_text += (
            f"\n{'=' * 50}\n"
            f"CROSS-VALIDATION NOTES:\n"
        )
        for note in candidate.cross_validation_notes:
            rejection_text += f"  - {note}\n"

    text_rect = fitz.Rect(50, 50, 562, 742)
    new_page.insert_textbox(
        text_rect,
        rejection_text,
        fontsize=11,
        fontname="helv",
    )

    doc.save(dst_path)
    doc.close()


def _append_acceptance_page(src_path: str, dst_path: str, candidate: Candidate):
    """Copy a PDF and append a page with scoring details."""
    doc = fitz.open(src_path)

    new_page = doc.new_page(width=612, height=792)

    top_depts = ""
    for i, d in enumerate(candidate.top_3_departments[:3], 1):
        top_depts += (
            f"  {i}. {d.get('department', '?')}: {d.get('score', '?')}/100\n"
            f"     Skills: {d.get('skills_match', '?')}/40 | "
            f"Experience: {d.get('experience_relevance', '?')}/35 | "
            f"Potential: {d.get('potential', '?')}/25\n"
            f"     {d.get('reasoning', '')[:150]}\n\n"
        )

    acceptance_text = (
        f"RECRUITMENT PIPELINE — CANDIDATE SUMMARY\n"
        f"{'=' * 50}\n\n"
        f"Candidate: {candidate.name}\n"
        f"Location: {candidate.location}\n"
        f"University: {candidate.university}\n"
        f"Major: {candidate.major}\n"
        f"Graduation: {candidate.graduation_date}\n\n"
        f"Status: SELECTED FOR INTERVIEW\n"
        f"Overall Score: {candidate.quality_score}/100\n"
        f"Best Fit Department: {candidate.best_fit_department}\n\n"
        f"TOP DEPARTMENT FITS:\n"
        f"{top_depts}"
    )

    if candidate.cross_validation_notes:
        acceptance_text += (
            f"{'=' * 50}\n"
            f"CROSS-VALIDATION NOTES:\n"
        )
        for note in candidate.cross_validation_notes:
            acceptance_text += f"  - {note}\n"

    text_rect = fitz.Rect(50, 50, 562, 742)
    new_page.insert_textbox(
        text_rect,
        acceptance_text,
        fontsize=10,
        fontname="helv",
    )

    doc.save(dst_path)
    doc.close()


def sort_resumes_locally(candidates: list[Candidate]) -> dict:
    """Sort resumes into accepted/rejected local folders."""
    _ensure_local_dirs()

    accepted_dir = os.path.join(OUTPUT_BASE, "accepted")
    rejected_dir = os.path.join(OUTPUT_BASE, "rejected")

    results = {"accepted": [], "rejected": [], "errors": []}

    for c in candidates:
        if not c.resume_path or not os.path.exists(c.resume_path):
            results["errors"].append(f"{c.id}: Resume file not found at {c.resume_path}")
            continue

        filename = os.path.basename(c.resume_path)

        if c.status in {CandidateStatus.SELECTED, CandidateStatus.RANKED}:
            dst = os.path.join(accepted_dir, filename)
            try:
                _append_acceptance_page(c.resume_path, dst, c)
                results["accepted"].append({"name": c.name, "file": dst})
            except Exception as e:
                results["errors"].append(f"{c.name}: Failed to process — {e}")

        elif c.status == CandidateStatus.REJECTED:
            dst = os.path.join(rejected_dir, filename)
            try:
                _append_rejection_page(c.resume_path, dst, c)
                results["rejected"].append({"name": c.name, "file": dst, "reason": c.rejection_reason})
            except Exception as e:
                results["errors"].append(f"{c.name}: Failed to process — {e}")

    return results


def _get_drive_service():
    """Initialize Google Drive API service."""
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


def upload_to_drive(candidates: list[Candidate]) -> dict:
    """Upload sorted resumes to Google Drive folders."""
    service = _get_drive_service()
    if not service:
        return {"error": "Google Drive not configured — using local folders instead"}

    if not GDRIVE_ACCEPTED_FOLDER_ID or not GDRIVE_REJECTED_FOLDER_ID:
        return {"error": "Drive folder IDs not set in .env"}

    from googleapiclient.http import MediaFileUpload

    local_results = sort_resumes_locally(candidates)
    drive_results = {"accepted": [], "rejected": [], "errors": local_results["errors"]}

    for item in local_results["accepted"]:
        try:
            file_metadata = {
                "name": os.path.basename(item["file"]),
                "parents": [GDRIVE_ACCEPTED_FOLDER_ID],
            }
            media = MediaFileUpload(item["file"], mimetype="application/pdf")
            uploaded = service.files().create(
                body=file_metadata, media_body=media, fields="id,webViewLink"
            ).execute()
            drive_results["accepted"].append({
                **item, "drive_id": uploaded["id"], "link": uploaded.get("webViewLink", "")
            })
        except Exception as e:
            drive_results["errors"].append(f"Drive upload failed for {item['name']}: {e}")

    for item in local_results["rejected"]:
        try:
            file_metadata = {
                "name": os.path.basename(item["file"]),
                "parents": [GDRIVE_REJECTED_FOLDER_ID],
            }
            media = MediaFileUpload(item["file"], mimetype="application/pdf")
            uploaded = service.files().create(
                body=file_metadata, media_body=media, fields="id,webViewLink"
            ).execute()
            drive_results["rejected"].append({
                **item, "drive_id": uploaded["id"], "link": uploaded.get("webViewLink", "")
            })
        except Exception as e:
            drive_results["errors"].append(f"Drive upload failed for {item['name']}: {e}")

    return drive_results


def sort_and_upload(candidates: list[Candidate]) -> dict:
    """Sort resumes and upload to Drive if configured, otherwise local only."""
    service = _get_drive_service()
    if service and GDRIVE_ACCEPTED_FOLDER_ID and GDRIVE_REJECTED_FOLDER_ID:
        print("[Sort] Uploading to Google Drive...")
        return upload_to_drive(candidates)
    else:
        print("[Sort] Google Drive not configured — sorting to local folders")
        return sort_resumes_locally(candidates)
