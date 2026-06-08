"""
Entry point for the recruitment filtration pipeline.

Usage:
    python main.py
    python main.py --resume-dir ./data/resumes --top-k 50
"""

import argparse
import asyncio
from datetime import datetime

from config.settings import (
    RESUME_DIR,
    JOB_REQUIREMENTS_DIR,
    TARGET_LOCATIONS,
    GRADUATION_EARLIEST,
    GRADUATION_LATEST,
    TOP_K_CANDIDATES,
)
from src.graph import build_pipeline
from src.utils.helpers import load_job_requirements_from_dir
from src.utils.tracing import PipelineTracer, set_tracer


def parse_args():
    parser = argparse.ArgumentParser(
        description="Red Hat Engineering Internship — Recruitment Filtration Agent"
    )
    parser.add_argument(
        "--resume-dir", default=RESUME_DIR, help="Directory containing resume PDFs"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=TOP_K_CANDIDATES,
        help="Number of top candidates to select",
    )
    parser.add_argument(
        "--locations",
        nargs="+",
        default=None,
        help="Target locations (overrides .env)",
    )
    parser.add_argument(
        "--no-mlflow",
        action="store_true",
        help="Disable MLflow tracing",
    )
    return parser.parse_args()


async def run():
    args = parse_args()

    locations = (
        [loc.lower().strip() for loc in args.locations]
        if args.locations
        else TARGET_LOCATIONS
    )

    job_requirements = load_job_requirements_from_dir(JOB_REQUIREMENTS_DIR)

    initial_state = {
        "candidates": [],
        "job_requirements": job_requirements,
        "resume_dir": args.resume_dir,
        "target_locations": locations,
        "graduation_earliest": GRADUATION_EARLIEST,
        "graduation_latest": GRADUATION_LATEST,
        "top_k": args.top_k,
        "current_phase": "start",
        "errors": [],
        "summary": {},
    }

    tracer = None
    if not args.no_mlflow:
        tracer = PipelineTracer()
        run_name = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tracer.start_run(
            run_name=run_name,
            tags={
                "pipeline_version": "1.0",
                "role": job_requirements.get("role", "N/A"),
                "organization": job_requirements.get("organization", "N/A"),
            },
        )
        tracer.log_params({
            "resume_dir": args.resume_dir,
            "top_k": args.top_k,
            "target_locations": ",".join(locations),
            "graduation_earliest": GRADUATION_EARLIEST,
            "graduation_latest": GRADUATION_LATEST,
            "num_departments": len(job_requirements.get("departments", {})),
        })
        set_tracer(tracer)
        print("  MLflow tracing:    ENABLED")
    else:
        print("  MLflow tracing:    DISABLED")

    print("=" * 60)
    print("  Red Hat Engineering — Recruitment Filtration Agent")
    print("=" * 60)
    print(f"  Resume directory:  {args.resume_dir}")
    print(f"  Target locations:  {locations}")
    print(f"  Graduation window: {GRADUATION_EARLIEST} to {GRADUATION_LATEST}")
    print(f"  Top K candidates:  {args.top_k}")
    print(f"  Job requirements:  {job_requirements.get('role', 'N/A')}")
    print("=" * 60)
    print()

    pipeline = build_pipeline()
    result = await pipeline.ainvoke(initial_state)

    if result.get("errors"):
        print(f"\n[Warnings/Errors during pipeline run]")
        for err in result["errors"]:
            print(f"  - {err}")

    if tracer:
        tracer.log_pipeline_summary(result.get("summary", {}))
        tracer.log_errors(result.get("errors", []))
        tracer.log_candidate_scores(result.get("candidates", []))
        tracer.end_run()
        set_tracer(None)
        print("\n[MLflow] Run logged successfully. View with: mlflow ui")

    return result


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
