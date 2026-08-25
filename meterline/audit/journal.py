"""The journal: an ordered record of what a run did."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from ..core.ids import digest_of
from ..version import version_string
from .events import Event, EventKind

__all__ = ["Journal"]


@dataclass(slots=True)
class Journal:
    """An append-only list of events with a stable digest.

    The journal carries no timestamps.  That is not an oversight: a run
    stamped with the wall clock cannot be compared byte-for-byte with the
    same run an hour later, and being able to make that comparison is the
    whole point of keeping the journal.
    """

    run_label: str = ""
    events: list[Event] = field(default_factory=list)

    def record(self, kind: EventKind, subject: str = "", **detail: Any) -> Event:
        """Append an event and return it."""

        event = Event.make(len(self.events) + 1, kind, subject, **detail)
        self.events.append(event)
        return event

    def started(self, dataset_name: str, fingerprint: str) -> None:
        """Record the opening event of a run."""

        self.record(
            EventKind.RUN_STARTED,
            dataset_name,
            engine=version_string(),
            fingerprint=fingerprint,
        )

    def finished(self, bills: int) -> None:
        """Record the closing event of a run."""

        self.record(EventKind.RUN_FINISHED, self.run_label, bills=bills)

    def of_kind(self, kind: EventKind) -> list[Event]:
        """Return every event of one kind."""

        return [event for event in self.events if event.kind is kind]

    @property
    def digest(self) -> str:
        """Return a content hash of the whole journal."""

        return digest_of([event.as_dict() for event in self.events])

    def render(self) -> str:
        """Render the journal, one event per line."""

        return "\n".join(event.render() for event in self.events)

    def as_list(self) -> list[dict[str, Any]]:
        """Return a JSON friendly view."""

        return [event.as_dict() for event in self.events]

    def __iter__(self) -> Iterator[Event]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)
