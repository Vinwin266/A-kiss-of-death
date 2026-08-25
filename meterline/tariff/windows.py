"""Time-of-use windows and the buckets they assign hours to.

A window is a range of wall-clock minutes on a set of day types, optionally
restricted to a season.  Two things make this harder than it looks:

* windows overlap, and which one wins is a convention, not a fact;
* wall-clock minutes are not real time twice a year, so a window cannot be
  turned into a span by adding minutes to midnight.

The second is why :func:`bucket_spans` walks real instants and re-derives
the wall clock at each step rather than the other way round.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Sequence

from ..constants import MINUTES_PER_DAY
from ..errors import TariffError
from ..policy.conventions import WindowPrecedence
from ..timeline.daytypes import DayType, DayTypeRules, classify_day
from ..timeline.holidays import HolidayCalendar
from ..timeline.spans import Span, merge_spans
from ..timeline.zones import Zone
from .seasons import SeasonSet

__all__ = ["TimeWindow", "WindowSet", "bucket_spans", "parse_clock"]


def parse_clock(text: str) -> int:
    """Parse ``"14:30"`` into minutes past local midnight.

    ``"24:00"`` is accepted and means the end of the day, which is how rate
    sheets write a window that runs to midnight without implying it also
    covers the first instant of the next one.
    """

    parts = text.strip().split(":")
    if len(parts) != 2:
        raise TariffError("clock times look like HH:MM", value=text)
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        raise TariffError("clock times look like HH:MM", value=text) from None
    total = hours * 60 + minutes
    if not 0 <= total <= MINUTES_PER_DAY:
        raise TariffError("clock time out of range", value=text)
    return total


def format_clock(minutes: int) -> str:
    """Render minutes past midnight as ``"14:30"``."""

    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A named period of the day that maps usage into a bucket."""

    bucket: str
    start_minute: int
    end_minute: int
    day_types: tuple[DayType, ...] = ()
    """Day types the window applies to; empty means every day type."""

    season_code: str = ""
    """Season the window is restricted to; empty means all year."""

    label: str = ""

    def __post_init__(self) -> None:
        for value in (self.start_minute, self.end_minute):
            if not 0 <= value <= MINUTES_PER_DAY:
                raise TariffError(
                    "window boundary out of range", bucket=self.bucket, minute=value
                )
        if self.start_minute == self.end_minute:
            raise TariffError("window has zero length", bucket=self.bucket)

    @classmethod
    def between(
        cls,
        bucket: str,
        start: str,
        end: str,
        day_types: Sequence[DayType] = (),
        season_code: str = "",
        label: str = "",
    ) -> "TimeWindow":
        """Build a window from ``"08:00"``-style clock strings."""

        return cls(
            bucket,
            parse_clock(start),
            parse_clock(end),
            tuple(day_types),
            season_code,
            label,
        )

    @property
    def wraps_midnight(self) -> bool:
        """Return ``True`` when the window runs past midnight."""

        return self.end_minute < self.start_minute

    @property
    def length_minutes(self) -> int:
        """Return the window's length in minutes of wall clock."""

        if self.wraps_midnight:
            return MINUTES_PER_DAY - self.start_minute + self.end_minute
        return self.end_minute - self.start_minute

    def covers_minute(self, minute: int) -> bool:
        """Return ``True`` when ``minute`` past midnight is in the window."""

        if self.wraps_midnight:
            return minute >= self.start_minute or minute < self.end_minute
        return self.start_minute <= minute < self.end_minute

    def covers_day_type(self, day_type: DayType) -> bool:
        """Return ``True`` when the window applies to ``day_type``."""

        return not self.day_types or day_type in self.day_types

    def covers_season(self, season_code: str) -> bool:
        """Return ``True`` when the window applies in ``season_code``."""

        return not self.season_code or self.season_code == season_code

    def matches(self, minute: int, day_type: DayType, season_code: str) -> bool:
        """Return ``True`` when all three tests pass."""

        return (
            self.covers_minute(minute)
            and self.covers_day_type(day_type)
            and self.covers_season(season_code)
        )

    @property
    def specificity(self) -> tuple[int, int, int]:
        """Return an ordering key where lower means more specific."""

        return (
            self.length_minutes,
            len(self.day_types) if self.day_types else 9,
            0 if self.season_code else 1,
        )

    @property
    def boundaries(self) -> tuple[int, ...]:
        """Return the minute boundaries this window introduces."""

        return (self.start_minute, self.end_minute)

    def as_dict(self) -> dict[str, object]:
        """Return the document form the loader reads back."""

        return {
            "bucket": self.bucket,
            "start": format_clock(self.start_minute),
            "end": format_clock(self.end_minute),
            "day_types": [day.value for day in self.day_types],
            "season": self.season_code,
            "label": self.label,
        }

    def describe(self) -> str:
        """Return a one-line description for reports."""

        days = ", ".join(day.value for day in self.day_types) or "all days"
        season = self.season_code or "all year"
        return (
            f"{self.bucket}: {format_clock(self.start_minute)}"
            f"-{format_clock(self.end_minute)} ({days}, {season})"
        )


@dataclass(frozen=True, slots=True)
class WindowSet:
    """The windows of one tariff, plus the bucket used when none match."""

    windows: tuple[TimeWindow, ...] = ()
    default_bucket: str = "offpeak"
    precedence: WindowPrecedence | None = None
    """Overrides the profile's precedence when a tariff insists on its own."""

    @property
    def buckets(self) -> tuple[str, ...]:
        """Return the distinct bucket names, in declaration order."""

        seen: list[str] = []
        for window in self.windows:
            if window.bucket not in seen:
                seen.append(window.bucket)
        if self.default_bucket not in seen:
            seen.append(self.default_bucket)
        return tuple(seen)

    def boundaries(self) -> tuple[int, ...]:
        """Return every minute boundary any window introduces."""

        marks = {0, MINUTES_PER_DAY}
        for window in self.windows:
            marks.update(window.boundaries)
        return tuple(sorted(marks))

    def resolve(
        self,
        minute: int,
        day_type: DayType,
        season_code: str,
        precedence: WindowPrecedence,
    ) -> str:
        """Return the bucket a minute falls into under ``precedence``."""

        matches = [
            window
            for window in self.windows
            if window.matches(minute, day_type, season_code)
        ]
        if not matches:
            return self.default_bucket
        effective = self.precedence or precedence
        if effective is WindowPrecedence.FIRST_MATCH:
            return matches[0].bucket
        if effective is WindowPrecedence.LAST_MATCH:
            return matches[-1].bucket
        return min(matches, key=lambda window: window.specificity).bucket

    def as_dict(self) -> dict[str, object]:
        """Return the document form the loader reads back."""

        return {
            "windows": [window.as_dict() for window in self.windows],
            "default_bucket": self.default_bucket,
            "precedence": self.precedence.value if self.precedence else None,
        }

    def describe(self) -> str:
        """Return one line per window."""

        lines = [window.describe() for window in self.windows]
        lines.append(f"default: {self.default_bucket}")
        return "\n".join(lines)


def bucket_spans(
    span: Span,
    zone: Zone,
    windows: WindowSet,
    *,
    seasons: SeasonSet | None = None,
    holidays: HolidayCalendar | None = None,
    day_rules: DayTypeRules | None = None,
    precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC,
) -> dict[str, list[Span]]:
    """Split ``span`` into the buckets its windows assign.

    The walk advances in real time, re-deriving the local wall clock at each
    step, so a 25-hour autumn day contributes 25 hours of buckets and a
    23-hour spring day contributes 23.  Adjacent spans in the same bucket
    are merged, which keeps the result stable regardless of how many window
    boundaries happen to fall inside a run.
    """

    if span.is_empty:
        return {}
    marks = windows.boundaries()
    result: dict[str, list[Span]] = {}
    for day, day_span in span.local_days(zone):
        day_type = classify_day(day, holidays, day_rules)
        season_code = seasons.season_for(day) if seasons is not None else ""
        cursor = day_span.start
        while cursor < day_span.end:
            wall = zone.to_local(cursor)
            minute = wall.hour * 60 + wall.minute
            bucket = windows.resolve(minute, day_type, season_code, precedence)
            nxt_mark = next(mark for mark in marks if mark > minute)
            step = timedelta(minutes=nxt_mark - minute)
            end = min(cursor + step, day_span.end)
            if end <= cursor:  # pragma: no cover - defensive
                break
            result.setdefault(bucket, []).append(Span(cursor, end))
            cursor = end
    return {bucket: merge_spans(spans) for bucket, spans in sorted(result.items())}


def bucket_at(
    moment: datetime,
    zone: Zone,
    windows: WindowSet,
    *,
    seasons: SeasonSet | None = None,
    holidays: HolidayCalendar | None = None,
    day_rules: DayTypeRules | None = None,
    precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC,
) -> str:
    """Return the bucket a single instant falls into."""

    wall = zone.to_local(moment)
    day: date = wall.date()
    day_type = classify_day(day, holidays, day_rules)
    season_code = seasons.season_for(day) if seasons is not None else ""
    return windows.resolve(
        wall.hour * 60 + wall.minute, day_type, season_code, precedence
    )
