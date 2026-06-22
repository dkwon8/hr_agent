"""
PDF summary page generator — appends a decision page to candidate resumes.

Uses PyMuPDF (fitz) to create formatted summary pages showing scoring
rationale for accepted candidates or rejection reasons for rejected ones.
"""

from __future__ import annotations

import fitz


PAGE_WIDTH = 595  # A4
PAGE_HEIGHT = 842
MARGIN = 60
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN

RED_HAT_RED = (0.8, 0.08, 0.08)
DARK_GRAY = (0.2, 0.2, 0.2)
MEDIUM_GRAY = (0.45, 0.45, 0.45)
GREEN = (0.13, 0.55, 0.13)
REJECT_RED = (0.7, 0.1, 0.1)


def _insert_header(page: fitz.Page, y: float, text: str) -> float:
    """Insert a section header and return the new y position."""
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + 20)
    page.insert_textbox(r, text, fontsize=11, fontname="helv", color=RED_HAT_RED)
    y += 18
    page.draw_line((MARGIN, y), (MARGIN + TEXT_WIDTH, y), color=RED_HAT_RED, width=0.8)
    return y + 8


def _insert_line(page: fitz.Page, y: float, text: str,
                 fontsize: float = 9.5, color: tuple = DARK_GRAY,
                 fontname: str = "helv") -> float:
    """Insert a line of text and return the new y position."""
    line_height = fontsize + 5
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + line_height * 3)
    overflow = page.insert_textbox(r, text, fontsize=fontsize, fontname=fontname, color=color)
    lines_used = 1 if overflow >= 0 else 2
    return y + line_height * lines_used


def _insert_wrapped(page: fitz.Page, y: float, text: str,
                    fontsize: float = 9, color: tuple = MEDIUM_GRAY,
                    max_height: float = 80) -> float:
    """Insert wrapped text within a bounded box and return the new y position."""
    r = fitz.Rect(MARGIN + 10, y, MARGIN + TEXT_WIDTH, y + max_height)
    page.insert_textbox(r, text, fontsize=fontsize, fontname="helv", color=color)
    approx_chars_per_line = TEXT_WIDTH / (fontsize * 0.5)
    approx_lines = max(1, len(text) / approx_chars_per_line)
    used_height = min(max_height, approx_lines * (fontsize + 3))
    return y + used_height + 6


def create_accepted_page(candidate: dict) -> fitz.Document:
    """Create a summary page for an accepted candidate."""
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

    y = MARGIN

    # Title
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + 28)
    page.insert_textbox(r, "Red Hat Global Engineering — Candidate Summary",
                        fontsize=15, fontname="helv", color=RED_HAT_RED)
    y += 30
    page.draw_line((MARGIN, y), (MARGIN + TEXT_WIDTH, y), color=RED_HAT_RED, width=2)
    y += 15

    # Status badge
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + 22)
    page.insert_textbox(r, "STATUS: ACCEPTED", fontsize=13, fontname="helv", color=GREEN)
    y += 28

    # Candidate info
    y = _insert_header(page, y, "Candidate Information")
    name = candidate.get("name", "Unknown")
    y = _insert_line(page, y, f"Name: {name}")
    y = _insert_line(page, y, f"University: {candidate.get('university', 'N/A')}  |  Major: {candidate.get('major', 'N/A')}")
    y = _insert_line(page, y, f"Location: {candidate.get('location', 'N/A')}  |  Graduation: {candidate.get('graduation_date', 'N/A')}")
    y += 6

    # Overall score
    score = candidate.get("quality_score")
    best_dept = candidate.get("best_fit_department", "N/A")
    if score is not None:
        y = _insert_header(page, y, "Scoring Summary")
        y = _insert_line(page, y, f"Overall Score: {score}/100  |  Best Fit: {best_dept}", fontsize=11)

        confidence = candidate.get("score_confidence", {})
        if confidence:
            y = _insert_line(page, y,
                f"Confidence: {confidence.get('min', '?')}-{confidence.get('max', '?')} "
                f"(median {confidence.get('median', '?')}, {confidence.get('passes', '?')} passes)",
                fontsize=9, color=MEDIUM_GRAY)
        y += 4

    # Top 3 departments
    top_depts = candidate.get("top_3_departments", [])
    if top_depts:
        y = _insert_header(page, y, "Top Department Fits")
        for i, d in enumerate(top_depts[:3], 1):
            dept_name = d.get("department", "?")
            dept_score = d.get("score", "?")
            exp = d.get("experience", "?")
            proj = d.get("projects", "?")
            lp = d.get("learning_potential", "?")

            y = _insert_line(page, y,
                f"{i}. {dept_name}: {dept_score}/100  "
                f"(Experience: {exp}/40, Projects: {proj}/35, Learning Potential: {lp}/25)",
                fontsize=9.5)

            reasoning = d.get("reasoning", "")
            if reasoning:
                y = _insert_wrapped(page, y, reasoning, max_height=40)
        y += 4

    # GitHub findings
    github = candidate.get("github_url", "") or candidate.get("github_profile", "")
    github_notes = candidate.get("cross_validation_notes", [])
    if github or github_notes:
        y = _insert_header(page, y, "GitHub Validation")
        if github:
            y = _insert_line(page, y, f"Profile: {github}")
        for note in github_notes:
            y = _insert_line(page, y, f"  • {note}", fontsize=9, color=MEDIUM_GRAY)
        y += 4

    # Overall reasoning
    reasoning = candidate.get("quality_reasoning", "")
    if reasoning:
        y = _insert_header(page, y, "Overall Assessment")
        y = _insert_wrapped(page, y, reasoning, max_height=100)

    # Footer
    page.draw_line((MARGIN, PAGE_HEIGHT - 50), (MARGIN + TEXT_WIDTH, PAGE_HEIGHT - 50),
                   color=MEDIUM_GRAY, width=0.5)
    r = fitz.Rect(MARGIN, PAGE_HEIGHT - 45, MARGIN + TEXT_WIDTH, PAGE_HEIGHT - 30)
    page.insert_textbox(r, "Generated by Red Hat HR Recruitment Agent",
                        fontsize=8, fontname="helv", color=MEDIUM_GRAY, align=fitz.TEXT_ALIGN_CENTER)

    return doc


def create_rejected_page(candidate: dict) -> fitz.Document:
    """Create a summary page for a rejected candidate."""
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

    y = MARGIN

    # Title
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + 28)
    page.insert_textbox(r, "Red Hat Global Engineering — Candidate Summary",
                        fontsize=15, fontname="helv", color=RED_HAT_RED)
    y += 30
    page.draw_line((MARGIN, y), (MARGIN + TEXT_WIDTH, y), color=RED_HAT_RED, width=2)
    y += 15

    # Status badge
    r = fitz.Rect(MARGIN, y, MARGIN + TEXT_WIDTH, y + 22)
    page.insert_textbox(r, "STATUS: REJECTED", fontsize=13, fontname="helv", color=REJECT_RED)
    y += 28

    # Candidate info
    y = _insert_header(page, y, "Candidate Information")
    y = _insert_line(page, y, f"Name: {candidate.get('name', 'Unknown')}")
    y = _insert_line(page, y, f"University: {candidate.get('university', 'N/A')}")
    y = _insert_line(page, y, f"Location: {candidate.get('location', 'N/A')}  |  Graduation: {candidate.get('graduation_date', 'N/A')}")
    y += 10

    # Rejection reason
    y = _insert_header(page, y, "Rejection Reason")
    reason = candidate.get("rejection_reason", "No reason provided")
    y = _insert_wrapped(page, y, reason, fontsize=11, color=DARK_GRAY, max_height=60)

    # Footer
    page.draw_line((MARGIN, PAGE_HEIGHT - 50), (MARGIN + TEXT_WIDTH, PAGE_HEIGHT - 50),
                   color=MEDIUM_GRAY, width=0.5)
    r = fitz.Rect(MARGIN, PAGE_HEIGHT - 45, MARGIN + TEXT_WIDTH, PAGE_HEIGHT - 30)
    page.insert_textbox(r, "Generated by Red Hat HR Recruitment Agent",
                        fontsize=8, fontname="helv", color=MEDIUM_GRAY, align=fitz.TEXT_ALIGN_CENTER)

    return doc


def append_summary_to_pdf(pdf_bytes: bytes, summary_doc: fitz.Document) -> bytes:
    """Append summary page(s) to an existing PDF and return the modified bytes."""
    original = fitz.open(stream=pdf_bytes, filetype="pdf")
    original.insert_pdf(summary_doc)
    result = original.tobytes()
    original.close()
    summary_doc.close()
    return result
