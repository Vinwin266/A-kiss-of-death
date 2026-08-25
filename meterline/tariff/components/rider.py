"""Riders: surcharges expressed per unit or as a percentage of a basis."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Sequence

from ...charge.basis import Basis, basis_amount
from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...core.decimals import D, is_zero
from ...core.units import Unit
from ...errors import TariffError
from .base import Component, Stage

__all__ = ["RiderKind", "Rider"]


class RiderKind(str, Enum):
    """How a rider's amount is arrived at."""

    PER_UNIT = "per_unit"
    """A rate applied to a metered determinant."""

    PERCENT = "percent"
    """A percentage of a named basis of the charges so far."""

    FLAT = "flat"
    """A fixed amount, prorated like a standing charge."""


class Rider(Component):
    """A surcharge added on top of the base rates.

    Riders are where the ordering convention shows up most clearly: a
    percentage rider assessed on :data:`Basis.SUBTOTAL` sees export credits
    and therefore shrinks when the customer generates, while the same rider
    on :data:`Basis.BEFORE_CREDITS` does not.  Both are written as "a
    percentage of the bill" on the rate sheet.
    """

    kind = "rider"

    def __init__(
        self,
        code: str,
        label: str,
        rate: Decimal | str,
        *,
        rider_kind: RiderKind = RiderKind.PER_UNIT,
        determinant: str = "energy.total",
        unit: Unit = Unit.KWH,
        basis: Basis = Basis.BEFORE_CREDITS,
        side: ChargeSide = ChargeSide.DELIVERY,
        stage: int = Stage.RIDER,
        taxable: bool = True,
    ) -> None:
        super().__init__(code, label, ChargeClass.RIDER, stage, side)
        self.rate = D(rate)
        self.rider_kind = rider_kind
        self.determinant = determinant
        self.unit = unit
        self.basis = basis
        self.taxable = taxable
        if rider_kind is RiderKind.PERCENT and basis is Basis.TOTAL:
            raise TariffError(
                "a rider cannot be a percentage of the total it is part of",
                component=code,
            )

    def determinants(self) -> tuple[str, ...]:
        """Return the determinant this component reads, if any."""

        return (self.determinant,) if self.rider_kind is RiderKind.PER_UNIT else ()

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the rider line, or nothing when it comes to zero."""

        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.RIDER, self.code, self.side
        )
        if not self.taxable:
            builder.exempt()
        if self.rider_kind is RiderKind.PER_UNIT:
            measured = context.optional_quantity(self.determinant, self.unit)
            builder.measure(measured, "billed usage")
            builder.priced_at(self.rate, "rider rate")
            amount = context.money(measured.value * self.rate)
        elif self.rider_kind is RiderKind.PERCENT:
            base = basis_amount(so_far, self.basis, context.currency)
            builder.note(f"basis: {self.basis.label}", "", base.format(6))
            builder.priced_at(self.rate, "percent")
            amount = base * (self.rate / D(100))
        else:
            from ...charge.scaling import proration_factor

            factor = proration_factor(context)
            builder.note("proration", context.profile.proration.value, factor)
            amount = context.money(self.rate * factor)
        if is_zero(amount.amount):
            return []
        builder.detail(kind=self.rider_kind.value, basis=self.basis.value)
        return [builder.seal(amount)]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "rate": str(self.rate),
                "rider_kind": self.rider_kind.value,
                "determinant": self.determinant,
                "unit": str(self.unit),
                "basis": self.basis.value,
                "taxable": self.taxable,
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        if self.rider_kind is RiderKind.PERCENT:
            return f"{self.code}: {self.label}, {self.rate}% of {self.basis.label}"
        if self.rider_kind is RiderKind.FLAT:
            return f"{self.code}: {self.label}, flat {self.rate}"
        return f"{self.code}: {self.label}, {self.rate} per {self.unit}"
