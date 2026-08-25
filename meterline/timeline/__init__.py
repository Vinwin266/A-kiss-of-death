"""Time, zones, calendars and billing cycles.

Everything the engine knows about *when* lives here.  Two rules hold
throughout:

* an instant is always a timezone-aware UTC :class:`~datetime.datetime`;
* a wall-clock time is always a naive :class:`~datetime.datetime` plus an
  explicit :class:`~meterline.timeline.zones.Zone`.

Mixing the two is the bug that puts an hour of usage in the wrong
time-of-use bucket twice a year, so the type of a value says which it is.
"""

from __future__ import annotations

from .calendars import add_months, days_in_month, end_of_month, month_of
from .cycles import BillingCycle, CycleSchedule
from .daycount import DayCount, billing_days, days_between, year_fraction
from .daytypes import DayType, DayTypeRules, classify_day
from .holidays import Holiday, HolidayCalendar, ObservedRule
from .instants import EPOCH, format_instant, parse_instant, utc
from .spans import Span, merge_spans, subtract_spans
from .zones import UTC, Zone, ZoneRegistry, common_zone

__all__ = [
    "BillingCycle",
    "CycleSchedule",
    "DayCount",
    "DayType",
    "DayTypeRules",
    "EPOCH",
    "Holiday",
    "HolidayCalendar",
    "ObservedRule",
    "Span",
    "UTC",
    "Zone",
    "ZoneRegistry",
    "add_months",
    "billing_days",
    "classify_day",
    "common_zone",
    "days_between",
    "days_in_month",
    "end_of_month",
    "format_instant",
    "merge_spans",
    "month_of",
    "parse_instant",
    "subtract_spans",
    "utc",
    "year_fraction",
]
