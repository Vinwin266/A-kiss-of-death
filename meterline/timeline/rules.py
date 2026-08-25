"""Calendar rules that resolve to a date within a given year.

Both daylight-saving transitions and public holidays are described the same
way: "the second Sunday in March", "25 December", "the last Monday in May".
One rule type serves both, which keeps the two subsystems from drifting
apart on, say, what "the last week" means.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from enum import Enum

from ..errors import TimelineError

__all__ = ["Weekday", "DateRule", "FixedDate", "NthWeekday", "LastWeekday"]


class Weekday(int, Enum):
    """Days of the week, matching :meth:`datetime.date.weekday` numbering."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @property
    def label(self) -> str:
        """Return the capitalised English name."""

        return self.name.capitalize()

    @property
    def is_weekend(self) -> bool:
        """Return ``True`` for Saturday and Sunday.

        Note that whether a *tariff* treats the weekend as off-peak is a
        separate question answered in :mod:`meterline.timeline.daytypes`.
        """

        return self in (Weekday.SATURDAY, Weekday.SUNDAY)


class DateRule:
    """Base class for anything that resolves to a date in a given year."""

    def resolve(self, year: int) -> date:  # pragma: no cover - interface
        """Return the date this rule picks out in ``year``."""

        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - interface
        """Return a short human description of the rule."""

        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class FixedDate(DateRule):
    """A fixed month and day, such as 4 July."""

    month: int
    day: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise TimelineError("month out of range", month=self.month)
        if not 1 <= self.day <= 31:
            raise TimelineError("day out of range", day=self.day)

    def resolve(self, year: int) -> date:
        """Return the date, clamping 29 February in a common year."""

        last = calendar.monthrange(year, self.month)[1]
        return date(year, self.month, min(self.day, last))

    def describe(self) -> str:
        return f"{calendar.month_name[self.month]} {self.day}"


@dataclass(frozen=True, slots=True)
class NthWeekday(DateRule):
    """The nth occurrence of a weekday in a month, counting from the start."""

    month: int
    weekday: Weekday
    occurrence: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise TimelineError("month out of range", month=self.month)
        if not 1 <= self.occurrence <= 5:
            raise TimelineError("occurrence out of range", n=self.occurrence)

    def resolve(self, year: int) -> date:
        """Return the date, clamping a fifth occurrence to the last one."""

        first = date(year, self.month, 1)
        shift = (int(self.weekday) - first.weekday()) % 7
        day = 1 + shift + (self.occurrence - 1) * 7
        last = calendar.monthrange(year, self.month)[1]
        while day > last:
            day -= 7
        return date(year, self.month, day)

    def describe(self) -> str:
        ordinals = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
        which = ordinals[self.occurrence]
        return f"the {which} {self.weekday.label} in {calendar.month_name[self.month]}"


@dataclass(frozen=True, slots=True)
class LastWeekday(DateRule):
    """The last occurrence of a weekday in a month."""

    month: int
    weekday: Weekday

    def resolve(self, year: int) -> date:
        """Return the last such weekday in the month."""

        last = calendar.monthrange(year, self.month)[1]
        candidate = date(year, self.month, last)
        shift = (candidate.weekday() - int(self.weekday)) % 7
        return date(year, self.month, last - shift)

    def describe(self) -> str:
        return f"the last {self.weekday.label} in {calendar.month_name[self.month]}"
