"""Classifying a local date as a weekday, weekend or holiday."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .holidays import HolidayCalendar
from .rules import Weekday

__all__ = ["DayType", "DayTypeRules", "classify_day"]


class DayType(str, Enum):
    """The kind of day a tariff sees."""

    WEEKDAY = "weekday"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"

    @property
    def is_offpeak_by_default(self) -> bool:
        """Return ``True`` for the kinds most tariffs treat as off-peak."""

        return self in (DayType.WEEKEND, DayType.HOLIDAY)


@dataclass(frozen=True, slots=True)
class DayTypeRules:
    """The conventions governing how a date becomes a :class:`DayType`.

    Three genuine disagreements are captured:

    * whether Saturday counts as a weekend day at all (some commercial
      tariffs bill Saturday as a weekday and only exempt Sunday);
    * whether a holiday falling on a weekend adds anything, given the day is
      already off-peak;
    * whether a holiday keeps its own classification or collapses into the
      weekend bucket, which matters when a tariff prices the two apart.
    """

    saturday_is_weekend: bool = True
    sunday_is_weekend: bool = True
    holidays_are_distinct: bool = True
    holiday_wins_over_weekend: bool = True

    @property
    def weekend_days(self) -> tuple[Weekday, ...]:
        """Return the weekdays treated as weekend days."""

        days: list[Weekday] = []
        if self.saturday_is_weekend:
            days.append(Weekday.SATURDAY)
        if self.sunday_is_weekend:
            days.append(Weekday.SUNDAY)
        return tuple(days)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        weekend = ", ".join(day.label for day in self.weekend_days) or "none"
        holiday = "distinct" if self.holidays_are_distinct else "as weekend"
        return f"weekend: {weekend}; holidays: {holiday}"


def classify_day(
    day: date,
    calendar: HolidayCalendar | None = None,
    rules: DayTypeRules | None = None,
) -> DayType:
    """Return the :class:`DayType` of ``day`` under ``rules``."""

    active = rules or DayTypeRules()
    is_weekend = Weekday(day.weekday()) in active.weekend_days
    is_holiday = calendar is not None and calendar.is_holiday(day)
    if is_holiday:
        if is_weekend and not active.holiday_wins_over_weekend:
            return DayType.WEEKEND
        return DayType.HOLIDAY if active.holidays_are_distinct else DayType.WEEKEND
    return DayType.WEEKEND if is_weekend else DayType.WEEKDAY
