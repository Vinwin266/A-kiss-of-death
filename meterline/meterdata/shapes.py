"""Load shapes: how usage is distributed within a period.

A shape is a set of relative weights, not absolute usage.  Estimating with
one is a two-step process — decide how much, then decide when — and keeping
the two apart means the same shape can be reused with any magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from ..core.decimals import ONE, ZERO, D, dsum, safe_divide
from ..errors import MeterDataError
from ..timeline.daytypes import DayType

__all__ = ["LoadShape", "FLAT_SHAPE", "RESIDENTIAL_SHAPE", "COMMERCIAL_SHAPE"]


@dataclass(frozen=True, slots=True)
class LoadShape:
    """Twenty-four hourly weights, optionally varying by day type."""

    code: str
    weekday: tuple[Decimal, ...]
    weekend: tuple[Decimal, ...] = ()
    holiday: tuple[Decimal, ...] = ()
    label: str = ""

    def __post_init__(self) -> None:
        for name, values in (
            ("weekday", self.weekday),
            ("weekend", self.weekend),
            ("holiday", self.holiday),
        ):
            if values and len(values) != 24:
                raise MeterDataError(
                    "a load shape needs one weight per hour",
                    shape=self.code,
                    profile=name,
                    found=len(values),
                )
        if not self.weekday:
            raise MeterDataError("a load shape needs a weekday profile", shape=self.code)

    @classmethod
    def of(
        cls,
        code: str,
        weekday: Sequence[str | int | Decimal],
        weekend: Sequence[str | int | Decimal] = (),
        holiday: Sequence[str | int | Decimal] = (),
        label: str = "",
    ) -> "LoadShape":
        """Build a shape from loosely typed weights."""

        return cls(
            code,
            tuple(D(value) for value in weekday),
            tuple(D(value) for value in weekend),
            tuple(D(value) for value in holiday),
            label,
        )

    def hours_for(self, day_type: DayType) -> tuple[Decimal, ...]:
        """Return the hourly weights for a day type, falling back sensibly."""

        if day_type is DayType.WEEKEND and self.weekend:
            return self.weekend
        if day_type is DayType.HOLIDAY:
            if self.holiday:
                return self.holiday
            if self.weekend:
                return self.weekend
        return self.weekday

    def day_weight(self, day_type: DayType) -> Decimal:
        """Return the total weight of one day of the given type."""

        return dsum(self.hours_for(day_type))

    def hour_share(self, day_type: DayType, hour: int) -> Decimal:
        """Return an hour's share of its day, as a fraction of one."""

        weights = self.hours_for(day_type)
        total = dsum(weights)
        if total <= ZERO:
            return safe_divide(ONE, D(24))
        return safe_divide(weights[hour % 24], total)

    def allocate(
        self, total: Decimal, days: Sequence[tuple[date, DayType]]
    ) -> list[Decimal]:
        """Split ``total`` across days in proportion to their weights."""

        if not days:
            return []
        weights = [self.day_weight(day_type) for _, day_type in days]
        grand = dsum(weights)
        if grand <= ZERO:
            share = safe_divide(total, D(len(days)))
            return [share for _ in days]
        return [safe_divide(total * weight, grand) for weight in weights]

    def describe(self) -> str:
        """Return a one-line description for reports."""

        variants = ["weekday"]
        if self.weekend:
            variants.append("weekend")
        if self.holiday:
            variants.append("holiday")
        return f"{self.code}: {', '.join(variants)}"


def _weights(values: Sequence[float | int | str]) -> tuple[Decimal, ...]:
    """Convert a list of literals into decimal weights."""

    return tuple(D(str(value)) for value in values)


FLAT_SHAPE = LoadShape(
    "flat",
    _weights([1] * 24),
    label="uniform across the day",
)

RESIDENTIAL_SHAPE = LoadShape(
    "residential",
    _weights(
        [
            "0.6", "0.5", "0.5", "0.5", "0.5", "0.7",
            "1.0", "1.3", "1.2", "1.0", "0.9", "0.9",
            "0.9", "0.9", "1.0", "1.1", "1.4", "1.8",
            "2.0", "1.9", "1.6", "1.3", "1.0", "0.7",
        ]
    ),
    _weights(
        [
            "0.7", "0.6", "0.5", "0.5", "0.5", "0.6",
            "0.8", "1.0", "1.2", "1.3", "1.3", "1.3",
            "1.2", "1.2", "1.2", "1.3", "1.5", "1.8",
            "1.9", "1.8", "1.5", "1.2", "1.0", "0.8",
        ]
    ),
    label="an evening-peaking household",
)

COMMERCIAL_SHAPE = LoadShape(
    "commercial",
    _weights(
        [
            "0.4", "0.4", "0.4", "0.4", "0.4", "0.5",
            "0.8", "1.4", "1.8", "2.0", "2.0", "2.0",
            "1.9", "2.0", "2.0", "1.9", "1.6", "1.1",
            "0.8", "0.6", "0.5", "0.4", "0.4", "0.4",
        ]
    ),
    _weights(["0.4"] * 24),
    label="an office on a weekday schedule",
)

SHAPES: dict[str, LoadShape] = {
    shape.code: shape
    for shape in (FLAT_SHAPE, RESIDENTIAL_SHAPE, COMMERCIAL_SHAPE)
}


def shape(code: str) -> LoadShape:
    """Return a built-in load shape by code."""

    try:
        return SHAPES[code]
    except KeyError:
        raise MeterDataError(
            "unknown load shape", code=code, known=", ".join(sorted(SHAPES))
        ) from None


def shape_mapping() -> Mapping[str, LoadShape]:
    """Return the built-in shapes as a read-only mapping."""

    return dict(SHAPES)
