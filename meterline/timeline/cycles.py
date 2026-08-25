"""Billing cycles and the schedules that produce them.

A cycle is the span a bill covers.  Where its edges sit is a convention with
real money attached: a cycle that ends at local midnight on the scheduled
read date and one that ends at the moment the meter was actually read
differ by up to a day of standing charge and, on a time-of-use tariff, by
whichever hours fall in the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterator

from ..core.ids import stable_id
from ..errors import TimelineError
from .calendars import MonthKey, add_months, days_in_month
from .daycount import DayCount, billing_days
from .holidays import HolidayCalendar
from .rules import Weekday
from .spans import Span
from .zones import Zone

__all__ = ["CycleKind", "ReadDayShift", "BillingCycle", "CycleSchedule"]


class CycleKind(str, Enum):
    """Why a cycle has the length it has."""

    REGULAR = "regular"
    """A scheduled cycle of ordinary length."""

    INITIAL = "initial"
    """The first cycle after a move-in; usually short."""

    FINAL = "final"
    """The cycle ending at a move-out; usually short."""

    REBILL = "rebill"
    """A cycle regenerated to correct an earlier bill."""

    OFF_CYCLE = "off_cycle"
    """A cycle produced by an unscheduled read, e.g. a customer request."""


class ReadDayShift(str, Enum):
    """What to do when a scheduled read date is not a working day."""

    NONE = "none"
    """Read on the scheduled date regardless."""

    FORWARD = "forward"
    """Move to the next working day, lengthening the cycle."""

    BACKWARD = "backward"
    """Move to the previous working day, shortening the cycle."""

    NEAREST = "nearest"
    """Move to whichever working day is closer, ties going backward."""


@dataclass(frozen=True, slots=True)
class BillingCycle:
    """One billable period for one service point."""

    cycle_id: str
    service_point_id: str
    span: Span
    scheduled_read: date
    kind: CycleKind = CycleKind.REGULAR
    sequence: int = 0
    route: str = ""

    @classmethod
    def build(
        cls,
        service_point_id: str,
        span: Span,
        scheduled_read: date,
        kind: CycleKind = CycleKind.REGULAR,
        sequence: int = 0,
        route: str = "",
    ) -> "BillingCycle":
        """Build a cycle with a deterministic identifier."""

        cycle_id = stable_id(
            "cyc",
            service_point_id,
            span.start.isoformat(),
            span.end.isoformat(),
            kind.value,
        )
        return cls(cycle_id, service_point_id, span, scheduled_read, kind, sequence, route)

    def days(self, zone: Zone, convention: DayCount = DayCount.ACTUAL) -> int:
        """Return the cycle length in billable days."""

        return billing_days(self.span, zone, convention)

    def contains(self, moment) -> bool:  # noqa: ANN001
        """Return ``True`` when an instant falls inside the cycle."""

        return self.span.contains(moment)

    def month(self, zone: Zone) -> MonthKey:
        """Return the calendar month a cycle is attributed to.

        The convention here is "the month containing the cycle's end", which
        is what ratchets and annual true-ups assume.  Attributing by start
        instead shifts a whole year's ratchet history by one month.
        """

        return MonthKey.of(zone.local_date(self.span.end - timedelta(microseconds=1)))

    def describe(self, zone: Zone) -> str:
        """Return a one-line description in local dates."""

        start = zone.local_date(self.span.start)
        end = zone.local_date(self.span.end - timedelta(microseconds=1))
        return f"{start.isoformat()} to {end.isoformat()} ({self.kind.value})"


@dataclass(frozen=True, slots=True)
class CycleSchedule:
    """Generates the cycles of a meter-reading route."""

    route: str
    read_day: int
    zone: Zone
    shift: ReadDayShift = ReadDayShift.NONE
    holidays: HolidayCalendar | None = None
    working_days: tuple[Weekday, ...] = (
        Weekday.MONDAY,
        Weekday.TUESDAY,
        Weekday.WEDNESDAY,
        Weekday.THURSDAY,
        Weekday.FRIDAY,
    )
    minimum_days: int = 26
    maximum_days: int = 35

    def __post_init__(self) -> None:
        if not 1 <= self.read_day <= 31:
            raise TimelineError("read day out of range", day=self.read_day)
        if self.minimum_days > self.maximum_days:
            raise TimelineError(
                "minimum cycle length exceeds the maximum",
                minimum=self.minimum_days,
                maximum=self.maximum_days,
            )

    # -- read dates -----------------------------------------------------

    def is_working_day(self, day: date) -> bool:
        """Return ``True`` when the route reads meters on ``day``."""

        if Weekday(day.weekday()) not in self.working_days:
            return False
        if self.holidays is not None and self.holidays.is_holiday(day):
            return False
        return True

    def scheduled_read_for(self, month: MonthKey) -> date:
        """Return the read date in ``month`` after applying the shift rule."""

        nominal = date(
            month.year,
            month.month,
            min(self.read_day, days_in_month(month.year, month.month)),
        )
        return self.apply_shift(nominal)

    def apply_shift(self, day: date) -> date:
        """Move ``day`` onto a working day under the configured rule."""

        if self.shift is ReadDayShift.NONE or self.is_working_day(day):
            return day
        if self.shift is ReadDayShift.FORWARD:
            return self._search(day, 1)
        if self.shift is ReadDayShift.BACKWARD:
            return self._search(day, -1)
        backward = self._search(day, -1)
        forward = self._search(day, 1)
        return backward if (day - backward) <= (forward - day) else forward

    def _search(self, day: date, step: int) -> date:
        """Walk day by day in ``step`` until a working day is found."""

        cursor = day
        for _ in range(14):
            cursor = cursor + timedelta(days=step)
            if self.is_working_day(cursor):
                return cursor
        raise TimelineError(
            "no working day found near the scheduled read",
            route=self.route,
            near=day.isoformat(),
        )

    # -- cycles ---------------------------------------------------------

    def boundary(self, read_day: date) -> "object":
        """Return the UTC instant a cycle ending on ``read_day`` closes.

        Cycles close at local midnight *after* the read date, so the read
        date itself is billed.
        """

        return self.zone.day_start(read_day + timedelta(days=1))

    def cycles(
        self, service_point_id: str, first_month: MonthKey, count: int
    ) -> list[BillingCycle]:
        """Return ``count`` consecutive cycles for a service point."""

        if count <= 0:
            return []
        cycles: list[BillingCycle] = []
        previous_read = self.scheduled_read_for(first_month.shift(-1))
        for index in range(count):
            month = first_month.shift(index)
            read = self.scheduled_read_for(month)
            span = Span(self.boundary(previous_read), self.boundary(read))
            cycles.append(
                BillingCycle.build(
                    service_point_id,
                    span,
                    read,
                    CycleKind.REGULAR,
                    sequence=index,
                    route=self.route,
                )
            )
            previous_read = read
        return cycles

    def iter_cycles(
        self, service_point_id: str, first_month: MonthKey
    ) -> Iterator[BillingCycle]:
        """Yield cycles indefinitely, for callers that stop on a condition."""

        month = first_month
        previous_read = self.scheduled_read_for(first_month.shift(-1))
        index = 0
        while True:
            read = self.scheduled_read_for(month)
            span = Span(self.boundary(previous_read), self.boundary(read))
            yield BillingCycle.build(
                service_point_id,
                span,
                read,
                CycleKind.REGULAR,
                sequence=index,
                route=self.route,
            )
            previous_read = read
            month = month.shift(1)
            index += 1

    def is_within_tolerance(self, cycle: BillingCycle) -> bool:
        """Return ``True`` when a cycle's length is inside the route bounds."""

        length = cycle.days(self.zone)
        return self.minimum_days <= length <= self.maximum_days

    def next_read_after(self, day: date) -> date:
        """Return the first scheduled read date strictly after ``day``."""

        month = MonthKey.of(day)
        for offset in range(0, 3):
            candidate = self.scheduled_read_for(month.shift(offset))
            if candidate > day:
                return candidate
        return self.scheduled_read_for(MonthKey.of(add_months(day, 3)))
