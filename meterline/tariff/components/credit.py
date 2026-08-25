"""Export credits for customer generation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...core.decimals import D, is_zero
from ...core.units import Unit
from ...policy.conventions import CreditValuation
from .base import Component, Stage

__all__ = ["ExportCredit"]


class ExportCredit(Component):
    """Credits energy the customer put back onto the grid.

    What an exported unit is worth is the single most contested number in
    distributed generation, and the three answers in
    :class:`~meterline.policy.conventions.CreditValuation` differ by a
    factor of three or more.  The component holds both rates — the retail
    reference and the avoided cost — so switching the convention does not
    require a different tariff.

    Banking is deliberately *not* handled here.  A credit that exceeds the
    bill has to be carried, expired or cashed out, and all three need state
    from outside this cycle; :mod:`meterline.rating.netting` owns that.
    """

    kind = "credit"

    def __init__(
        self,
        code: str,
        label: str,
        *,
        retail_rate: Decimal | str,
        avoided_cost_rate: Decimal | str = "0",
        determinant: str = "energy.exported",
        unit: Unit = Unit.KWH,
        side: ChargeSide = ChargeSide.SUPPLY,
        stage: int = Stage.CREDIT,
    ) -> None:
        super().__init__(code, label, ChargeClass.CREDIT, stage, side)
        self.retail_rate = D(retail_rate)
        self.avoided_cost_rate = D(avoided_cost_rate)
        self.determinant = determinant
        self.unit = unit

    def determinants(self) -> tuple[str, ...]:
        """Return the determinant this component reads."""

        return (self.determinant,)

    def effective_rate(self, context: RatingContext) -> Decimal:
        """Return the credit rate under the profile's valuation rule."""

        valuation = context.profile.credit_valuation
        if valuation is CreditValuation.AVOIDED_COST:
            return self.avoided_cost_rate
        if valuation is CreditValuation.PERCENT_OF_RETAIL:
            return self.retail_rate * context.profile.credit_fraction
        return self.retail_rate

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the credit line, or nothing when nothing was exported."""

        exported = context.optional_quantity(self.determinant, self.unit)
        if is_zero(exported.value):
            return []
        rate = self.effective_rate(context)
        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.CREDIT, self.code, self.side
        )
        builder.measure(exported, "exported energy")
        builder.note("valuation", context.profile.credit_valuation.value)
        builder.priced_at(rate, "credit rate")
        found = context.determinants.get(self.determinant)
        if found is not None:
            builder.flag(found.quality)
        builder.detail(
            determinant=self.determinant,
            valuation=context.profile.credit_valuation.value,
        )
        return [builder.seal(context.money(-(exported.value * rate)))]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "retail_rate": str(self.retail_rate),
                "avoided_cost_rate": str(self.avoided_cost_rate),
                "determinant": self.determinant,
                "unit": str(self.unit),
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{self.code}: {self.label}, retail {self.retail_rate} / "
            f"avoided {self.avoided_cost_rate} per {self.unit}"
        )
