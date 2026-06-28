"""
FastAPI backend for the HR Recruitment Dashboard.

Serves pipeline report data from JSON files and MLflow trace data.

Run:
    python dashboard/api.py
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

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
    """List all report files with metadata."""
    pattern = os.path.join(DATA_DIR, "report_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    runs = []
    for f in files:
        basename = os.path.basename(f)
        match = re.search(r"report_(\d{8}_\d{6})\.json", basename)
        if match:
            ts = match.group(1)
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
            runs.append({
                "id": ts,
                "filename": basename,
                "path": f,
                "timestamp": dt.isoformat(),
                "label": dt.strftime("%b %d, %Y at %I:%M %p"),
            })
    return runs


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
    return {"runs": [{"id": r["id"], "label": r["label"], "timestamp": r["timestamp"]} for r in runs]}


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


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8001)
