"""Power-factor and reactive-energy charges."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...core.decimals import ONE, ZERO, D, is_zero, safe_divide
from ...core.quantity import Quantity
from ...core.units import Unit
from .base import Component, Stage

__all__ = ["PowerFactorCharge"]


class PowerFactorCharge(Component):
    """Charges for reactive energy, or penalises a poor power factor.

    Two shapes are in circulation and this component supports both:

    * a flat rate per kvarh above an allowance expressed as a fraction of
      real energy;
    * a penalty that scales billed demand up by the ratio of a target power
      factor to the achieved one.

    The second is the older form and is still what most industrial tariffs
    say, which is why the achieved factor is derived here rather than being
    expected as a determinant.
    """

    kind = "reactive"

    def __init__(
        self,
        code: str,
        label: str,
        rate: Decimal | str,
        *,
        allowance_fraction: Decimal | str = "0.3",
        target_power_factor: Decimal | str = "0.95",
        mode: str = "kvarh",
        reactive_determinant: str = "reactive.total",
        energy_determinant: str = "energy.total",
        side: ChargeSide = ChargeSide.DELIVERY,
        stage: int = Stage.REACTIVE,
    ) -> None:
        super().__init__(code, label, ChargeClass.REACTIVE, stage, side)
        self.rate = D(rate)
        self.allowance_fraction = D(allowance_fraction)
        self.target_power_factor = D(target_power_factor)
        self.mode = mode
        self.reactive_determinant = reactive_determinant
        self.energy_determinant = energy_determinant

    def determinants(self) -> tuple[str, ...]:
        """Return the determinants this component reads."""

        return (self.reactive_determinant, self.energy_determinant)

    def power_factor(self, real: Decimal, reactive: Decimal) -> Decimal:
        """Return the achieved power factor from real and reactive energy."""

        apparent_squared = real * real + reactive * reactive
        if apparent_squared <= ZERO:
            return ONE
        apparent = apparent_squared.sqrt()
        return safe_divide(real, apparent, default=ONE)

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the reactive charge, or nothing when none is due."""

        reactive = context.optional_quantity(self.reactive_determinant, Unit.KVARH)
        real = context.optional_quantity(self.energy_determinant, Unit.KWH)
        if is_zero(reactive.value):
            return []
        builder = LineItemBuilder(
            self.code, self.label, ChargeClass.REACTIVE, self.code, self.side
        )
        builder.measure(reactive, "reactive energy")
        if self.mode == "power_factor":
            achieved = self.power_factor(real.value, reactive.value)
            builder.note("achieved power factor", "", achieved)
            builder.note("target power factor", "", self.target_power_factor)
            if achieved >= self.target_power_factor:
                return []
            shortfall = self.target_power_factor - achieved
            builder.priced_at(self.rate, "penalty per point")
            amount = context.money(shortfall * D(100) * self.rate)
            return [builder.seal(amount)]
        allowance = real.value * self.allowance_fraction
        builder.note("allowance", f"{self.allowance_fraction} x real energy", allowance)
        billable = reactive.value - allowance
        if billable <= ZERO:
            return []
        builder.measure(Quantity(billable, Unit.KVARH), "chargeable reactive energy")
        builder.priced_at(self.rate, "rate per kvarh")
        return [builder.seal(context.money(billable * self.rate))]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "rate": str(self.rate),
                "mode": self.mode,
                "allowance_fraction": str(self.allowance_fraction),
                "target_power_factor": str(self.target_power_factor),
                "reactive_determinant": self.reactive_determinant,
                "energy_determinant": self.energy_determinant,
            }
        )
        return data

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.code}: {self.label} ({self.mode}) at {self.rate}"
