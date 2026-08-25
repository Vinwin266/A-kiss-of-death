"""Blocks: the thresholds a volumetric charge is split by.

A block list is priced two incompatible ways and both are called "tiered"
in the trade:

* *marginal* — each block prices only the usage inside it, the way income
  tax works;
* *stepped* — the whole usage is priced at the rate of the block it lands
  in, so crossing a threshold raises the price of every unit.

:class:`~meterline.tariff.components.tiered.TieredCharge` does the first and
:class:`~meterline.tariff.components.step.SteppedCharge` the second.  They
share these block definitions so a tariff can be switched between them
without rewriting the thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from ...core.decimals import ZERO, D
from ...errors import TariffError

__all__ = ["Block", "allocate_blocks", "validate_blocks", "scaled_limits"]


@dataclass(frozen=True, slots=True)
class Block:
    """One band of a block-rate schedule."""

    limit: Decimal | None
    """Upper bound of the block, or ``None`` for the final open block."""

    rate: Decimal
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", D(self.rate))
        if self.limit is not None:
            object.__setattr__(self, "limit", D(self.limit))
            if self.limit <= ZERO:
                raise TariffError("block limits must be positive", limit=str(self.limit))

    @classmethod
    def of(
        cls, limit: Decimal | str | int | None, rate: Decimal | str, label: str = ""
    ) -> "Block":
        """Build a block from loosely typed values."""

        return cls(None if limit is None else D(limit), D(rate), label)

    @property
    def is_open(self) -> bool:
        """Return ``True`` when the block has no upper bound."""

        return self.limit is None

    def display_name(self, index: int) -> str:
        """Return the label, falling back to a positional name."""

        return self.label or f"block {index + 1}"

    def describe(self) -> str:
        """Return a one-line description for reports."""

        bound = "and above" if self.is_open else f"up to {self.limit}"
        return f"{bound} at {self.rate}"


def validate_blocks(blocks: Sequence[Block], *, component: str = "") -> None:
    """Check that block limits ascend and that only the last is open."""

    if not blocks:
        raise TariffError("a block schedule needs at least one block", component=component)
    previous: Decimal | None = None
    for index, block in enumerate(blocks):
        if block.is_open and index != len(blocks) - 1:
            raise TariffError(
                "only the final block may be open-ended",
                component=component,
                position=index,
            )
        if block.limit is not None:
            if previous is not None and block.limit <= previous:
                raise TariffError(
                    "block limits must strictly ascend",
                    component=component,
                    position=index,
                    limit=str(block.limit),
                )
            previous = block.limit
    if not blocks[-1].is_open and blocks[-1].limit is not None:
        # A closed final block silently drops usage above it; that is
        # occasionally intended, but never by accident.
        raise TariffError(
            "the final block must be open-ended, or usage above it is unpriced",
            component=component,
        )


def scaled_limits(blocks: Sequence[Block], scale: Decimal) -> list[Decimal | None]:
    """Return the block limits multiplied by a threshold scale."""

    return [None if block.is_open else D(block.limit) * scale for block in blocks]


def allocate_blocks(
    quantity: Decimal, blocks: Sequence[Block], scale: Decimal = D(1)
) -> list[Decimal]:
    """Split ``quantity`` across ``blocks`` marginally.

    Returns one amount per block; they sum to ``quantity`` for a
    non-negative input.  A negative quantity — which happens on a net
    channel — is placed entirely in the first block, because splitting a
    credit across ascending blocks would price exported energy at the
    highest tier.
    """

    amounts = [ZERO for _ in blocks]
    if quantity <= ZERO:
        if blocks:
            amounts[0] = quantity
        return amounts
    limits = scaled_limits(blocks, scale)
    remaining = quantity
    consumed = ZERO
    for index, limit in enumerate(limits):
        if remaining <= ZERO:
            break
        if limit is None:
            amounts[index] = remaining
            remaining = ZERO
            break
        room = limit - consumed
        if room <= ZERO:
            continue
        taken = min(room, remaining)
        amounts[index] = taken
        consumed += taken
        remaining -= taken
    return amounts


def block_for(quantity: Decimal, blocks: Sequence[Block], scale: Decimal = D(1)) -> int:
    """Return the index of the block a whole quantity lands in."""

    limits = scaled_limits(blocks, scale)
    for index, limit in enumerate(limits):
        if limit is None or quantity <= limit:
            return index
    return len(blocks) - 1
