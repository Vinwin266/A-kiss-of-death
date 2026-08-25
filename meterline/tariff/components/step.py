"""Stepped charges: the whole quantity at the band's rate."""

from __future__ import annotations

from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...charge.scaling import tier_scale
from ...core.quantity import Quantity
from ...core.units import Unit
from .base import Component, Stage
from .blocks import Block, block_for, scaled_limits, validate_blocks

__all__ = ["SteppedCharge"]


class SteppedCharge(Component):
    """Prices the whole determinant at the rate of the band it lands in.

    Stepped pricing has a cliff: one extra unit can raise the bill by more
    than that unit is worth.  Water utilities use it deliberately as a
    conservation signal, and the discontinuity is exactly what a customer
    disputes, so the line item records both the band and the distance to
    the next one.
    """

    kind = "stepped"

    def __init__(
        self,
        code: str,
        label: str,
        blocks: Sequence[Block],
        *,
        determinant: str = "energy.total",
        unit: Unit = Unit.KWH,
        side: ChargeSide = ChargeSide.SUPPLY,
        stage: int = Stage.ENERGY,
        charge_class: ChargeClass = ChargeClass.ENERGY,
    ) -> None:
        super().__init__(code, label, charge_class, stage, side)
        validate_blocks(blocks, component=code)
        self.blocks = tuple(blocks)
        self.determinant = determinant
        self.unit = unit

    def determinants(self) -> tuple[str, ...]:
        """Return the determinant this component reads."""

        return (self.determinant,)

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the single line for the band the usage falls in."""

        measured = context.quantity(self.determinant, self.unit)
        scale = tier_scale(context)
        index = block_for(measured.value, self.blocks, scale)
        block = self.blocks[index]
        limits = scaled_limits(self.blocks, scale)
        builder = LineItemBuilder(
            f"{self.code}.{index + 1}",
            f"{self.label} — {block.display_name(index)}",
            self.charge_class,
            self.code,
            self.side,
        )
        builder.measure(measured, "total usage")
        builder.priced_at(block.rate, "step rate")
        builder.flag(context.determinants.require(self.determinant).quality)
        if limits[index] is not None:
            headroom = limits[index] - measured.value
            builder.note("headroom to next step", f"{headroom} {self.unit}")
        builder.detail(step=index + 1, determinant=self.determinant)
        return [builder.seal(context.money(measured.value * block.rate))]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "determinant": self.determinant,
                "unit": str(self.unit),
                "blocks": [
                    {
                        "limit": None if block.is_open else str(block.limit),
                        "rate": str(block.rate),
                        "label": block.label,
                    }
                    for block in self.blocks
                ],
            }
        )
        return data

    def describe(self) -> str:
        """Return a multi-line description for reports."""

        head = f"{self.code}: {self.label} (stepped) on {self.determinant}"
        body = "\n".join(f"    {block.describe()}" for block in self.blocks)
        return f"{head}\n{body}"
