"""Calendar-date arithmetic on local dates."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

from ..errors import TimelineError

__all__ = [
    "MonthKey",
    "add_days",
    "add_months",
    "date_range",
    "days_in_month",
    "end_of_month",
    "iter_months",
    "month_of",
    "start_of_month",
]


@dataclass(frozen=True, order=True, slots=True)
class MonthKey:
    """A year and month, orderable and hashable.

    Ratchets, net-metering banks and budget-billing all bucket by calendar
    month; a dedicated key keeps those buckets from being stringly typed.
    """

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise TimelineError("month out of range", month=self.month)

    @classmethod
    def of(cls, day: date) -> "MonthKey":
        """Return the month containing ``day``."""

        return cls(day.year, day.month)

    @classmethod
    def parse(cls, text: str) -> "MonthKey":
        """Parse ``"2025-06"``."""

        parts = text.strip().split("-")
        if len(parts) != 2:
            raise TimelineError("month keys look like 2025-06", value=text)
        try:
            return cls(int(parts[0]), int(parts[1]))
        except ValueError:
            raise TimelineError("month keys look like 2025-06", value=text) from None

    def shift(self, months: int) -> "MonthKey":
        """Return the month ``months`` later (or earlier when negative)."""

        index = self.year * 12 + (self.month - 1) + months
        return MonthKey(index // 12, index % 12 + 1)

    def start(self) -> date:
        """Return the first calendar day of the month."""

        return date(self.year, self.month, 1)

    def end(self) -> date:
        """Return the last calendar day of the month."""

        return date(self.year, self.month, days_in_month(self.year, self.month))

    def contains(self, day: date) -> bool:
        """Return ``True`` when ``day`` falls in this month."""

        return day.year == self.year and day.month == self.month

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given month."""

    return calendar.monthrange(year, month)[1]


def start_of_month(day: date) -> date:
    """Return the first day of ``day``'s month."""

    return day.replace(day=1)


def end_of_month(day: date) -> date:
    """Return the last day of ``day``'s month."""

    return day.replace(day=days_in_month(day.year, day.month))


def month_of(day: date) -> MonthKey:
    """Return the :class:`MonthKey` containing ``day``."""

    return MonthKey.of(day)


def add_days(day: date, days: int) -> date:
    """Return ``day`` shifted by ``days``."""

    return day + timedelta(days=days)


def add_months(day: date, months: int, *, clamp: bool = True) -> date:
    """Return ``day`` shifted by whole months.

    The 31st of a month has no counterpart in February.  ``clamp=True``
    moves it to the last day of the target month, which is what read-cycle
    schedules and anniversary billing both expect; ``clamp=False`` raises so
    a caller that cannot tolerate the ambiguity finds out.
    """

    target = MonthKey(day.year, day.month).shift(months)
    last = days_in_month(target.year, target.month)
    if day.day > last:
        if not clamp:
            raise TimelineError(
                "day does not exist in the target month",
                day=day.isoformat(),
                months=months,
            )
        return date(target.year, target.month, last)
    return date(target.year, target.month, day.day)


def date_range(start: date, end: date, *, inclusive: bool = False) -> Iterator[date]:
    """Yield the dates from ``start`` to ``end``.

    The range is half-open by default, matching every other span in the
    engine; ``inclusive=True`` is offered because rate sheets are usually
    written the other way and translating at the boundary is where the
    off-by-one lives.
    """

    if end < start:
        raise TimelineError(
            "range ends before it starts", start=start.isoformat(), end=end.isoformat()
        )
    cursor = start
    limit = end + timedelta(days=1) if inclusive else end
    while cursor < limit:
        yield cursor
        cursor += timedelta(days=1)


def iter_months(start: MonthKey, count: int) -> Iterator[MonthKey]:
    """Yield ``count`` consecutive months beginning at ``start``."""

    if count < 0:
        raise TimelineError("month count cannot be negative", count=count)
    for offset in range(count):
        yield start.shift(offset)
