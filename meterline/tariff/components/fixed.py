"""Standing charges: the part of the bill that does not move with usage."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...charge.scaling import describe_proration, proration_factor
from ...core.decimals import D
from ...core.quantity import Quantity
from ...core.units import Unit
from ...errors import TariffError
from .base import Component, Stage

__all__ = ["FixedCharge"]


class FixedCharge(Component):
    """A charge quoted per month or per day.

    The per-day form is unambiguous.  The per-month form is where the
    proration convention bites: 27 days of a 31-day month is 0.871 of a
    month under actual-days proration, 0.900 under nominal-30, and a whole
    month under the "any day earns the month" convention still in force at
    a surprising number of cooperatives.
    """

    kind = "fixed"

    def __init__(
        self,
        code: str,
        label: str,
        amount: Decimal | str,
        *,
        per: str = "month",
        side: ChargeSide = ChargeSide.DELIVERY,
        stage: int = Stage.FIXED,
        taxable: bool = True,
    ) -> None:
        super().__init__(code, label, ChargeClass.FIXED, stage, side)
        if per not in ("month", "day", "bill"):
            raise TariffError(
                "a fixed charge is quoted per month, per day or per bill",
                component=code,
                per=per,
            )
        self.amount = D(amount)
        self.per = per
        self.taxable = taxable

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the standing charge for the period."""

        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.FIXED, self.code, self.side
        )
        if not self.taxable:
            builder.exempt()
        if self.per == "day":
            days = context.served_days
            builder.measure(Quantity(D(days), Unit.DAY), "days served")
            builder.priced_at(self.amount, "rate per day")
            amount = context.money(self.amount * D(days))
        elif self.per == "bill":
            builder.note("basis", "once per bill")
            builder.priced_at(self.amount, "rate per bill")
            amount = context.money(self.amount)
        else:
            factor = proration_factor(context)
            builder.priced_at(self.amount, "rate per month")
            builder.note("proration", describe_proration(context), factor)
            builder.measure(Quantity(D(context.served_days), Unit.DAY), "days served")
            amount = context.money(self.amount * factor)
        builder.detail(per=self.per, days=context.served_days)
        return [builder.seal(amount)]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update({"amount": str(self.amount), "per": self.per, "taxable": self.taxable})
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.code}: {self.label}, {self.amount} per {self.per}"
