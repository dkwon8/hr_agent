"""
Resume parsing utilities — PDF text extraction and LLM-based field extraction.

Used by the Resume MCP server. Two core functions:
  - extract_text_from_pdf: PyMuPDF text extraction
  - extract_structured_fields: GPT-5.4 structured parsing
  - normalize_graduation_date: handles all date formats
"""

from __future__ import annotations

import json
import re

import fitz  # PyMuPDF
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}


def normalize_graduation_date(raw: str) -> str:
    """Normalize graduation date to YYYY-MM format. Returns empty string if unparseable."""
    if not raw:
        return ""

    raw = raw.strip()

    if re.match(r"^\d{4}-\d{2}$", raw):
        return raw

    match = re.match(r"^([A-Za-z]+)\s+(\d{4})$", raw)
    if match:
        month_str = match.group(1).lower()
        year = match.group(2)
        month = MONTH_MAP.get(month_str)
        if month:
            return f"{year}-{month}"

    match = re.match(r"^(\d{4})-(\d{1})$", raw)
    if match:
        return f"{match.group(1)}-0{match.group(2)}"

    match = re.match(r"^(\d{1,2})/(\d{4})$", raw)
    if match:
        month = int(match.group(1))
        year = match.group(2)
        if 1 <= month <= 12:
            return f"{year}-{month:02d}"

    match = re.match(r"^(spring|fall|autumn|winter|summer)\s+(\d{4})$", raw, re.IGNORECASE)
    if match:
        season = match.group(1).lower()
        year = match.group(2)
        season_month = {"spring": "05", "summer": "08", "fall": "12", "autumn": "12", "winter": "12"}
        return f"{year}-{season_month[season]}"

    return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


EXTRACTION_PROMPT = """You are a resume parser. Extract the following fields from the resume text.
Return ONLY valid JSON with these exact keys:

{
  "name": "Full name",
  "email": "Email address or empty string",
  "phone": "Phone number or empty string",
  "location": "City and/or state the candidate is based in, or empty string",
  "graduation_date": "Expected or actual graduation date in YYYY-MM format, or empty string if unclear",
  "degree_level": "One of: freshman, sophomore, junior, senior, masters, phd, unknown",
  "university": "University name or empty string",
  "major": "Field of study or empty string",
  "skills": ["list", "of", "technical", "skills"],
  "experience_summary": "Brief 2-3 sentence summary of work/project experience",
  "education_summary": "Brief summary of education background",
  "linkedin_url": "LinkedIn profile URL if found in resume, or empty string",
  "github_url": "GitHub profile URL if found in resume, or empty string",
  "portfolio_url": "Personal website or portfolio URL if found, or empty string"
}

Be precise with graduation_date. If the resume says "Expected May 2026", output "2026-05".
If it says "Class of 2027", output "2027-05" (assume May).
For degree_level, infer from context — if they started college in 2022 and graduate 2026, they are likely a senior.
If they started 2023 and graduate 2027, they are likely a junior."""


async def extract_structured_fields(raw_text: str, llm: ChatOpenAI) -> dict:
    """Send resume text to GPT-5.4 and get structured fields back as a dict."""
    response = await llm.ainvoke([
        SystemMessage(content=EXTRACTION_PROMPT),
        HumanMessage(content=f"Resume text:\n\n{raw_text}"),
    ])

    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        raise ValueError(f"Could not parse LLM response as JSON: {content[:200]}")
