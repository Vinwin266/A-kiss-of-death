"""Day-count conventions.

"How many days were in this bill?" has at least four defensible answers for
the same pair of read dates, and the difference lands directly on any charge
quoted per day.  The conventions are named here and chosen by policy.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..constants import BILLING_DAYS_NOMINAL
from ..core.decimals import D, safe_divide
from ..errors import TimelineError
from .calendars import days_in_month
from .spans import Span

__all__ = ["DayCount", "days_between", "billing_days", "year_fraction"]


class DayCount(str, Enum):
    """How the days between two dates are counted."""

    ACTUAL = "actual"
    """Calendar days, half-open: 1 June to 1 July is 30 days."""

    ACTUAL_INCLUSIVE = "actual_inclusive"
    """Calendar days counting both endpoints: the same pair is 31 days.

    Common on paper rate sheets, where "service from the 1st to the 1st" is
    read as covering both dates.  Charging a standing charge on 31 days of a
    30-day month is exactly the sort of penny that reconciliation teams
    spend an afternoon on.
    """

    THIRTY_360 = "thirty_360"
    """Every month is 30 days and every year 360; the accountant's calendar."""

    NOMINAL_30 = "nominal_30"
    """Always 30 days regardless of the dates, for levelised charges."""

    @property
    def label(self) -> str:
        """Return a readable description."""

        return _LABELS[self]


_LABELS = {
    DayCount.ACTUAL: "actual days, half-open",
    DayCount.ACTUAL_INCLUSIVE: "actual days, both endpoints counted",
    DayCount.THIRTY_360: "30/360",
    DayCount.NOMINAL_30: "nominal 30-day month",
}


def _thirty_360(start: date, end: date) -> int:
    """Return the 30/360 day count between two dates (US convention)."""

    start_day = min(start.day, 30)
    end_day = end.day
    if start_day == 30 and end_day == 31:
        end_day = 30
    return (
        (end.year - start.year) * 360
        + (end.month - start.month) * 30
        + (end_day - start_day)
    )


def days_between(start: date, end: date, convention: DayCount = DayCount.ACTUAL) -> int:
    """Return the day count between two local dates under ``convention``."""

    if end < start:
        raise TimelineError(
            "end date precedes start date",
            start=start.isoformat(),
            end=end.isoformat(),
        )
    if convention is DayCount.NOMINAL_30:
        return BILLING_DAYS_NOMINAL
    if convention is DayCount.THIRTY_360:
        return _thirty_360(start, end)
    plain = (end - start).days
    if convention is DayCount.ACTUAL_INCLUSIVE:
        return plain + 1
    return plain


def billing_days(span: Span, zone, convention: DayCount = DayCount.ACTUAL) -> int:  # noqa: ANN001
    """Return the billable day count of a span in a local zone.

    The span is measured by the local dates it touches rather than by its
    duration in hours, so a 25-hour autumn day still counts as one day.
    """

    if span.is_empty:
        return 0
    start_day = zone.local_date(span.start)
    end_day = zone.local_date(span.end - timedelta(microseconds=1))
    if convention is DayCount.ACTUAL:
        return (end_day - start_day).days + 1
    return days_between(start_day, end_day + timedelta(days=1), convention)


def year_fraction(
    start: date, end: date, convention: DayCount = DayCount.ACTUAL
) -> Decimal:
    """Return the fraction of a year between two dates."""

    if convention is DayCount.THIRTY_360:
        return safe_divide(D(days_between(start, end, convention)), D(360))
    days = D(days_between(start, end, convention))
    basis = D(366) if _spans_leap_day(start, end) else D(365)
    return safe_divide(days, basis)


def _spans_leap_day(start: date, end: date) -> bool:
    """Return ``True`` when 29 February falls in the half-open range."""

    for year in range(start.year, end.year + 1):
        if days_in_month(year, 2) == 29:
            leap = date(year, 2, 29)
            if start <= leap < end:
                return True
    return False


def day_fraction(span: Span, zone, convention: DayCount = DayCount.ACTUAL) -> Decimal:  # noqa: ANN001
    """Return the span's length as a fraction of a nominal 30-day month."""

    return safe_divide(D(billing_days(span, zone, convention)), D(BILLING_DAYS_NOMINAL))
