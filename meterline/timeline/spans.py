"""Half-open spans of instants.

Every period in the engine is ``[start, end)``.  Adjacent spans therefore
tile without overlap and without a missing microsecond, which is what makes
"the meter was read at midnight" unambiguous: that read belongs to the day
starting at midnight, not to the one ending there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Iterator, Sequence

from ..core.decimals import D, safe_divide
from ..errors import TimelineError
from .instants import ensure_utc, format_instant

__all__ = ["Span", "merge_spans", "subtract_spans", "intersect_all", "total_hours"]


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open interval of UTC instants."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = ensure_utc(self.start, what="span start")
        end = ensure_utc(self.end, what="span end")
        if end < start:
            raise TimelineError(
                "a span cannot end before it starts",
                start=format_instant(start),
                end=format_instant(end),
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    # -- construction ---------------------------------------------------

    @classmethod
    def of_length(cls, start: datetime, length: timedelta) -> "Span":
        """Return the span beginning at ``start`` lasting ``length``."""

        return cls(start, start + length)

    @classmethod
    def of_minutes(cls, start: datetime, minutes: int) -> "Span":
        """Return the span beginning at ``start`` lasting ``minutes``."""

        return cls.of_length(start, timedelta(minutes=minutes))

    # -- measurement ----------------------------------------------------

    @property
    def duration(self) -> timedelta:
        """Return the length of the span."""

        return self.end - self.start

    @property
    def seconds(self) -> int:
        """Return the length in whole seconds."""

        return int(self.duration.total_seconds())

    @property
    def hours(self) -> Decimal:
        """Return the length in hours, exactly."""

        return safe_divide(D(self.seconds), D(3600))

    @property
    def is_empty(self) -> bool:
        """Return ``True`` for a zero-length span."""

        return self.start == self.end

    # -- relations ------------------------------------------------------

    def contains(self, moment: datetime) -> bool:
        """Return ``True`` when ``moment`` falls inside the half-open span."""

        normalised = ensure_utc(moment)
        return self.start <= normalised < self.end

    def contains_span(self, other: "Span") -> bool:
        """Return ``True`` when ``other`` lies entirely within this span."""

        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: "Span") -> bool:
        """Return ``True`` when the two spans share any instant."""

        return self.start < other.end and other.start < self.end

    def abuts(self, other: "Span") -> bool:
        """Return ``True`` when the spans touch without overlapping."""

        return self.end == other.start or other.end == self.start

    def intersection(self, other: "Span") -> "Span | None":
        """Return the shared span, or ``None`` when they do not overlap."""

        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if end <= start:
            return None
        return Span(start, end)

    def clamp(self, bounds: "Span") -> "Span | None":
        """Restrict this span to ``bounds``."""

        return self.intersection(bounds)

    def union(self, other: "Span") -> "Span":
        """Return the smallest span covering both."""

        if not (self.overlaps(other) or self.abuts(other)):
            raise TimelineError("cannot union disjoint spans")
        return Span(min(self.start, other.start), max(self.end, other.end))

    # -- subdivision ----------------------------------------------------

    def split_at(self, moment: datetime) -> tuple["Span", "Span"]:
        """Split into the parts before and after ``moment``."""

        cut = ensure_utc(moment)
        if not self.contains(cut):
            raise TimelineError(
                "split point lies outside the span", at=format_instant(cut)
            )
        return Span(self.start, cut), Span(cut, self.end)

    def steps(self, minutes: int) -> Iterator["Span"]:
        """Yield consecutive sub-spans of ``minutes``, clipping the last."""

        if minutes <= 0:
            raise TimelineError("step must be positive", minutes=minutes)
        width = timedelta(minutes=minutes)
        cursor = self.start
        while cursor < self.end:
            nxt = min(cursor + width, self.end)
            yield Span(cursor, nxt)
            cursor = nxt

    def local_days(self, zone) -> list[tuple[date, "Span"]]:  # noqa: ANN001
        """Split the span into local calendar days.

        The returned sub-spans are the *actual* extent of each local day, so
        a spring-forward day is 23 hours long and an autumn one 25.  Code
        that assumes 24 produces a bill an hour short twice a year.
        """

        if self.is_empty:
            return []
        result: list[tuple[date, Span]] = []
        cursor = self.start
        while cursor < self.end:
            day = zone.local_date(cursor)
            day_end = zone.day_start(day + timedelta(days=1))
            piece_end = min(day_end, self.end)
            if piece_end <= cursor:  # pragma: no cover - defensive
                break
            result.append((day, Span(cursor, piece_end)))
            cursor = piece_end
        return result

    # -- rendering ------------------------------------------------------

    def describe(self) -> str:
        """Render as ``[start, end)``."""

        return f"[{format_instant(self.start)}, {format_instant(self.end)})"

    def __str__(self) -> str:
        return self.describe()


def total_hours(spans: Iterable[Span]) -> Decimal:
    """Sum the durations of ``spans`` in hours."""

    total = D(0)
    for span in spans:
        total += span.hours
    return total


def merge_spans(spans: Sequence[Span]) -> list[Span]:
    """Merge overlapping and touching spans into a minimal cover."""

    if not spans:
        return []
    ordered = sorted(spans, key=lambda span: (span.start, span.end))
    merged = [ordered[0]]
    for span in ordered[1:]:
        last = merged[-1]
        if span.start <= last.end:
            merged[-1] = Span(last.start, max(last.end, span.end))
        else:
            merged.append(span)
    return merged


def subtract_spans(base: Span, cuts: Sequence[Span]) -> list[Span]:
    """Return the parts of ``base`` not covered by ``cuts``."""

    remaining = [base]
    for cut in merge_spans(list(cuts)):
        nxt: list[Span] = []
        for piece in remaining:
            if not piece.overlaps(cut):
                nxt.append(piece)
                continue
            if piece.start < cut.start:
                nxt.append(Span(piece.start, cut.start))
            if cut.end < piece.end:
                nxt.append(Span(cut.end, piece.end))
        remaining = nxt
    return remaining


def intersect_all(spans: Sequence[Span]) -> Span | None:
    """Return the span common to every input, or ``None``."""

    if not spans:
        return None
    current: Span | None = spans[0]
    for span in spans[1:]:
        if current is None:
            return None
        current = current.intersection(span)
    return current
