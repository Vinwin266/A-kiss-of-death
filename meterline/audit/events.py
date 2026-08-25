"""Journal events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["EventKind", "Event"]


class EventKind(str, Enum):
    """What kind of thing happened."""

    RUN_STARTED = "run_started"
    DATASET_LOADED = "dataset_loaded"
    PROFILE_SELECTED = "profile_selected"
    CYCLE_RATED = "cycle_rated"
    BILL_ISSUED = "bill_issued"
    BILL_HELD = "bill_held"
    ADJUSTMENT_POSTED = "adjustment_posted"
    BANK_MOVEMENT = "bank_movement"
    RUN_FINISHED = "run_finished"

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` for the event that closes a run."""

        return self is EventKind.RUN_FINISHED


@dataclass(frozen=True, slots=True)
class Event:
    """One recorded step of a run."""

    sequence: int
    kind: EventKind
    subject: str = ""
    detail: tuple[tuple[str, str], ...] = ()

    @classmethod
    def make(
        cls, sequence: int, kind: EventKind, subject: str = "", **detail: Any
    ) -> "Event":
        """Build an event with keyword detail."""

        rendered = tuple(sorted((key, str(value)) for key, value in detail.items()))
        return cls(sequence, kind, subject, rendered)

    def render(self) -> str:
        """Render as one line."""

        head = f"{self.sequence:04d} {self.kind.value}"
        if self.subject:
            head = f"{head} {self.subject}"
        if not self.detail:
            return head
        rendered = " ".join(f"{key}={value}" for key, value in self.detail)
        return f"{head} {rendered}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view."""

        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "subject": self.subject,
            "detail": dict(self.detail),
        }
