"""
Chainlit UI for the HR Recruitment Agent.

Run:
    chainlit run app.py
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

import chainlit as cl
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agent import create_agent

from agents import Runner
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent


def _log_scoring_assessments(trace_id: str):
    """Log candidate scoring data as MLflow assessments from the most recent report."""
    import glob
    import json
    import mlflow
    from mlflow.entities import Feedback, AssessmentSource, AssessmentSourceType

    report_dir = os.path.join(os.path.dirname(__file__), "data")
    reports = sorted(glob.glob(os.path.join(report_dir, "report_*.json")))
    if not reports:
        return

    with open(reports[-1]) as f:
        report = json.load(f)

    source = AssessmentSource(
        source_type=AssessmentSourceType.LLM_JUDGE,
        source_id="scoring-mcp",
    )

    selected = report.get("selected_candidates", [])
    rejected = report.get("rejected_candidates", [])

    if not selected and not rejected:
        return

    summary = report.get("summary", {})
    mlflow.log_assessment(trace_id, Feedback(
        name="pipeline_summary",
        value=f"{summary.get('total_selected', 0)} accepted, {summary.get('total_rejected', 0)} rejected",
        rationale=f"Top score: {summary.get('top_score', 'N/A')}/100",
        source=source,
    ))

    for c in selected:
        name = c.get("name", "Unknown")
        score = c.get("quality_score", 0)
        best_dept = c.get("best_fit_department", "N/A")
        breakdown = c.get("fit_breakdown", {})
        confidence = c.get("score_confidence", {})
        top_3 = c.get("top_3_departments", [])

        top_3_str = ", ".join(
            f"{d.get('department', '?')}: {d.get('score', '?')}"
            for d in top_3
        )

        mlflow.log_assessment(trace_id, Feedback(
            name=f"candidate_{name.replace(' ', '_').lower()}",
            value=score,
            rationale=(
                f"Best fit: {best_dept} | "
                f"Experience: {breakdown.get('experience', '?')}/40, "
                f"Projects: {breakdown.get('projects', '?')}/35, "
                f"Learning Potential: {breakdown.get('learning_potential', '?')}/25 | "
                f"Confidence: {confidence.get('min', '?')}-{confidence.get('max', '?')} | "
                f"Top 3: {top_3_str}"
            ),
            source=source,
        ))

    for c in rejected:
        name = c.get("name", "Unknown")
        mlflow.log_assessment(trace_id, Feedback(
            name=f"rejected_{name.replace(' ', '_').lower()}",
            value=0,
            rationale=c.get("rejection_reason", "No reason"),
            source=source,
        ))


TOOL_LABELS = {
    "list_resumes": "Listing resumes from Google Drive",
    "list_sorted_resumes": "Listing sorted resumes",
    "read_resume": "Reading resume PDF",
    "parse_resume": "Parsing resume with LLM",
    "parse_all_resumes": "Parsing all resumes",
    "search_candidates": "Searching candidates",
    "check_candidate_location": "Checking candidate location",
    "check_candidate_graduation": "Checking graduation date",
    "filter_candidates": "Filtering candidates",
    "lookup_profile": "Looking up GitHub profile",
    "discover_profile": "Searching for GitHub profile",
    "check_authenticity": "Checking GitHub authenticity",
    "score_candidate": "Scoring candidate against departments",
    "score_all_candidates": "Scoring all candidates",
    "score_candidate_for_role": "Scoring candidate for custom role",
    "score_all_for_role": "Scoring all candidates for custom role",
    "get_department_requirements": "Loading department requirements",
    "generate_report": "Generating pipeline report",
    "sort_resumes": "Sorting resumes into folders",
    "web_search": "Searching the web",
    "fetch_job_posting": "Fetching job posting from Workday",
}


@cl.on_chat_start
async def on_chat_start():
    agent, mcp_servers = create_agent()

    stack = contextlib.AsyncExitStack()
    for server in mcp_servers:
        await stack.enter_async_context(server)

    cl.user_session.set("agent", agent)
    cl.user_session.set("stack", stack)
    cl.user_session.set("messages", [])

    await cl.Message(
        content=(
            "**Red Hat — HR Recruitment Agent**\n\n"
            "I can help you process resumes, filter candidates, "
            "validate GitHub profiles, score applicants, and generate reports.\n\n"
            "Try:\n"
            "- *\"Run the full pipeline\"* — use default GE intern requirements\n"
            "- *\"Evaluate resumes for [Workday URL]\"* — fetch requirements from a job posting\n"
            "- *\"List the resumes\"* — see available resumes"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get("agent")
    messages = cl.user_session.get("messages")

    messages.append({"role": "user", "content": message.content})

    msg = cl.Message(content="")
    await msg.send()

    result = Runner.run_streamed(agent, messages)
    streaming_started = False
    tool_status_lines = []

    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            if isinstance(event.data, ResponseTextDeltaEvent):
                if not streaming_started:
                    streaming_started = True
                    msg.content = ""
                    await msg.update()
                await msg.stream_token(event.data.delta)

        elif isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                raw = event.item.raw_item
                tool_name = getattr(raw, "name", "") or ""
                label = TOOL_LABELS.get(tool_name, f"Running {tool_name}")
                tool_status_lines.append(f"⏳ {label}...")
                msg.content = "\n".join(tool_status_lines)
                await msg.update()

            elif event.name == "tool_output":
                if tool_status_lines:
                    tool_status_lines[-1] = tool_status_lines[-1].replace("⏳", "✅")
                    msg.content = "\n".join(tool_status_lines)
                    await msg.update()

    response = re.sub(r"\s*(?:citeturn|turn)\d+\S*", "", result.final_output, flags=re.IGNORECASE).rstrip()
    messages.append({"role": "assistant", "content": response})
    cl.user_session.set("messages", messages)

    if not streaming_started:
        msg.content = response
    else:
        msg.content = re.sub(r"\s*(?:citeturn|turn)\d+\S*", "", msg.content, flags=re.IGNORECASE).rstrip()
    await msg.update()

    try:
        import mlflow
        import urllib.request

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        urllib.request.urlopen(tracking_uri, timeout=2)

        mlflow.flush_trace_async_logging()

        exp = mlflow.get_experiment_by_name(
            os.getenv("MLFLOW_EXPERIMENT_NAME", "recruitment-filtration-agent")
        )
        if exp:
            traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=1)
            if len(traces) > 0:
                trace_id = traces.iloc[0]["trace_id"]
                _log_scoring_assessments(trace_id)
    except Exception:
        pass


@cl.on_chat_end
async def on_chat_end():
    stack = cl.user_session.get("stack")
    if stack:
        await stack.aclose()
