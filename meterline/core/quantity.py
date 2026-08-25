"""A number with a unit attached."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from ..constants import WORKING_SCALE
from ..errors import UnitMismatch
from .decimals import ZERO, D, is_zero, scale_to
from .rounding import RoundingMode, quantize
from .units import Unit, conversion_factor

__all__ = ["Quantity", "quantity", "sum_quantities"]


@dataclass(frozen=True, slots=True)
class Quantity:
    """An exact amount of a metered thing."""

    value: Decimal
    unit: Unit

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", D(self.value))
        object.__setattr__(self, "unit", Unit(self.unit))

    @classmethod
    def zero(cls, unit: Unit) -> "Quantity":
        """Return a zero quantity in ``unit``."""

        return cls(ZERO, unit)

    # -- arithmetic -----------------------------------------------------

    def _aligned(self, other: "Quantity") -> Decimal:
        if self.unit is other.unit:
            return other.value
        if other.unit.kind is not self.unit.kind:
            raise UnitMismatch(
                "cannot combine quantities of different kinds",
                left=str(self.unit),
                right=str(other.unit),
            )
        return other.to(self.unit).value

    def __add__(self, other: "Quantity") -> "Quantity":
        return Quantity(self.value + self._aligned(other), self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        return Quantity(self.value - self._aligned(other), self.unit)

    def __mul__(self, factor: Decimal | int | str) -> "Quantity":
        return Quantity(self.value * D(factor), self.unit)

    __rmul__ = __mul__

    def __truediv__(self, divisor: Decimal | int | str) -> "Quantity":
        return Quantity(scale_to(self.value / D(divisor)), self.unit)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value, self.unit)

    def __abs__(self) -> "Quantity":
        return Quantity(abs(self.value), self.unit)

    # -- comparison -----------------------------------------------------

    def __lt__(self, other: "Quantity") -> bool:
        return self.value < self._aligned(other)

    def __le__(self, other: "Quantity") -> bool:
        return self.value <= self._aligned(other)

    def __gt__(self, other: "Quantity") -> bool:
        return self.value > self._aligned(other)

    def __ge__(self, other: "Quantity") -> bool:
        return self.value >= self._aligned(other)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.unit.kind is not self.unit.kind:
            return False
        return self.value == self._aligned(other)

    def __hash__(self) -> int:
        return hash((self.unit.kind, self.value, self.unit))

    # -- inspection -----------------------------------------------------

    @property
    def is_zero(self) -> bool:
        """Return ``True`` when the value is zero within tolerance."""

        return is_zero(self.value)

    @property
    def is_negative(self) -> bool:
        """Return ``True`` for a negative quantity, e.g. exported energy."""

        return self.value < ZERO

    def to(self, unit: Unit) -> "Quantity":
        """Convert to ``unit`` within the same dimension."""

        if unit is self.unit:
            return self
        factor = conversion_factor(self.unit, unit)
        return Quantity(scale_to(self.value * factor, WORKING_SCALE), unit)

    def positive_part(self) -> "Quantity":
        """Return the quantity clipped at zero from below.

        Net metering needs the import and export halves of a signed net
        value separately; clipping is how both are taken from one series.
        """

        return self if self.value > ZERO else Quantity.zero(self.unit)

    def negative_part(self) -> "Quantity":
        """Return the magnitude of the negative part, as a positive value."""

        return Quantity(-self.value, self.unit) if self.value < ZERO else Quantity.zero(
            self.unit
        )

    def quantized(
        self, places: int = 3, mode: RoundingMode = RoundingMode.HALF_UP
    ) -> "Quantity":
        """Return a copy rounded for presentation."""

        return Quantity(quantize(self.value, places, mode), self.unit)

    def format(self, places: int = 3) -> str:
        """Render as ``"1234.000 kWh"``."""

        return f"{quantize(self.value, places, RoundingMode.HALF_UP):.{places}f} {self.unit}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Quantity({self.value!s}, {self.unit!r})"


def quantity(value: Any, unit: Unit) -> Quantity:
    """Convenience constructor: ``quantity("120.5", Unit.KWH)``."""

    if isinstance(value, Quantity):
        return value.to(unit)
    return Quantity(D(value), unit)


def sum_quantities(items: Iterable[Quantity], unit: Unit) -> Quantity:
    """Sum quantities into ``unit``, tolerating an empty iterable."""

    total = Quantity.zero(unit)
    for item in items:
        total = total + item
    return total
