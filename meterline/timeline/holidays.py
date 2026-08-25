"""Holiday calendars and observed-day conventions.

Time-of-use tariffs almost always treat holidays as off-peak, and almost
always disagree about which holidays and about what happens when one falls
on a weekend.  Both halves are data here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Iterable

from .rules import DateRule, FixedDate, LastWeekday, NthWeekday, Weekday

__all__ = ["ObservedRule", "Holiday", "HolidayCalendar", "us_federal_calendar"]


class ObservedRule(str, Enum):
    """What happens when a holiday falls on a weekend."""

    NONE = "none"
    """The holiday is observed on its actual date, weekend or not."""

    NEAREST_WEEKDAY = "nearest_weekday"
    """Saturday moves to Friday, Sunday to Monday; the US federal rule."""

    FOLLOWING_MONDAY = "following_monday"
    """Both Saturday and Sunday move forward to the Monday."""

    BOTH = "both"
    """Both the actual date and the observed date count as holidays."""


@dataclass(frozen=True, slots=True)
class Holiday:
    """A named holiday and the rule that places it in a year."""

    name: str
    rule: DateRule
    observed: ObservedRule = ObservedRule.NEAREST_WEEKDAY

    def dates_in(self, year: int) -> tuple[date, ...]:
        """Return every date this holiday occupies in ``year``."""

        actual = self.rule.resolve(year)
        shifted = _observe(actual, self.observed)
        if self.observed is ObservedRule.BOTH:
            return tuple(sorted({actual, shifted}))
        return (shifted,)

    def describe(self) -> str:
        """Return a one-line description."""

        return f"{self.name}: {self.rule.describe()} ({self.observed.value})"


def _observe(day: date, rule: ObservedRule) -> date:
    """Apply an observed-day rule to a single date."""

    weekday = day.weekday()
    if rule is ObservedRule.NONE:
        return day
    if weekday == Weekday.SATURDAY:
        if rule is ObservedRule.FOLLOWING_MONDAY:
            return day + timedelta(days=2)
        return day - timedelta(days=1)
    if weekday == Weekday.SUNDAY:
        return day + timedelta(days=1)
    return day


@dataclass(slots=True)
class HolidayCalendar:
    """A named set of holidays, resolved lazily per year and cached."""

    name: str
    holidays: tuple[Holiday, ...] = ()
    _cache: dict[int, dict[date, str]] = field(default_factory=dict, repr=False)

    def add(self, holiday: Holiday) -> None:
        """Add a holiday, discarding any cached resolutions."""

        self.holidays = self.holidays + (holiday,)
        self._cache.clear()

    def extend(self, holidays: Iterable[Holiday]) -> None:
        """Add several holidays."""

        for holiday in holidays:
            self.add(holiday)

    def in_year(self, year: int) -> dict[date, str]:
        """Return a mapping of date to holiday name for ``year``."""

        cached = self._cache.get(year)
        if cached is not None:
            return cached
        resolved: dict[date, str] = {}
        for holiday in self.holidays:
            for day in holiday.dates_in(year):
                resolved.setdefault(day, holiday.name)
        self._cache[year] = resolved
        return resolved

    def is_holiday(self, day: date) -> bool:
        """Return ``True`` when ``day`` is observed as a holiday."""

        return day in self.in_year(day.year)

    def name_of(self, day: date) -> str:
        """Return the holiday name for ``day``, or an empty string."""

        return self.in_year(day.year).get(day, "")

    def between(self, start: date, end: date) -> list[tuple[date, str]]:
        """Return the observed holidays in the half-open range."""

        found: list[tuple[date, str]] = []
        for year in range(start.year, end.year + 1):
            for day, label in sorted(self.in_year(year).items()):
                if start <= day < end:
                    found.append((day, label))
        return found

    def count_between(self, start: date, end: date) -> int:
        """Return how many observed holidays fall in the half-open range."""

        return len(self.between(start, end))


def us_federal_calendar(
    observed: ObservedRule = ObservedRule.NEAREST_WEEKDAY,
) -> HolidayCalendar:
    """Return the six holidays most US electric tariffs recognise.

    Deliberately not the full federal list: rate schedules typically name a
    shorter set, and inventing holidays a tariff does not recognise moves
    peak hours to off-peak without anyone asking for it.
    """

    return HolidayCalendar(
        "us-tariff",
        (
            Holiday("New Year's Day", FixedDate(1, 1), observed),
            Holiday("Memorial Day", LastWeekday(5, Weekday.MONDAY), ObservedRule.NONE),
            Holiday("Independence Day", FixedDate(7, 4), observed),
            Holiday(
                "Labor Day", NthWeekday(9, Weekday.MONDAY, 1), ObservedRule.NONE
            ),
            Holiday(
                "Thanksgiving", NthWeekday(11, Weekday.THURSDAY, 4), ObservedRule.NONE
            ),
            Holiday("Christmas Day", FixedDate(12, 25), observed),
        ),
    )
