"""
Shared utility functions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class TokenTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def add(self, response):
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.prompt_tokens += usage.get("input_tokens", 0)
            self.completion_tokens += usage.get("output_tokens", 0)
            self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def estimated_cost(self, input_price_per_m: float = 0.15, output_price_per_m: float = 0.60) -> float:
        return (self.prompt_tokens * input_price_per_m + self.completion_tokens * output_price_per_m) / 1_000_000

    def summary(self, phase: str) -> str:
        cost = self.estimated_cost()
        return (
            f"[{phase}] Tokens — input: {self.prompt_tokens:,}, output: {self.completion_tokens:,}, "
            f"total: {self.total_tokens:,} | LLM calls: {self.calls} | Est. cost: ${cost:.4f}"
        )


def load_job_requirements(path: str) -> dict:
    """Load job requirements from a JSON file."""
    with open(path) as f:
        return json.load(f)


def load_job_requirements_from_dir(directory: str) -> dict:
    """
    Load the first .json file found in the job requirements directory.
    Returns a default structure if no file is found.
    """
    if not os.path.isdir(directory):
        return _default_job_requirements()

    json_files = [f for f in os.listdir(directory) if f.endswith(".json")]
    if not json_files:
        return _default_job_requirements()

    return load_job_requirements(os.path.join(directory, json_files[0]))


def _default_job_requirements() -> dict:
    raise FileNotFoundError(
        "No job requirements JSON found in the job_requirements directory. "
        "Please add a department requirements file (see data/job_requirements/ge_intern_requirements.json "
        "for the expected format with a 'departments' key)."
    )
