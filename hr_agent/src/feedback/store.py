"""
Feedback storage — persists human reviewer feedback on candidate scores.

Each feedback entry records: which candidate, what the LLM scored,
what the human thinks the score should be, and why. This history
drives the self-optimization loop.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime


FEEDBACK_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback")


@dataclass
class FeedbackEntry:
    candidate_id: str
    candidate_name: str
    department: str
    llm_score: float
    human_score: float | None = None
    action: str = ""  # "approve", "reject", "adjust"
    reason: str = ""
    skill_overrides: dict = field(default_factory=dict)
    timestamp: str = ""
    run_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FeedbackStore:
    def __init__(self, feedback_dir: str = FEEDBACK_DIR):
        self.feedback_dir = feedback_dir
        os.makedirs(self.feedback_dir, exist_ok=True)
        self._entries: list[FeedbackEntry] = []
        self._load()

    def _filepath(self) -> str:
        return os.path.join(self.feedback_dir, "feedback_history.json")

    def _load(self):
        path = self._filepath()
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self._entries = [FeedbackEntry(**e) for e in data]

    def _save(self):
        with open(self._filepath(), "w") as f:
            json.dump([asdict(e) for e in self._entries], f, indent=2)

    def add(self, entry: FeedbackEntry):
        self._entries.append(entry)
        self._save()

    def add_batch(self, entries: list[FeedbackEntry]):
        self._entries.extend(entries)
        self._save()

    def get_all(self) -> list[FeedbackEntry]:
        return list(self._entries)

    def get_for_department(self, department: str) -> list[FeedbackEntry]:
        return [e for e in self._entries if e.department == department]

    def get_rejections(self) -> list[FeedbackEntry]:
        return [e for e in self._entries if e.action == "reject"]

    def get_adjustments(self) -> list[FeedbackEntry]:
        return [e for e in self._entries if e.action == "adjust"]

    def summary(self) -> dict:
        if not self._entries:
            return {"total": 0}

        approvals = sum(1 for e in self._entries if e.action == "approve")
        rejections = sum(1 for e in self._entries if e.action == "reject")
        adjustments = sum(1 for e in self._entries if e.action == "adjust")

        score_diffs = [
            e.human_score - e.llm_score
            for e in self._entries
            if e.human_score is not None
        ]

        return {
            "total": len(self._entries),
            "approvals": approvals,
            "rejections": rejections,
            "adjustments": adjustments,
            "approval_rate": round(approvals / len(self._entries) * 100, 1),
            "avg_score_adjustment": round(sum(score_diffs) / max(len(score_diffs), 1), 2) if score_diffs else 0,
            "bias_direction": "overscoring" if sum(score_diffs) < 0 else "underscoring" if sum(score_diffs) > 0 else "neutral",
        }
