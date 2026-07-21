"""
Improve module — analyzes MLflow traces to detect agent quality issues.

Proxies to the MLflow fork's improve endpoint (which uses statistical
baselines and LLM code analysis). Falls back to a local tag-based
analyzer if the MLflow fork server is unreachable.

Usage:
    from improve import analyze

    result = analyze(experiment_name="recruitment-filtration-agent")

    for s in result["suggestions"]:
        print(f"[{s['severity']}] {s['title']}: {s['action']}")
"""

from __future__ import annotations

import logging
import os

from .analyzer import analyze_traces, Finding  # noqa: F401 — used by _local_analyze
from .suggestions import generate_suggestions, Suggestion  # noqa: F401 — used by _local_analyze

_logger = logging.getLogger(__name__)

_MLFLOW_SERVER = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")


def analyze(
    experiment_name: str,
    trace_count: int = 20,
    tracking_uri: str | None = None,
) -> dict:
    """Analyze recent traces and generate improvement suggestions.

    Delegates to the MLflow fork's improve endpoint (statistical baselines,
    LLM code analysis). Falls back to the local tag-based analyzer if the
    MLflow fork server is unreachable.
    """
    server = tracking_uri or _MLFLOW_SERVER
    try:
        return _proxy_to_mlflow(server, experiment_name, trace_count)
    except Exception as e:
        _logger.warning("MLflow improve proxy failed (%s), falling back to local analyzer", e)
        return _local_analyze(experiment_name, trace_count, tracking_uri)


def _proxy_to_mlflow(server: str, experiment_name: str, trace_count: int) -> dict:
    """Call the MLflow fork's improve endpoint over HTTP."""
    import httpx
    import mlflow

    mlflow.set_tracking_uri(server)
    exp = mlflow.get_experiment_by_name(experiment_name)
    if not exp:
        return {
            "findings": [],
            "suggestions": [],
            "summary": {"status": "no_experiment", "experiment_name": experiment_name},
        }

    resp = httpx.post(
        f"{server}/ajax-api/3.0/mlflow/improve/invoke",
        json={
            "experiment_id": exp.experiment_id,
            "trace_count": trace_count,
            "mode": "traces_only",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _local_analyze(
    experiment_name: str,
    trace_count: int = 20,
    tracking_uri: str | None = None,
) -> dict:
    """Fallback: local tag-based analyzer (Level 1 hardcoded thresholds)."""
    import mlflow

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    exp = mlflow.get_experiment_by_name(experiment_name)
    if not exp:
        return {
            "findings": [],
            "suggestions": [],
            "summary": {"status": "no_experiment", "experiment_name": experiment_name},
        }

    raw_traces = mlflow.search_traces(
        experiment_ids=[exp.experiment_id],
        max_results=trace_count,
    )

    if len(raw_traces) == 0:
        return {
            "findings": [],
            "suggestions": [],
            "summary": {"status": "no_traces", "experiment_name": experiment_name},
        }

    traces_data = []
    for _, row in raw_traces.iterrows():
        trace_id = row.get("trace_id", "")

        tags = row.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}

        assessments = []
        raw_assessments = row.get("assessments", [])
        if isinstance(raw_assessments, list):
            for a in raw_assessments:
                if isinstance(a, dict):
                    assessments.append(a)
                else:
                    assessments.append({
                        "name": getattr(a, "assessment_name", getattr(a, "name", "")),
                        "value": getattr(a, "string_value", getattr(a, "value", "")),
                    })

        traces_data.append({
            "trace_id": trace_id,
            "tags": tags,
            "assessments": assessments,
            "execution_duration": int(row.get("execution_duration", 0) or 0),
        })

    findings = analyze_traces(traces_data)
    suggestions = generate_suggestions(findings)

    model_tags = [t["tags"].get("agent.model", "") for t in traces_data if t["tags"].get("agent.model")]
    current_model = model_tags[0] if model_tags else "unknown"

    avg_tool_calls = 0
    tool_counts = [int(t["tags"].get("agent.tool_call_count", 0)) for t in traces_data if t["tags"].get("agent.tool_call_count")]
    if tool_counts:
        avg_tool_calls = sum(tool_counts) / len(tool_counts)

    return {
        "findings": [
            {
                "pattern": f.pattern,
                "severity": f.severity,
                "category": f.category,
                "description": f.description,
                "evidence": f.evidence,
            }
            for f in findings
        ],
        "suggestions": [
            {
                "id": s.id,
                "type": s.type,
                "severity": s.severity,
                "category": s.category,
                "title": s.title,
                "description": s.description,
                "action": s.action,
                "confidence": s.confidence,
                "auto_applicable": s.auto_applicable,
                "evidence": s.evidence,
            }
            for s in suggestions
        ],
        "summary": {
            "status": "ok",
            "experiment_name": experiment_name,
            "traces_analyzed": len(traces_data),
            "findings_count": len(findings),
            "suggestions_count": len(suggestions),
            "current_model": current_model,
            "avg_tool_calls": round(avg_tool_calls, 1),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "medium_severity": sum(1 for f in findings if f.severity == "medium"),
        },
    }


def build_harness_prompt(
    suggestions: list[dict],
    traces_summary: dict,
    repo_path: str,
) -> str:
    """Construct a prompt for the coding harness based on analysis results."""
    heal_suggestions = [s for s in suggestions if s.get("category") == "heal"]
    improve_suggestions = [s for s in suggestions if s.get("category") == "improve"]

    lines = [
        "You are analyzing and fixing an AI agent's codebase based on issues "
        "detected from its execution traces. Make minimal, focused changes.",
        "",
        "## Trace Analysis Summary",
        f"- Traces analyzed: {traces_summary.get('traces_analyzed', 'N/A')}",
        f"- Current model: {traces_summary.get('current_model', 'unknown')}",
        f"- Average tool calls per run: {traces_summary.get('avg_tool_calls', 'N/A')}",
    ]
    if traces_summary.get("high_severity"):
        lines.append(f"- High severity issues: {traces_summary['high_severity']}")
    if traces_summary.get("medium_severity"):
        lines.append(f"- Medium severity issues: {traces_summary['medium_severity']}")
    lines.append("")

    idx = 1
    if heal_suggestions:
        lines.append("## Critical: Errors & Failures (fix these first)")
        for s in heal_suggestions:
            lines.append(f"### {idx}. [{s['severity'].upper()}] {s['title']}")
            lines.append(f"**Type:** {s['type']}")
            lines.append(f"**Description:** {s['description']}")
            lines.append(f"**Recommended action:** {s['action']}")
            if s.get("evidence"):
                evidence_items = ", ".join(f"{k}={v}" for k, v in s["evidence"].items())
                lines.append(f"**Evidence:** {evidence_items}")
            lines.append("")
            idx += 1

    if improve_suggestions:
        lines.append("## Optimization Opportunities")
        for s in improve_suggestions:
            lines.append(f"### {idx}. [{s['severity'].upper()}] {s['title']}")
            lines.append(f"**Type:** {s['type']}")
            lines.append(f"**Description:** {s['description']}")
            lines.append(f"**Recommended action:** {s['action']}")
            if s.get("evidence"):
                evidence_items = ", ".join(f"{k}={v}" for k, v in s["evidence"].items())
                lines.append(f"**Evidence:** {evidence_items}")
            lines.append("")
            idx += 1

    lines.extend([
        "## Instructions",
        "- Fix errors and failures first, then apply optimizations.",
        "- Make minimal, focused changes. Do not refactor unrelated code.",
        "- Prefer changes to configuration, prompts, and system instructions over architectural changes.",
        "- If a suggestion recommends a model change, update the relevant configuration or environment variable.",
        "- If a suggestion recommends a prompt fix, edit the system prompt or instructions file.",
        f"- The repository is at: {repo_path}",
        "",
    ])

    return "\n".join(lines)


__all__ = ["analyze", "build_harness_prompt"]
