"""Units of measure for metered quantities.

A billing determinant is never just a number.  "1,200" is a bill for
1,200 kWh, a demand charge on 1,200 kW or a water bill for 1,200 gallons,
and confusing the first two is a factor-of-720 error.  Every quantity in the
engine therefore carries its unit, and unit-crossing arithmetic raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import UnitMismatch
from .decimals import D

__all__ = ["Unit", "UnitKind", "conversion_factor", "convertible"]


class UnitKind(str, Enum):
    """The dimension a unit measures."""

    ENERGY = "energy"
    """Consumption over a period: kWh, therms, ccf."""

    POWER = "power"
    """Instantaneous or integrated rate: kW, kVA."""

    REACTIVE = "reactive"
    """Reactive energy and power, billed separately where power factor is."""

    VOLUME = "volume"
    """Water and gas volume before any heat-content conversion."""

    TIME = "time"
    """Days, months and hours, used by fixed and standing charges."""

    COUNT = "count"
    """Dimensionless counts: meters, service points, bills."""


@dataclass(frozen=True, slots=True)
class _UnitSpec:
    symbol: str
    kind: UnitKind
    factor: Decimal
    label: str


class Unit(str, Enum):
    """A unit of measure.

    Units within a :class:`UnitKind` convert by a fixed factor relative to
    the kind's base unit.  Crossing kinds is deliberately impossible: gas
    volume to energy needs a heating value that belongs to the meter, not to
    a lookup table, so that conversion lives in the meter data layer.
    """

    KWH = "kWh"
    MWH = "MWh"
    WH = "Wh"
    THERM = "therm"
    KW = "kW"
    MW = "MW"
    KVA = "kVA"
    KVARH = "kvarh"
    CCF = "ccf"
    MCF = "Mcf"
    GALLON = "gal"
    KGAL = "kgal"
    DAY = "day"
    MONTH = "month"
    HOUR = "hour"
    EACH = "each"

    @property
    def spec(self) -> _UnitSpec:
        """Return the static description of the unit."""

        return _SPECS[self]

    @property
    def kind(self) -> UnitKind:
        """Return the dimension the unit measures."""

        return self.spec.kind

    @property
    def label(self) -> str:
        """Return a human readable name for rendering."""

        return self.spec.label

    def __str__(self) -> str:
        return self.spec.symbol


_SPECS: dict[Unit, _UnitSpec] = {
    Unit.WH: _UnitSpec("Wh", UnitKind.ENERGY, D("0.001"), "watt-hours"),
    Unit.KWH: _UnitSpec("kWh", UnitKind.ENERGY, D("1"), "kilowatt-hours"),
    Unit.MWH: _UnitSpec("MWh", UnitKind.ENERGY, D("1000"), "megawatt-hours"),
    Unit.THERM: _UnitSpec("therm", UnitKind.ENERGY, D("29.3071"), "therms"),
    Unit.KW: _UnitSpec("kW", UnitKind.POWER, D("1"), "kilowatts"),
    Unit.MW: _UnitSpec("MW", UnitKind.POWER, D("1000"), "megawatts"),
    Unit.KVA: _UnitSpec("kVA", UnitKind.POWER, D("1"), "kilovolt-amperes"),
    Unit.KVARH: _UnitSpec("kvarh", UnitKind.REACTIVE, D("1"), "reactive kWh"),
    Unit.CCF: _UnitSpec("ccf", UnitKind.VOLUME, D("1"), "hundred cubic feet"),
    Unit.MCF: _UnitSpec("Mcf", UnitKind.VOLUME, D("10"), "thousand cubic feet"),
    Unit.GALLON: _UnitSpec("gal", UnitKind.VOLUME, D("0.13368"), "gallons"),
    Unit.KGAL: _UnitSpec("kgal", UnitKind.VOLUME, D("133.68"), "thousand gallons"),
    Unit.HOUR: _UnitSpec("hour", UnitKind.TIME, D("1"), "hours"),
    Unit.DAY: _UnitSpec("day", UnitKind.TIME, D("24"), "days"),
    Unit.MONTH: _UnitSpec("month", UnitKind.TIME, D("720"), "months"),
    Unit.EACH: _UnitSpec("each", UnitKind.COUNT, D("1"), "units"),
}


def convertible(left: Unit, right: Unit) -> bool:
    """Return ``True`` when the two units measure the same dimension.

    ``kVA`` and ``kW`` share :data:`UnitKind.POWER` but are not
    interchangeable without a power factor, so they are excluded explicitly.
    """

    if left is right:
        return True
    if left.kind is not right.kind:
        return False
    apparent = {Unit.KVA}
    return (left in apparent) == (right in apparent)


def conversion_factor(source: Unit, target: Unit) -> Decimal:
    """Return the multiplier taking a value in ``source`` to ``target``."""

    if source is target:
        return D(1)
    if not convertible(source, target):
        raise UnitMismatch(
            "these units do not measure the same thing",
            source=str(source),
            target=str(target),
        )
    return source.spec.factor / target.spec.factor
