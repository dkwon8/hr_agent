"""
Phase 1 — Resume Ingestion & Parsing

Reads PDFs from the resume directory, extracts text via PyMuPDF,
and uses an LLM to pull structured fields (name, graduation date,
location, skills, etc.) into Candidate objects.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from src.state import PipelineState, CandidateStatus
from src.tools.resume_parser import parse_resumes_from_directory
from src.utils.helpers import TokenTracker
from src.utils.tracing import get_tracer
from config.settings import OPENAI_API_KEY


async def ingest_resumes(state: PipelineState) -> dict:
    resume_dir = state["resume_dir"]
    tracker = TokenTracker()
    tracer = get_tracer()

    llm = ChatOpenAI(
        model="gpt-5.4",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )

    if tracer:
        with tracer.phase("ingestion"):
            candidates = await parse_resumes_from_directory(resume_dir, llm, tracker)
    else:
        candidates = await parse_resumes_from_directory(resume_dir, llm, tracker)

    errors = []
    for c in candidates:
        if c.rejection_reason:
            errors.append(f"[ingestion] {c.id}: {c.rejection_reason}")
        else:
            c.status = CandidateStatus.PENDING
            c.current_phase = "ingestion"

    print(f"[Phase 1] Ingested {len(candidates)} resumes, "
          f"{len(errors)} parse errors")
    print(f"  {tracker.summary('Ingestion')}")

    if tracer:
        tracer.log_token_usage("ingestion", tracker)
        tracer.log_phase_metrics("ingestion", {
            "resumes_parsed": len(candidates),
            "parse_errors": len(errors),
        })

    return {
        "candidates": candidates,
        "current_phase": "ingestion_complete",
        "errors": errors,
    }
