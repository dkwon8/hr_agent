"""
Resume MCP Server — reads, parses, and serves resume data.

Connects to Google Drive to access resume PDFs, extracts text via PyMuPDF,
and uses GPT-5.4 for structured field extraction.

Run standalone:
    python -m mcp_servers.resume.server                    # stdio mode (for agent)
    python -m mcp_servers.resume.server --transport sse    # HTTP mode (for testing)

Tools:
    list_resumes     — list all PDFs in a Google Drive folder
    read_resume      — extract raw text from one PDF
    parse_resume     — parse one resume into structured candidate data
    parse_all_resumes — batch parse all resumes in a folder
    search_candidates — search parsed candidates by name/skill/university
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import tempfile
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# Add project root to path so we can import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp_servers.resume.parser import (
    extract_text_from_pdf,
    extract_structured_fields,
    normalize_graduation_date,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resume_mcp")

# ── Server Setup ──────────────────────────────────────────

mcp = FastMCP(
    "Resume MCP Server",
    instructions=(
        "Provides tools for reading and parsing resumes. "
        "Can list resumes from Google Drive, extract text from PDFs, "
        "and parse resumes into structured candidate data using an LLM."
    ),
)

# ── Google Drive Helpers ──────────────────────────────────

GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GDRIVE_RESUME_FOLDER_ID = os.getenv("GDRIVE_RESUME_FOLDER_ID", "")

# Local fallback directory
LOCAL_RESUME_DIR = os.getenv(
    "RESUME_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "resumes"),
)

# In-memory cache of parsed candidates for search
_parsed_candidates: list[dict] = []


def _get_drive_service():
    """Initialize Google Drive API service if credentials exist."""
    if not GOOGLE_CREDENTIALS_PATH or not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        logger.warning(f"Google Drive not available: {e}")
        return None


def _get_llm():
    """Create the LLM client for resume parsing."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL_NAME", "gpt-5.4"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0,
        seed=42,
    )


# ── MCP Tools ─────────────────────────────────────────────


@mcp.tool()
async def list_resumes(
    folder_id: Optional[str] = None,
) -> str:
    """List all PDF resumes available. Checks Google Drive first, falls back to local folder.

    Args:
        folder_id: Google Drive folder ID (optional, uses default from .env if not provided)
    """
    drive = _get_drive_service()
    fid = folder_id or GDRIVE_RESUME_FOLDER_ID

    if drive and fid:
        try:
            results = drive.files().list(
                q=f"'{fid}' in parents and mimeType='application/pdf' and trashed=false",
                fields="files(id, name, size, modifiedTime)",
                orderBy="name",
            ).execute()

            files = results.get("files", [])
            if not files:
                return json.dumps({"source": "google_drive", "count": 0, "files": []})

            file_list = [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "size_bytes": f.get("size", "unknown"),
                    "modified": f.get("modifiedTime", "unknown"),
                }
                for f in files
            ]
            return json.dumps({"source": "google_drive", "count": len(file_list), "files": file_list})

        except Exception as e:
            logger.warning(f"Drive list failed: {e}, falling back to local")

    # Local fallback
    if os.path.isdir(LOCAL_RESUME_DIR):
        pdf_files = sorted(f for f in os.listdir(LOCAL_RESUME_DIR) if f.lower().endswith(".pdf"))
        file_list = [
            {
                "id": f,
                "name": f,
                "size_bytes": os.path.getsize(os.path.join(LOCAL_RESUME_DIR, f)),
                "source": "local",
            }
            for f in pdf_files
        ]
        return json.dumps({"source": "local", "count": len(file_list), "files": file_list})

    return json.dumps({"source": "none", "count": 0, "error": "No resume source configured"})


@mcp.tool()
async def read_resume(
    file_id: str,
) -> str:
    """Extract raw text from a resume PDF.

    Args:
        file_id: Google Drive file ID or local filename
    """
    drive = _get_drive_service()

    # Try Google Drive first
    if drive and not os.path.sep in file_id and len(file_id) > 20:
        try:
            content = drive.files().get_media(fileId=file_id).execute()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            text = extract_text_from_pdf(tmp_path)
            os.unlink(tmp_path)

            return json.dumps({
                "file_id": file_id,
                "text_length": len(text),
                "text": text,
            })
        except Exception as e:
            logger.warning(f"Drive read failed for {file_id}: {e}")

    # Local fallback
    local_path = os.path.join(LOCAL_RESUME_DIR, file_id)
    if os.path.exists(local_path):
        text = extract_text_from_pdf(local_path)
        return json.dumps({
            "file_id": file_id,
            "source": "local",
            "text_length": len(text),
            "text": text,
        })

    return json.dumps({"error": f"Resume not found: {file_id}"})


@mcp.tool()
async def parse_resume(
    file_id: str,
    candidate_id: Optional[str] = None,
) -> str:
    """Parse a single resume into structured candidate data using LLM.

    Extracts: name, email, phone, location, graduation date, degree level,
    university, major, skills, experience summary, education summary,
    LinkedIn URL, GitHub URL, portfolio URL.

    Args:
        file_id: Google Drive file ID or local filename
        candidate_id: Optional ID to assign to the candidate
    """
    # Get the raw text first
    raw_result = json.loads(await read_resume(file_id))
    if "error" in raw_result:
        return json.dumps(raw_result)

    raw_text = raw_result["text"]
    cid = candidate_id or f"candidate_{file_id[:8]}"

    llm = _get_llm()

    try:
        fields = await extract_structured_fields(raw_text, llm)

        grad_raw = fields.get("graduation_date", "")
        grad_normalized = normalize_graduation_date(grad_raw)

        candidate = {
            "id": cid,
            "file_id": file_id,
            "name": fields.get("name", ""),
            "email": fields.get("email", ""),
            "phone": fields.get("phone", ""),
            "location": fields.get("location", ""),
            "graduation_date": grad_normalized,
            "degree_level": fields.get("degree_level", "unknown"),
            "university": fields.get("university", ""),
            "major": fields.get("major", ""),
            "skills": fields.get("skills", []),
            "experience_summary": fields.get("experience_summary", ""),
            "education_summary": fields.get("education_summary", ""),
            "linkedin_url": fields.get("linkedin_url", ""),
            "github_url": fields.get("github_url", ""),
            "portfolio_url": fields.get("portfolio_url", ""),
            "status": "parsed",
        }

        # Cache for search
        _parsed_candidates.append(candidate)

        return json.dumps(candidate)

    except Exception as e:
        return json.dumps({
            "id": cid,
            "file_id": file_id,
            "error": f"Parse failed: {e}",
            "status": "parse_error",
        })


@mcp.tool()
async def parse_all_resumes(
    folder_id: Optional[str] = None,
) -> str:
    """Parse all resumes in a folder into structured candidate data.

    Processes in batches of 10 for efficiency. Returns a summary with
    all parsed candidates.

    Args:
        folder_id: Google Drive folder ID (optional, uses default from .env)
    """
    global _parsed_candidates
    _parsed_candidates = []

    listing = json.loads(await list_resumes(folder_id))
    files = listing.get("files", [])

    if not files:
        return json.dumps({
            "count": 0,
            "candidates": [],
            "message": "No resumes found",
        })

    results = []
    errors = []

    # Process in batches
    batch_size = 10
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        tasks = [
            parse_resume(f["id"], f"candidate_{i+j:04d}")
            for j, f in enumerate(batch)
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for f, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                errors.append({"file": f["name"], "error": str(result)})
            else:
                parsed = json.loads(result)
                if "error" in parsed:
                    errors.append({"file": f["name"], "error": parsed["error"]})
                else:
                    results.append(parsed)

    return json.dumps({
        "count": len(results),
        "errors": len(errors),
        "candidates": results,
        "error_details": errors if errors else [],
    })


@mcp.tool()
async def search_candidates(
    query: str,
) -> str:
    """Search previously parsed candidates by name, skill, university, or location.

    Must run parse_all_resumes or parse_resume first to populate the candidate cache.

    Args:
        query: Search term to match against candidate fields
    """
    if not _parsed_candidates:
        return json.dumps({
            "error": "No candidates parsed yet. Run parse_all_resumes first.",
            "count": 0,
        })

    query_lower = query.lower()
    matches = []

    for c in _parsed_candidates:
        searchable = " ".join([
            c.get("name", ""),
            c.get("university", ""),
            c.get("major", ""),
            c.get("location", ""),
            " ".join(c.get("skills", [])),
            c.get("experience_summary", ""),
        ]).lower()

        if query_lower in searchable:
            matches.append(c)

    return json.dumps({
        "query": query,
        "count": len(matches),
        "candidates": matches,
    })


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resume MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport mode (stdio for agent, sse for HTTP testing)",
    )
    parser.add_argument("--port", type=int, default=3001, help="Port for SSE mode")
    parser.add_argument("--host", default="localhost", help="Host for SSE mode")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
