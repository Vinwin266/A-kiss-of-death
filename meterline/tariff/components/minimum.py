"""Minimum charges: lifting a small bill to a floor."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.basis import Basis, basis_amount
from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...charge.scaling import proration_factor
from ...core.decimals import D
from ...policy.conventions import MinimumBasis
from .base import Component, Stage

__all__ = ["MinimumCharge"]


_BASIS_FOR_POLICY = {
    MinimumBasis.ENERGY_ONLY: Basis.ENERGY,
    MinimumBasis.DELIVERY_ONLY: Basis.DELIVERY,
    MinimumBasis.ENERGY_AND_FIXED: Basis.BEFORE_CREDITS,
    MinimumBasis.ALL_BEFORE_TAX: Basis.SUBTOTAL,
}


class MinimumCharge(Component):
    """Adds the difference when the bill falls below a floor.

    Which subtotal the floor is compared against is a policy convention,
    not a property of the tariff, because the same rate sheet wording —
    "a minimum charge of $12.00 per month" — is implemented four different
    ways in the field.  The line item records which comparison was made.

    Whether the floor itself is prorated for a short period is a second,
    independent question, and this component follows the profile's
    proration convention for it.
    """

    kind = "minimum"

    def __init__(
        self,
        code: str,
        label: str,
        amount: Decimal | str,
        *,
        prorate: bool = True,
        side: ChargeSide = ChargeSide.DELIVERY,
        stage: int = Stage.MINIMUM,
        basis_override: Basis | None = None,
    ) -> None:
        super().__init__(code, label, ChargeClass.MINIMUM, stage, side)
        self.amount = D(amount)
        self.prorate = prorate
        self.basis_override = basis_override

    def basis_for(self, context: RatingContext) -> Basis:
        """Return the basis the floor is compared against."""

        if self.basis_override is not None:
            return self.basis_override
        return _BASIS_FOR_POLICY[context.profile.minimum_basis]

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the make-up line, or nothing when the floor is cleared."""

        basis = self.basis_for(context)
        current = basis_amount(so_far, basis, context.currency)
        floor = self.amount
        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.MINIMUM, self.code, self.side
        )
        if self.prorate:
            factor = proration_factor(context)
            floor = floor * factor
            builder.note("floor proration", context.profile.proration.value, factor)
        builder.note(f"basis: {basis.label}", "", current.format(6))
        builder.note("minimum", "", floor)
        shortfall = context.money(floor) - current
        if shortfall.amount <= D(0):
            context.notice(
                "tariff.minimum.not_applied",
                "the bill already exceeds the minimum charge",
                component=self.code,
                basis=basis.value,
            )
            return []
        builder.detail(basis=basis.value, floor=str(floor))
        return [builder.seal(shortfall)]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "amount": str(self.amount),
                "prorate": self.prorate,
                "basis_override": self.basis_override.value if self.basis_override else None,
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.code}: {self.label}, floor {self.amount}"
