"""Peak demand and the ratchet.

Demand is a rate, not a total, so it depends on the window it is measured
over: the same day of interval data yields a different peak at 15 minutes,
30 minutes and one hour, and a rolling window can only ever find a peak at
least as high as a block window over the same data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from ..constants import RATCHET_LOOKBACK_MONTHS
from ..core.decimals import ZERO, D, safe_divide
from ..core.quantity import Quantity
from ..core.units import Unit
from ..errors import MeterDataError
from ..model.quality import QualityCode
from ..model.series import IntervalSeries
from ..policy.conventions import DemandMethod, RatchetBasis
from ..timeline.calendars import MonthKey
from ..timeline.spans import Span
from ..timeline.zones import Zone

__all__ = [
    "DemandPeak",
    "bucket_peaks",
    "effective_window",
    "peak_demand",
    "ratchet_floor",
]


@dataclass(frozen=True, slots=True)
class DemandPeak:
    """The highest demand found, and where it was."""

    value: Decimal
    span: Span | None
    quality: QualityCode = QualityCode.VALID
    method: DemandMethod = DemandMethod.BLOCK
    window_minutes: int = 15

    @property
    def quantity(self) -> Quantity:
        """Return the peak as a kilowatt quantity."""

        return Quantity(self.value, Unit.KW)

    @property
    def is_zero(self) -> bool:
        """Return ``True`` when no demand was found."""

        return self.value <= ZERO

    def describe(self) -> str:
        """Return a one-line description for reports."""

        where = self.span.describe() if self.span else "no interval"
        return f"{self.value} kW over {self.window_minutes}min at {where}"


def _energy_to_demand(energy: Decimal, minutes: int) -> Decimal:
    """Convert energy over a window into an average rate in kilowatts."""

    hours = safe_divide(D(minutes), D(60))
    return safe_divide(energy, hours)


def peak_demand(
    series: IntervalSeries,
    span: Span,
    *,
    method: DemandMethod = DemandMethod.BLOCK,
    window_minutes: int = 15,
) -> DemandPeak:
    """Return the highest demand in ``span`` under ``method``.

    ``BLOCK`` aligns non-overlapping windows to the start of the span,
    ``ROLLING`` slides one interval at a time, and ``HIGHEST_INTERVAL``
    ignores ``window_minutes`` entirely and reads the largest single
    interval — the cheapest to compute and the most sensitive to a spike.
    """

    if window_minutes % series.interval_minutes != 0:
        raise MeterDataError(
            "the demand window must be a whole number of intervals",
            window=window_minutes,
            interval=series.interval_minutes,
        )
    per_window = window_minutes // series.interval_minutes
    points = series.points_in(span)
    if not points:
        return DemandPeak(ZERO, None, QualityCode.MISSING, method, window_minutes)

    quality = max((point.quality for point in points), key=lambda code: code.rank)

    if method is DemandMethod.HIGHEST_INTERVAL:
        best = max(points, key=lambda point: point.amount)
        return DemandPeak(
            _energy_to_demand(best.amount, series.interval_minutes),
            best.span,
            quality,
            method,
            series.interval_minutes,
        )

    step = 1 if method is DemandMethod.ROLLING else per_window
    best_value = ZERO
    best_span: Span | None = None
    for start in range(0, max(len(points) - per_window + 1, 1), step):
        window = points[start : start + per_window]
        if len(window) < per_window:
            break
        total = sum((point.amount for point in window), ZERO)
        value = _energy_to_demand(total, window_minutes)
        if value > best_value:
            best_value = value
            best_span = Span(window[0].span.start, window[-1].span.end)
    if best_span is None:
        best_span = Span(points[0].span.start, points[-1].span.end)
    return DemandPeak(best_value, best_span, quality, method, window_minutes)


def bucket_peaks(
    series: IntervalSeries,
    bucket_windows: Mapping[str, Sequence[Span]],
    *,
    method: DemandMethod = DemandMethod.BLOCK,
    window_minutes: int = 15,
) -> dict[str, DemandPeak]:
    """Return the peak demand within each time-of-use bucket.

    A tariff that prices on-peak demand separately needs the peak *inside*
    the on-peak hours, which is not the same as the overall peak restricted
    to those hours when the demand window straddles a boundary.
    """

    peaks: dict[str, DemandPeak] = {}
    for bucket in sorted(bucket_windows):
        best: DemandPeak | None = None
        for piece in bucket_windows[bucket]:
            candidate = peak_demand(
                series, piece, method=method, window_minutes=window_minutes
            )
            if best is None or candidate.value > best.value:
                best = candidate
        if best is not None:
            peaks[bucket] = best
    return peaks


def ratchet_floor(
    history: Mapping[MonthKey, Decimal],
    month: MonthKey,
    *,
    basis: RatchetBasis = RatchetBasis.ANNUAL_PEAK,
    lookback_months: int = RATCHET_LOOKBACK_MONTHS,
    season_months: Sequence[int] = (),
    contract_kw: Decimal = ZERO,
) -> Decimal:
    """Return the demand a ratchet remembers, before the percentage.

    The lookback deliberately excludes the current month: a ratchet that
    included it would never bind, since this month's peak is always at
    least itself.
    """

    if basis is RatchetBasis.NONE:
        return ZERO
    if basis is RatchetBasis.CONTRACT:
        return contract_kw
    candidates: list[Decimal] = []
    for offset in range(1, lookback_months + 1):
        key = month.shift(-offset)
        value = history.get(key)
        if value is None:
            continue
        if basis is RatchetBasis.SEASON_PEAK and season_months:
            if key.month not in season_months:
                continue
        candidates.append(value)
    if not candidates:
        return ZERO
    return max(candidates)


def effective_window(series: IntervalSeries, requested: int) -> tuple[int, str]:
    """Return the demand window that can actually be measured, and why.

    A tariff may ask for a fifteen-minute demand window while the meter
    records hourly, and no amount of arithmetic recovers the quarter-hour
    peak from an hourly total.  Rather than refuse the bill or silently
    pretend, the window widens to the finest the data supports and the
    reason travels with the determinant.
    """

    width = series.interval_minutes
    if requested < width:
        return width, (
            f"the tariff asks for a {requested}-minute window but the meter "
            f"records {width}-minute intervals"
        )
    if requested % width:
        widened = ((requested // width) + 1) * width
        return widened, (
            f"a {requested}-minute window is not a whole number of "
            f"{width}-minute intervals; {widened} minutes was used"
        )
    return requested, ""
