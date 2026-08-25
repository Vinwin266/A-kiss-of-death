"""Bases: the subtotals a percentage charge can be assessed on.

Riders, minimum charges, discounts and taxes all say "a percentage of ..."
and mean different things by it.  Naming the bases and computing them in one
place is what stops a rider from accidentally taxing a credit.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Sequence

from ..core.money import Money, total_of
from .classes import ChargeClass, ChargeSide
from .lineitem import LineItem

__all__ = ["Basis", "basis_amount", "basis_includes", "subtotal_by_class"]


class Basis(str, Enum):
    """A named subtotal of the lines produced so far."""

    ENERGY = "energy"
    """Volumetric energy charges only."""

    DEMAND = "demand"
    """Demand charges only."""

    FIXED = "fixed"
    """Standing charges only."""

    DELIVERY = "delivery"
    """Every charge on the delivery side."""

    SUPPLY = "supply"
    """Every charge on the supply side."""

    VOLUMETRIC = "volumetric"
    """Energy, demand and reactive charges together."""

    BEFORE_CREDITS = "before_credits"
    """Everything except export credits and discounts."""

    SUBTOTAL = "subtotal"
    """Everything except taxes; the usual tax base."""

    TOTAL = "total"
    """Everything, taxes included; used by sequential tax compounding."""

    @property
    def label(self) -> str:
        """Return a readable name."""

        return self.value.replace("_", " ")


_CLASS_SETS: dict[Basis, frozenset[ChargeClass]] = {
    Basis.ENERGY: frozenset({ChargeClass.ENERGY}),
    Basis.DEMAND: frozenset({ChargeClass.DEMAND}),
    Basis.FIXED: frozenset({ChargeClass.FIXED}),
    Basis.VOLUMETRIC: frozenset(
        {ChargeClass.ENERGY, ChargeClass.DEMAND, ChargeClass.REACTIVE}
    ),
    Basis.BEFORE_CREDITS: frozenset(
        {
            ChargeClass.FIXED,
            ChargeClass.ENERGY,
            ChargeClass.DEMAND,
            ChargeClass.REACTIVE,
            ChargeClass.RIDER,
            ChargeClass.MINIMUM,
        }
    ),
    Basis.SUBTOTAL: frozenset(
        {
            ChargeClass.FIXED,
            ChargeClass.ENERGY,
            ChargeClass.DEMAND,
            ChargeClass.REACTIVE,
            ChargeClass.RIDER,
            ChargeClass.CREDIT,
            ChargeClass.MINIMUM,
            ChargeClass.DISCOUNT,
            ChargeClass.ADJUSTMENT,
        }
    ),
    Basis.TOTAL: frozenset(ChargeClass),
}


def basis_includes(basis: Basis, line: LineItem) -> bool:
    """Return ``True`` when ``line`` contributes to ``basis``."""

    if basis is Basis.DELIVERY:
        return line.side is ChargeSide.DELIVERY
    if basis is Basis.SUPPLY:
        return line.side is ChargeSide.SUPPLY
    return line.charge_class in _CLASS_SETS[basis]


def basis_amount(lines: Iterable[LineItem], basis: Basis, currency: str) -> Money:
    """Return the subtotal of ``lines`` for ``basis``."""

    return total_of(
        (line.amount for line in lines if basis_includes(basis, line)), currency
    )


def subtotal_by_class(
    lines: Sequence[LineItem], currency: str
) -> dict[ChargeClass, Money]:
    """Return the subtotal of each charge class present."""

    totals: dict[ChargeClass, Money] = {}
    for line in lines:
        current = totals.get(line.charge_class, Money.zero(currency))
        totals[line.charge_class] = current + line.amount
    return totals
