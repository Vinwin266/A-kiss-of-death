"""Rolling interval and register data up into billing buckets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from ..core.decimals import ZERO, D, safe_divide
from ..core.quantity import Quantity
from ..core.units import Unit
from ..model.series import IntervalSeries
from ..policy.conventions import WindowPrecedence
from ..tariff.seasons import SeasonSet
from ..tariff.windows import WindowSet, bucket_spans
from ..timeline.daytypes import DayTypeRules
from ..timeline.holidays import HolidayCalendar
from ..timeline.spans import Span
from ..timeline.zones import Zone
from .consumption import Consumption

__all__ = [
    "daily_totals",
    "bucket_totals",
    "bucket_totals_from_consumption",
    "monthly_totals",
]


def daily_totals(
    series: IntervalSeries, zone: Zone, span: Span | None = None
) -> dict[date, Quantity]:
    """Return the total per local calendar day.

    Days are the zone's actual days, so the 25-hour day in autumn gets its
    extra hour of usage rather than losing it to the day after.
    """

    bounds = span or series.span
    totals: dict[date, Quantity] = {}
    for day, day_span in bounds.local_days(zone):
        totals[day] = series.total_in(day_span)
    return totals


def monthly_totals(
    series: IntervalSeries, zone: Zone, span: Span | None = None
) -> dict[str, Quantity]:
    """Return the total per calendar month, keyed by ``YYYY-MM``."""

    totals: dict[str, Quantity] = {}
    for day, quantity in sorted(daily_totals(series, zone, span).items()):
        key = f"{day.year:04d}-{day.month:02d}"
        current = totals.get(key, Quantity.zero(quantity.unit))
        totals[key] = current + quantity
    return totals


def bucket_totals(
    series: IntervalSeries,
    span: Span,
    zone: Zone,
    windows: WindowSet,
    *,
    seasons: SeasonSet | None = None,
    holidays: HolidayCalendar | None = None,
    day_rules: DayTypeRules | None = None,
    precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC,
) -> dict[str, Quantity]:
    """Return the total per time-of-use bucket from interval data.

    This is the accurate path: every interval is placed in the bucket its
    own timestamp falls in.  Where a bucket boundary cuts an interval in
    half, the interval's energy is split in proportion to time, which is the
    only assumption available without finer data.
    """

    result: dict[str, Quantity] = {}
    spans = bucket_spans(
        span,
        zone,
        windows,
        seasons=seasons,
        holidays=holidays,
        day_rules=day_rules,
        precedence=precedence,
    )
    for bucket in sorted(spans):
        total = Quantity.zero(series.unit)
        for piece in spans[bucket]:
            total = total + series.total_in(piece)
        result[bucket] = total
    return result


def bucket_totals_from_consumption(
    records: Sequence[Consumption],
    span: Span,
    zone: Zone,
    windows: WindowSet,
    unit: Unit,
    *,
    seasons: SeasonSet | None = None,
    holidays: HolidayCalendar | None = None,
    day_rules: DayTypeRules | None = None,
    precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC,
) -> dict[str, Quantity]:
    """Return per-bucket totals from register reads alone.

    Without interval data the only thing known about a month's usage is its
    total, so it is split between buckets in proportion to the *hours* each
    bucket occupies.  That systematically under-states peak usage for a
    customer who peaks in the evening, which is precisely why tariffs with
    real time-of-use rates require an interval meter.  The engine will do it
    anyway if asked, and says so.
    """

    spans = bucket_spans(
        span,
        zone,
        windows,
        seasons=seasons,
        holidays=holidays,
        day_rules=day_rules,
        precedence=precedence,
    )
    hours: dict[str, Decimal] = {}
    for bucket in sorted(spans):
        hours[bucket] = sum((piece.hours for piece in spans[bucket]), ZERO)
    total_hours = sum(hours.values(), ZERO)
    total_usage = ZERO
    for record in records:
        total_usage += record.quantity.to(unit).value
    result: dict[str, Quantity] = {}
    for bucket in sorted(hours):
        share = safe_divide(hours[bucket], total_hours)
        result[bucket] = Quantity(total_usage * share, unit)
    return result


def bucket_hours(
    span: Span,
    zone: Zone,
    windows: WindowSet,
    *,
    seasons: SeasonSet | None = None,
    holidays: HolidayCalendar | None = None,
    day_rules: DayTypeRules | None = None,
    precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC,
) -> Mapping[str, Decimal]:
    """Return how many hours each bucket occupies in a span."""

    spans = bucket_spans(
        span,
        zone,
        windows,
        seasons=seasons,
        holidays=holidays,
        day_rules=day_rules,
        precedence=precedence,
    )
    return {
        bucket: sum((piece.hours for piece in pieces), ZERO)
        for bucket, pieces in sorted(spans.items())
    }


def apportion(total: Quantity, weights: Mapping[str, Decimal]) -> dict[str, Quantity]:
    """Split a total across named weights, preserving the sum."""

    grand = sum(weights.values(), ZERO)
    if grand <= ZERO:
        return {key: Quantity.zero(total.unit) for key in sorted(weights)}
    allocated: dict[str, Quantity] = {}
    running = ZERO
    keys = sorted(weights)
    for key in keys[:-1]:
        share = safe_divide(total.value * weights[key], grand)
        allocated[key] = Quantity(share, total.unit)
        running += share
    allocated[keys[-1]] = Quantity(total.value - running, total.unit)
    return allocated
