"""Tariff enrolment history and how it is resolved mid-cycle.

A customer who switches rate on the 12th of a 30-day cycle has been on two
tariffs.  Utilities resolve that three ways, and the difference on a tiered
rate is substantial: split the cycle into two sub-periods and rate each,
apply whichever tariff was in force on the read date to the whole cycle, or
apply whichever tariff covered the majority of days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence

from ..errors import ConfigurationError, RatingError
from ..timeline.instants import ensure_utc, format_instant
from ..timeline.spans import Span

__all__ = ["EnrollmentResolution", "TariffEnrollment", "EnrollmentHistory"]


class EnrollmentResolution(str, Enum):
    """How a cycle spanning a tariff change is rated."""

    SPLIT = "split"
    """Rate each sub-period on its own tariff and add the results."""

    AT_END = "at_end"
    """Rate the whole cycle on the tariff in force at the cycle end."""

    AT_START = "at_start"
    """Rate the whole cycle on the tariff in force at the cycle start."""

    MAJORITY = "majority"
    """Rate the whole cycle on whichever tariff covered the most days."""


@dataclass(frozen=True, slots=True)
class TariffEnrollment:
    """A service point's enrolment on a tariff over a span of time."""

    service_point_id: str
    tariff_code: str
    effective_from: datetime
    effective_to: datetime | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "effective_from", ensure_utc(self.effective_from, what="enrolment start")
        )
        if self.effective_to is not None:
            end = ensure_utc(self.effective_to, what="enrolment end")
            if end <= self.effective_from:
                raise ConfigurationError(
                    "enrolment ends before it starts",
                    service_point=self.service_point_id,
                    tariff=self.tariff_code,
                )
            object.__setattr__(self, "effective_to", end)

    def covers(self, moment: datetime) -> bool:
        """Return ``True`` when the enrolment is in force at ``moment``."""

        normalised = ensure_utc(moment)
        if normalised < self.effective_from:
            return False
        return self.effective_to is None or normalised < self.effective_to

    def overlap(self, span: Span) -> Span | None:
        """Return the part of ``span`` this enrolment covers."""

        end = self.effective_to or span.end
        return span.intersection(Span(self.effective_from, max(end, self.effective_from)))

    def describe(self) -> str:
        """Return a one-line description for reports."""

        end = format_instant(self.effective_to) if self.effective_to else "open"
        return f"{self.tariff_code}: {format_instant(self.effective_from)} to {end}"


@dataclass(frozen=True, slots=True)
class EnrollmentHistory:
    """The ordered enrolments of one service point."""

    service_point_id: str
    entries: tuple[TariffEnrollment, ...] = ()

    @classmethod
    def of(
        cls, service_point_id: str, entries: Sequence[TariffEnrollment]
    ) -> "EnrollmentHistory":
        """Build a history with entries sorted and implicitly closed.

        An enrolment with no end date is closed when the next one begins.
        A customer is on one tariff at a time, and leaving both open would
        rate the overlap under each of them.
        """

        ordered = sorted(entries, key=lambda entry: entry.effective_from)
        closed: list[TariffEnrollment] = []
        for index, entry in enumerate(ordered):
            successor = ordered[index + 1] if index + 1 < len(ordered) else None
            if (
                successor is not None
                and entry.effective_to is None
                and successor.effective_from > entry.effective_from
            ):
                entry = TariffEnrollment(
                    entry.service_point_id,
                    entry.tariff_code,
                    entry.effective_from,
                    successor.effective_from,
                    entry.reason,
                )
            closed.append(entry)
        return cls(service_point_id, tuple(closed))

    def at(self, moment: datetime) -> TariffEnrollment | None:
        """Return the enrolment in force at ``moment``, if any."""

        found: TariffEnrollment | None = None
        for entry in self.entries:
            if entry.covers(moment):
                found = entry
        return found

    def segments(self, span: Span) -> list[tuple[Span, TariffEnrollment]]:
        """Return the sub-spans of ``span`` and the tariff covering each."""

        pieces: list[tuple[Span, TariffEnrollment]] = []
        for entry in self.entries:
            overlap = entry.overlap(span)
            if overlap is not None and not overlap.is_empty:
                pieces.append((overlap, entry))
        pieces.sort(key=lambda item: item[0].start)
        return pieces

    def resolve(
        self, span: Span, how: EnrollmentResolution = EnrollmentResolution.SPLIT
    ) -> list[tuple[Span, TariffEnrollment]]:
        """Return the (span, enrolment) pairs to rate under ``how``."""

        pieces = self.segments(span)
        if not pieces:
            raise RatingError(
                "no tariff enrolment covers this period",
                service_point=self.service_point_id,
                span=span.describe(),
            )
        if how is EnrollmentResolution.SPLIT:
            return pieces
        if how is EnrollmentResolution.AT_START:
            return [(span, pieces[0][1])]
        if how is EnrollmentResolution.AT_END:
            return [(span, pieces[-1][1])]
        widest = max(pieces, key=lambda item: (item[0].seconds, item[0].start))
        return [(span, widest[1])]

    @property
    def is_continuous(self) -> bool:
        """Return ``True`` when the enrolments leave no gap between them."""

        for earlier, later in zip(self.entries, self.entries[1:]):
            if earlier.effective_to is None:
                continue
            if earlier.effective_to < later.effective_from:
                return False
        return True

    def codes(self) -> list[str]:
        """Return the distinct tariff codes in the history, in order."""

        seen: list[str] = []
        for entry in self.entries:
            if entry.tariff_code not in seen:
                seen.append(entry.tariff_code)
        return seen
