"""
FastAPI backend for the HR Recruitment Dashboard.

Serves pipeline report data from JSON files and MLflow trace data.

Run:
    python dashboard/api.py
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import json
import os
import re
import sys
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="HR Recruitment Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
JOB_REQ_DIR = os.path.join(DATA_DIR, "job_requirements")


def _get_report_files() -> list[dict]:
    """List all report files with metadata, stats, and first-prompt labels."""
    pattern = os.path.join(DATA_DIR, "report_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    runs = []

    trace_prompts = _get_trace_first_prompts()

    for f in files:
        basename = os.path.basename(f)
        match = re.search(r"report_(\d{8}_\d{6})\.json", basename)
        if match:
            ts = match.group(1)
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
            run_time_ms = int(dt.timestamp() * 1000)

            stats = ""
            try:
                with open(f) as rf:
                    report = json.load(rf)
                summary = report.get("summary", {})
                total = summary.get("total_selected", 0) + summary.get("total_rejected", 0)
                accepted = summary.get("total_selected", 0)
                stats = f"{total} resumes · {accepted} accepted"
            except Exception:
                pass

            title = _find_matching_prompt(trace_prompts, run_time_ms)

            runs.append({
                "id": ts,
                "filename": basename,
                "path": f,
                "timestamp": dt.isoformat(),
                "label": dt.strftime("%b %d at %I:%M %p"),
                "title": title,
                "description": stats,
            })
    return runs


def _get_trace_first_prompts() -> list[tuple[int, str]]:
    """Get the first user prompt and timestamp from recent MLflow traces."""
    try:
        import mlflow
        import urllib.request

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        urllib.request.urlopen(tracking_uri, timeout=2)
        mlflow.set_tracking_uri(tracking_uri)

        exp = mlflow.get_experiment_by_name("recruitment-filtration-agent")
        if not exp:
            return []

        traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=50)
        prompts = []
        for _, row in traces.iterrows():
            request_time = int(row.get("request_time", 0) or 0)
            request_data = row.get("request")
            prompt = ""
            if isinstance(request_data, list):
                for msg in request_data:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        prompt = content[-1] if isinstance(content, list) else content
                        break
            if request_time and prompt:
                prompts.append((request_time, prompt))
        return prompts
    except Exception:
        return []


def _find_matching_prompt(prompts: list[tuple[int, str]], run_time_ms: int) -> str:
    """Find the first user prompt closest to a run's timestamp."""
    best = ""
    best_diff = float("inf")
    for trace_time, prompt in prompts:
        diff = abs(trace_time - run_time_ms)
        if diff < best_diff and diff < 10 * 60 * 1000:
            best_diff = diff
            best = prompt
    if len(best) > 60:
        best = best[:57] + "..."
    return best


def _load_report(run_id: str) -> dict:
    """Load a specific report by run ID."""
    path = os.path.join(DATA_DIR, f"report_{run_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Report {run_id} not found")
    with open(path) as f:
        return json.load(f)


@app.get("/api/runs")
def list_runs():
    """List all pipeline runs."""
    runs = _get_report_files()
    return {"runs": [{"id": r["id"], "label": r["label"], "timestamp": r["timestamp"], "title": r.get("title", ""), "description": r.get("description", "")} for r in runs]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    """Get full report data for a specific run."""
    report = _load_report(run_id)
    return report


@app.get("/api/departments")
def get_departments():
    """Get department requirements."""
    json_files = [f for f in os.listdir(JOB_REQ_DIR) if f.endswith(".json")]
    if not json_files:
        raise HTTPException(status_code=404, detail="No job requirements found")
    with open(os.path.join(JOB_REQ_DIR, json_files[0])) as f:
        return json.load(f)


@app.get("/api/traces")
def list_traces():
    """List recent MLflow traces."""
    try:
        import mlflow

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)

        exp = mlflow.get_experiment_by_name("recruitment-filtration-agent")
        if not exp:
            return {"traces": [], "status": "no_experiment"}

        traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=20)
        experiment_id = exp.experiment_id

        traces = mlflow.search_traces(experiment_ids=[experiment_id], max_results=20)
        trace_list = []
        for _, row in traces.iterrows():
            trace_id = row.get("trace_id", "")

            request_preview = ""
            request_data = row.get("request")
            if isinstance(request_data, list):
                for msg in reversed(request_data):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        request_preview = content[-1] if isinstance(content, list) else content
                        break

            response_data = row.get("response", "")
            response_preview = str(response_data)[:200] if response_data else ""

            state = row.get("state", "")
            status = state.value if hasattr(state, "value") else str(state)

            execution_ms = int(row.get("execution_duration", 0) or 0)
            request_time = int(row.get("request_time", 0) or 0)

            mlflow_url = f"{tracking_uri}/#/experiments/{experiment_id}/traces/{trace_id}"

            trace_list.append({
                "trace_id": trace_id,
                "timestamp": str(request_time),
                "status": status,
                "execution_time_ms": execution_ms,
                "request_preview": request_preview or "Agent run",
                "response_preview": response_preview,
                "mlflow_url": mlflow_url,
            })
        return {"traces": trace_list, "status": "ok"}
    except Exception as e:
        return {"traces": [], "status": "unavailable", "error": str(e)}


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str):
    """Get detailed trace data from MLflow."""
    try:
        import mlflow

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)

        trace = mlflow.get_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")

        spans = []
        for span in trace.data.spans:
            spans.append({
                "name": span.name,
                "span_type": str(span.span_type),
                "status": str(span.status.status_code) if span.status else "OK",
                "start_time": span.start_time_ns,
                "end_time": span.end_time_ns,
                "duration_ms": (span.end_time_ns - span.start_time_ns) / 1_000_000 if span.end_time_ns and span.start_time_ns else 0,
                "inputs": str(span.inputs)[:500] if span.inputs else None,
                "outputs": str(span.outputs)[:500] if span.outputs else None,
                "attributes": {k: str(v)[:200] for k, v in (span.attributes or {}).items()},
            })

        assessments = []
        for a in trace.info.assessments or []:
            assessments.append({
                "name": a.name,
                "value": a.value,
                "rationale": getattr(a, "rationale", None),
                "source": str(getattr(a, "source", "")),
            })

        request_text = str(trace.info.request_preview or "")
        response_text = str(trace.info.response_preview or "")

        if not request_text and trace.data.spans:
            root = trace.data.spans[0]
            if root.inputs and isinstance(root.inputs, list):
                for msg in root.inputs:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        request_text = content[-1] if isinstance(content, list) else content
                        break

        if not response_text and trace.data.spans:
            root = trace.data.spans[0]
            if root.outputs and isinstance(root.outputs, dict):
                response_text = root.outputs.get("final_output", "")
            elif root.outputs and isinstance(root.outputs, str):
                response_text = root.outputs

        exp_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "recruitment-filtration-agent")
        exp = mlflow.get_experiment_by_name(exp_name)
        experiment_id = exp.experiment_id if exp else "0"
        mlflow_url = f"{tracking_uri}/#/experiments/{experiment_id}/traces/{trace_id}"

        return {
            "trace_id": trace_id,
            "status": "ok",
            "request_preview": request_text,
            "response_preview": response_text,
            "spans": spans,
            "assessments": assessments,
            "mlflow_url": mlflow_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"trace_id": trace_id, "status": "unavailable", "error": str(e)}


# ── Post-message evaluation ──────────────────────────────

def _run_post_message_evaluation():
    """Run MLflow built-in agent evaluation scorers after a chat message."""
    try:
        import mlflow
        import mlflow.genai
        import urllib.request
        from mlflow.genai.scorers import (
            ToolCallCorrectness,
            ToolCallEfficiency,
            Completeness,
            RelevanceToQuery,
        )

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        urllib.request.urlopen(tracking_uri, timeout=2)
        mlflow.set_tracking_uri(tracking_uri)

        mlflow.flush_trace_async_logging()

        exp = mlflow.get_experiment_by_name(
            os.getenv("MLFLOW_EXPERIMENT_NAME", "recruitment-filtration-agent")
        )
        if not exp:
            return

        traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=1)
        if len(traces) == 0:
            return

        os.environ.setdefault(
            "MLFLOW_GENAI_JUDGE_DEFAULT_MODEL",
            f"openai:/{os.getenv('OPENAI_MODEL_NAME', 'gpt-5.4-mini')}",
        )

        mlflow.genai.evaluate(
            data=traces.head(1),
            scorers=[
                ToolCallCorrectness(),
                ToolCallEfficiency(),
                Completeness(),
                RelevanceToQuery(),
            ],
        )
    except Exception:
        pass


# ── Chat API ─────────────────────────────────────────────

_CITE_PATTERN = re.compile(r"\s*(?:citeturn|turn)\d+\S*", re.IGNORECASE)

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


class _ChatState:
    def __init__(self):
        self.agent = None
        self.mcp_servers = []
        self.stack = None
        self.messages: list[dict] = []
        self.ready = False

    async def ensure_ready(self):
        if self.ready:
            return
        from agent import create_agent
        self.agent, self.mcp_servers = create_agent()
        self.stack = contextlib.AsyncExitStack()
        for server in self.mcp_servers:
            await self.stack.enter_async_context(server)
        self.ready = True

    async def shutdown(self):
        if self.stack:
            await self.stack.aclose()
        self.ready = False


_chat = _ChatState()


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream a chat response from the agent via SSE."""
    from agents import Runner
    from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
    from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

    await _chat.ensure_ready()
    _chat.messages.append({"role": "user", "content": req.message})

    async def event_stream():
        result = Runner.run_streamed(_chat.agent, _chat.messages)

        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                if isinstance(event.data, ResponseTextDeltaEvent):
                    yield f"data: {json.dumps({'type': 'text', 'content': event.data.delta})}\n\n"

            elif isinstance(event, RunItemStreamEvent):
                if event.name == "tool_called":
                    raw = event.item.raw_item
                    tool_name = getattr(raw, "name", "") or ""
                    label = TOOL_LABELS.get(tool_name, f"Running {tool_name}")
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': label})}\n\n"

                elif event.name == "tool_output":
                    yield f"data: {json.dumps({'type': 'tool_done'})}\n\n"

        response = _CITE_PATTERN.sub("", result.final_output).rstrip()
        _chat.messages.append({"role": "assistant", "content": response})
        yield f"data: {json.dumps({'type': 'done', 'content': response})}\n\n"

        _run_post_message_evaluation()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chat/reset")
async def chat_reset():
    """Reset the chat conversation history."""
    _chat.messages.clear()
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown_chat():
    await _chat.shutdown()


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8001)
