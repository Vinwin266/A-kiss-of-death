"""Assistance discounts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.basis import Basis, basis_amount
from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...charge.scaling import proration_factor
from ...core.decimals import ZERO, D, is_zero
from ...core.money import Money
from .base import Component, Stage

__all__ = ["AssistanceDiscount"]


class AssistanceDiscount(Component):
    """Reduces the bill for an enrolled customer.

    Three details decide what the customer actually saves, and tariffs are
    routinely silent on all three: whether the discount is a percentage or a
    fixed amount, whether it is capped, and whether it lands before or after
    tax.  The stage is a policy convention because the same programme is
    applied differently by different billing systems in the same state.
    """

    kind = "discount"

    def __init__(
        self,
        code: str,
        label: str,
        *,
        percent: Decimal | str = "0",
        flat_amount: Decimal | str = "0",
        cap: Decimal | str = "0",
        basis: Basis = Basis.SUBTOTAL,
        prorate: bool = True,
        programme: str = "",
        side: ChargeSide = ChargeSide.OTHER,
        stage: int = Stage.DISCOUNT,
    ) -> None:
        super().__init__(code, label, ChargeClass.DISCOUNT, stage, side)
        self.percent = D(percent)
        self.flat_amount = D(flat_amount)
        self.cap = D(cap)
        self.basis = basis
        self.prorate = prorate
        self.programme = programme or code

    def applies_to(self, programme: str) -> bool:
        """Return ``True`` when an account's programme matches this discount."""

        return programme == self.programme

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the discount line, or nothing when it is worth nothing."""

        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.DISCOUNT, self.code, self.side
        )
        base = basis_amount(so_far, self.basis, context.currency)
        builder.note(f"basis: {self.basis.label}", "", base.format(6))
        amount = Money.zero(context.currency)
        if self.percent > ZERO:
            builder.priced_at(self.percent, "percent")
            amount = amount + base * (self.percent / D(100))
        if self.flat_amount > ZERO:
            factor = proration_factor(context) if self.prorate else D(1)
            builder.note("flat amount", str(self.flat_amount), self.flat_amount * factor)
            amount = amount + context.money(self.flat_amount * factor)
        if self.cap > ZERO and amount.amount > self.cap:
            builder.note("capped at", str(self.cap))
            amount = context.money(self.cap)
        if is_zero(amount.amount):
            return []
        builder.detail(
            programme=self.programme,
            stage=context.profile.assistance_stage.value,
            basis=self.basis.value,
        )
        return [builder.seal(-amount)]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "percent": str(self.percent),
                "flat_amount": str(self.flat_amount),
                "cap": str(self.cap),
                "basis": self.basis.value,
                "prorate": self.prorate,
                "programme": self.programme,
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        parts = []
        if self.percent > ZERO:
            parts.append(f"{self.percent}% of {self.basis.label}")
        if self.flat_amount > ZERO:
            parts.append(f"{self.flat_amount} flat")
        if self.cap > ZERO:
            parts.append(f"capped at {self.cap}")
        return f"{self.code}: {self.label}, " + ", ".join(parts)
