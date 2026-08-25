"""Interval data series.

An interval series is a fixed-width, contiguous run of values starting at a
known instant.  Storing it as a start plus a list rather than as (timestamp,
value) pairs is deliberate: it makes a gap impossible to represent by
accident, so a hole in the data has to be an explicit ``None`` and cannot be
a row that quietly failed to arrive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterator, Sequence

from ..core.decimals import ZERO, D
from ..core.quantity import Quantity
from ..core.units import Unit
from ..errors import MeterDataError
from ..timeline.instants import ensure_utc, format_instant
from ..timeline.spans import Span
from .quality import QualityCode

__all__ = ["SeriesPoint", "IntervalSeries"]


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One interval: its span, its value and how much it is trusted."""

    span: Span
    value: Decimal | None
    quality: QualityCode = QualityCode.VALID

    @property
    def is_missing(self) -> bool:
        """Return ``True`` when the interval carries no value."""

        return self.value is None

    @property
    def amount(self) -> Decimal:
        """Return the value, treating a hole as zero.

        Callers that must distinguish "no usage" from "no data" read
        :attr:`is_missing` first; this accessor exists for the aggregations
        where the distinction has already been resolved by policy.
        """

        return ZERO if self.value is None else self.value

    def describe(self) -> str:
        """Return a one-line description for reports."""

        value = "missing" if self.is_missing else str(self.value)
        return f"{format_instant(self.span.start)} {value} ({self.quality.value})"


@dataclass(frozen=True, slots=True)
class IntervalSeries:
    """A contiguous run of equal-width intervals for one channel."""

    channel_id: str
    start: datetime
    interval_minutes: int
    values: tuple[Decimal | None, ...]
    unit: Unit = Unit.KWH
    qualities: tuple[QualityCode, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", ensure_utc(self.start, what="series start"))
        if self.interval_minutes <= 0:
            raise MeterDataError(
                "interval width must be positive",
                channel=self.channel_id,
                minutes=self.interval_minutes,
            )
        object.__setattr__(
            self,
            "values",
            tuple(None if value is None else D(value) for value in self.values),
        )
        if not self.qualities:
            object.__setattr__(
                self,
                "qualities",
                tuple(
                    QualityCode.MISSING if value is None else QualityCode.VALID
                    for value in self.values
                ),
            )
        elif len(self.qualities) != len(self.values):
            raise MeterDataError(
                "quality codes do not match the number of intervals",
                channel=self.channel_id,
                values=len(self.values),
                qualities=len(self.qualities),
            )

    # -- geometry -------------------------------------------------------

    @property
    def width(self) -> timedelta:
        """Return the width of one interval."""

        return timedelta(minutes=self.interval_minutes)

    @property
    def end(self) -> datetime:
        """Return the instant after the last interval."""

        return self.start + self.width * len(self.values)

    @property
    def span(self) -> Span:
        """Return the span the series covers."""

        return Span(self.start, self.end)

    def interval_span(self, index: int) -> Span:
        """Return the span of the interval at ``index``."""

        begin = self.start + self.width * index
        return Span(begin, begin + self.width)

    def index_at(self, moment: datetime) -> int | None:
        """Return the index containing ``moment``, or ``None`` when outside."""

        normalised = ensure_utc(moment)
        if not self.span.contains(normalised):
            return None
        elapsed = (normalised - self.start).total_seconds()
        return int(elapsed // (self.interval_minutes * 60))

    # -- values ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self.values)

    def __iter__(self) -> Iterator[SeriesPoint]:
        for index, value in enumerate(self.values):
            yield SeriesPoint(self.interval_span(index), value, self.qualities[index])

    def points(self) -> list[SeriesPoint]:
        """Return every interval as a :class:`SeriesPoint`."""

        return list(self)

    def index_range(self, span: Span) -> tuple[int, int]:
        """Return the half-open index range overlapping ``span``.

        Computed arithmetically rather than by scanning.  A cycle's worth of
        hourly data is a few thousand intervals and the aggregations ask for
        overlapping windows dozens of times per bill; scanning each time
        turns a linear job into a quadratic one.
        """

        if not self.values:
            return (0, 0)
        width = self.interval_minutes * 60
        start_offset = (span.start - self.start).total_seconds()
        end_offset = (span.end - self.start).total_seconds()
        if end_offset <= 0 or start_offset >= width * len(self.values):
            return (0, 0)
        begin = max(0, int(start_offset // width))
        end = min(len(self.values), -(-int(end_offset) // width))
        return (begin, max(begin, end))

    def points_in(self, span: Span) -> list[SeriesPoint]:
        """Return the intervals whose spans overlap ``span``."""

        begin, end = self.index_range(span)
        return [
            SeriesPoint(self.interval_span(index), self.values[index], self.qualities[index])
            for index in range(begin, end)
        ]

    @property
    def missing_count(self) -> int:
        """Return how many intervals carry no value."""

        return sum(1 for value in self.values if value is None)

    @property
    def has_gaps(self) -> bool:
        """Return ``True`` when any interval is missing."""

        return self.missing_count > 0

    def total(self) -> Quantity:
        """Return the sum of the present values."""

        total = ZERO
        for value in self.values:
            if value is not None:
                total += value
        return Quantity(total, self.unit)

    def total_in(self, span: Span) -> Quantity:
        """Return the sum over ``span``, apportioning partial intervals.

        An interval half inside the span contributes half its value.  That
        is the only defensible reading for energy, which is a total over the
        interval rather than a sample at its start.
        """

        total = ZERO
        for point in self.points_in(span):
            if point.value is None:
                continue
            overlap = point.span.intersection(span)
            if overlap is None:
                continue
            if overlap.duration == point.span.duration:
                total += point.value
            else:
                share = D(overlap.seconds) / D(point.span.seconds)
                total += point.value * share
        return Quantity(total, self.unit)

    def with_values(
        self,
        values: Sequence[Decimal | None],
        qualities: Sequence[QualityCode] | None = None,
    ) -> "IntervalSeries":
        """Return a copy carrying different values."""

        return IntervalSeries(
            self.channel_id,
            self.start,
            self.interval_minutes,
            tuple(values),
            self.unit,
            tuple(qualities) if qualities is not None else (),
        )

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{self.channel_id}: {len(self.values)} x {self.interval_minutes}min "
            f"from {format_instant(self.start)} ({self.missing_count} missing)"
        )
