"""Demand charges, including the ratchet."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...core.decimals import ZERO, D, is_zero
from ...core.quantity import Quantity
from ...core.rounding import round_to_increment
from ...core.units import Unit
from ...policy.conventions import RatchetBasis
from .base import Component, Stage

__all__ = ["DemandCharge"]


class DemandCharge(Component):
    """Prices a peak demand determinant, subject to a ratchet.

    A ratchet is the convention that makes demand billing contentious: the
    customer is billed on a percentage of a *past* peak whenever this
    period's peak is lower.  A plant that ran hot for one August afternoon
    then idled all winter pays for that afternoon eleven more times.

    The floor is supplied as a determinant so that computing it — which
    needs cross-cycle history — stays out of the tariff.  A tariff that
    declares a ratchet but is rated without the history determinant bills on
    the measured peak and says so.
    """

    kind = "demand"

    def __init__(
        self,
        code: str,
        label: str,
        rate: Decimal | str,
        *,
        determinant: str = "demand.peak",
        floor_determinant: str = "demand.ratchet_floor",
        unit: Unit = Unit.KW,
        side: ChargeSide = ChargeSide.DELIVERY,
        stage: int = Stage.DEMAND,
        minimum_billed: Decimal | str = "0",
    ) -> None:
        super().__init__(code, label, ChargeClass.DEMAND, stage, side)
        self.rate = D(rate)
        self.determinant = determinant
        self.floor_determinant = floor_determinant
        self.unit = unit
        self.minimum_billed = D(minimum_billed)
        """A contractual floor applied even when no ratchet is configured."""

    def determinants(self) -> tuple[str, ...]:
        """Return the determinants this component reads."""

        return (self.determinant, self.floor_determinant)

    def _billed_quantity(
        self, context: RatingContext, builder: LineItemBuilder
    ) -> Quantity:
        """Return the demand actually billed, recording why."""

        measured = context.optional_quantity(self.determinant, self.unit)
        builder.measure(measured, "measured peak")
        billed = measured.value
        ratchet = context.profile.ratchet
        if ratchet is not RatchetBasis.NONE:
            floor = context.optional_quantity(self.floor_determinant, self.unit)
            if context.has(self.floor_determinant):
                scaled = floor.value * context.profile.ratchet_fraction
                builder.note(
                    "ratchet floor",
                    f"{floor.value} x {context.profile.ratchet_percent}%",
                    scaled,
                )
                if scaled > billed:
                    builder.note("ratchet applied", ratchet.value, scaled)
                    billed = scaled
            else:
                context.notice(
                    "tariff.demand.no_ratchet_history",
                    "the tariff declares a ratchet but no history was available",
                    component=self.code,
                )
        if self.minimum_billed > billed:
            builder.note("contract minimum", str(self.minimum_billed))
            billed = self.minimum_billed
        increment = D(context.profile.demand_increment)
        if not is_zero(increment):
            snapped = round_to_increment(billed, increment, context.profile.rounding_mode)
            builder.note("snapped to increment", str(increment), snapped)
            billed = snapped
        return Quantity(billed, self.unit)

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the demand line, or nothing when there is no demand."""

        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.DEMAND, self.code, self.side
        )
        billed = self._billed_quantity(context, builder)
        if is_zero(billed.value) or billed.value < ZERO:
            return []
        builder.priced_at(self.rate, "rate per kW")
        found = context.determinants.get(self.determinant)
        if found is not None:
            builder.flag(found.quality)
        builder.detail(determinant=self.determinant, method=context.profile.demand_method.value)
        return [builder.seal(context.money(billed.value * self.rate))]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "rate": str(self.rate),
                "determinant": self.determinant,
                "floor_determinant": self.floor_determinant,
                "unit": str(self.unit),
                "minimum_billed": str(self.minimum_billed),
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.code}: {self.label}, {self.rate} per {self.unit} on {self.determinant}"
