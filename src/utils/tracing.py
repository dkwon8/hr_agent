"""
MLflow tracing integration for the recruitment pipeline.

Provides a PipelineTracer that creates a parent run per pipeline execution
with nested child spans for each phase. Logs LLM inputs/outputs, candidate
scores, token usage, and pipeline summaries.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager

import mlflow
from mlflow.entities import SpanType

from config.settings import MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT_NAME


_active_tracer: PipelineTracer | None = None


def get_tracer() -> PipelineTracer | None:
    return _active_tracer


def set_tracer(tracer: PipelineTracer | None):
    global _active_tracer
    _active_tracer = tracer


class PipelineTracer:
    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
        self._run = None
        self._phase_start_times: dict[str, float] = {}

    def start_run(self, run_name: str, tags: dict | None = None):
        self._run = mlflow.start_run(run_name=run_name, tags=tags or {})
        return self._run

    def end_run(self):
        if self._run:
            mlflow.end_run()
            self._run = None

    def log_params(self, params: dict):
        mlflow.log_params(params)

    @contextmanager
    def phase(self, phase_name: str):
        self._phase_start_times[phase_name] = time.time()
        span = mlflow.start_span(
            name=phase_name,
            span_type=SpanType.CHAIN,
        )
        try:
            yield span
        finally:
            elapsed = time.time() - self._phase_start_times[phase_name]
            mlflow.log_metric(f"{phase_name}/duration_seconds", round(elapsed, 2))
            span.end()

    def log_llm_call(self, phase: str, candidate_id: str, prompt: str, response: str, token_info: dict | None = None):
        span = mlflow.start_span(
            name=f"{phase}/llm/{candidate_id}",
            span_type=SpanType.LLM,
        )
        span.set_inputs({"prompt": prompt[:2000]})
        span.set_outputs({"response": response[:2000]})
        if token_info:
            span.set_attributes(token_info)
        span.end()

    def log_phase_metrics(self, phase: str, metrics: dict):
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(f"{phase}/{key}", value)

    def log_token_usage(self, phase: str, tracker):
        mlflow.log_metrics({
            f"{phase}/input_tokens": tracker.prompt_tokens,
            f"{phase}/output_tokens": tracker.completion_tokens,
            f"{phase}/total_tokens": tracker.total_tokens,
            f"{phase}/llm_calls": tracker.calls,
            f"{phase}/estimated_cost_usd": round(tracker.estimated_cost(), 6),
        })

    def log_candidate_scores(self, candidates: list):
        scores = []
        for c in candidates:
            if c.quality_score > 0:
                scores.append({
                    "id": c.id,
                    "name": c.name,
                    "score": c.quality_score,
                    "best_fit_department": c.best_fit_department,
                    "status": c.status.value if hasattr(c.status, "value") else c.status,
                })

        if scores:
            mlflow.log_metric("scoring/num_scored", len(scores))
            mlflow.log_metric("scoring/max_score", max(s["score"] for s in scores))
            mlflow.log_metric("scoring/min_score", min(s["score"] for s in scores))
            mlflow.log_metric("scoring/avg_score", round(sum(s["score"] for s in scores) / len(scores), 2))

            mlflow.log_text(
                json.dumps(scores, indent=2),
                "candidate_scores.json",
            )

    def log_pipeline_summary(self, summary: dict):
        mlflow.log_metrics({
            "pipeline/total_resumes": summary.get("total_resumes", 0),
            "pipeline/passed_deterministic": summary.get("passed_deterministic", 0),
            "pipeline/flagged": summary.get("flagged_cross_validation", 0),
            "pipeline/total_scored": summary.get("total_scored", 0),
            "pipeline/total_selected": summary.get("total_selected", 0),
            "pipeline/total_rejected": summary.get("total_rejected", 0),
        })

        if summary.get("top_score") is not None:
            mlflow.log_metric("pipeline/top_score", summary["top_score"])
        if summary.get("bottom_selected_score") is not None:
            mlflow.log_metric("pipeline/cutoff_score", summary["bottom_selected_score"])

    def log_report(self, report: dict, report_path: str):
        mlflow.log_artifact(report_path)
        mlflow.log_text(
            json.dumps(report.get("summary", {}), indent=2),
            "pipeline_summary.json",
        )

    def log_errors(self, errors: list[str]):
        if errors:
            mlflow.log_metric("pipeline/error_count", len(errors))
            mlflow.log_text("\n".join(errors), "pipeline_errors.txt")
