"""Marginal block-rate energy charges."""

from __future__ import annotations

from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...charge.scaling import tier_scale
from ...core.decimals import ZERO, D, is_zero
from ...core.quantity import Quantity
from ...core.units import Unit
from ...policy.conventions import TierBasis
from .base import Component, Stage
from .blocks import Block, allocate_blocks, validate_blocks

__all__ = ["TieredCharge"]


class TieredCharge(Component):
    """Prices a determinant across ascending blocks, marginally.

    One line item is produced per block that received any usage.  Empty
    blocks are omitted rather than shown at zero, which keeps a residential
    bill from listing four tiers the customer never reached — a presentation
    choice, but one that also means the line count depends on usage, so the
    tests assert on codes rather than positions.
    """

    kind = "tiered"

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
        """Return one line per block that received usage."""

        measured = context.quantity(self.determinant, self.unit)
        scale = tier_scale(context)
        allocations = allocate_blocks(measured.value, self.blocks, scale)
        quality = context.determinants.require(self.determinant).quality
        lines: list[LineItem] = []
        for index, (block, amount) in enumerate(zip(self.blocks, allocations)):
            if is_zero(amount) and not (index == 0 and measured.value < ZERO):
                continue
            name = block.display_name(index)
            builder = LineItemBuilder(
                f"{self.code}.{index + 1}",
                f"{self.label} — {name}",
                self.charge_class,
                self.code,
                self.side,
            )
            builder.measure(Quantity(amount, self.unit), "usage in block")
            builder.priced_at(block.rate, "block rate")
            builder.flag(quality)
            if block.limit is not None:
                builder.note(
                    "block limit",
                    f"{block.limit} x {scale}",
                    D(block.limit) * scale,
                )
            if context.profile.tier_basis is not TierBasis.CYCLE:
                builder.note(
                    "threshold basis",
                    context.profile.tier_basis.value,
                    f"{context.days} days",
                )
            builder.detail(block=index + 1, determinant=self.determinant)
            lines.append(builder.seal(context.money(amount * block.rate)))
        return lines

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

        head = f"{self.code}: {self.label} on {self.determinant}"
        body = "\n".join(f"    {block.describe()}" for block in self.blocks)
        return f"{head}\n{body}"
