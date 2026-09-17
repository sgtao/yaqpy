"""Evaluation step counting and deadlines (NFR-05)."""

from __future__ import annotations

import threading
import time

from pyyq.errors import EvaluationLimitError


class StepBudget:
    """Counts evaluation steps and checks a deadline. One instance per evaluation."""

    __slots__ = ("max_steps", "deadline", "steps", "_cancelled")

    def __init__(self, max_steps: int | None = None, timeout_seconds: float | None = None) -> None:
        self.max_steps = max_steps
        self.deadline = (time.monotonic() + timeout_seconds) if timeout_seconds else None
        self.steps = 0
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def tick(self) -> None:
        self.steps += 1
        if self.max_steps is not None and self.steps > self.max_steps:
            raise EvaluationLimitError(
                f"evaluation exceeded {self.max_steps} steps", limit="max_steps")
        if self.deadline is not None and (self.steps & 0x3F) == 0 and time.monotonic() > self.deadline:
            raise EvaluationLimitError("evaluation exceeded the time limit", limit="timeout_seconds")
        if self._cancelled.is_set():
            raise EvaluationLimitError("evaluation was cancelled", limit="cancelled")
