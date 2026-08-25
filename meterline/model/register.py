"""Registers: the cumulative dials on a meter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.decimals import ONE, D
from ..core.units import Unit
from ..errors import ConfigurationError
from .channel import ChannelKind

__all__ = ["Register"]


@dataclass(frozen=True, slots=True)
class Register:
    """One cumulative dial, with the arithmetic needed to read it.

    A register is a counter of fixed width that wraps.  Two facts about it
    decide whether a bill is right: how many digits it has, and what the
    multiplier is between the dial and the unit the tariff prices.  Getting
    the second wrong is a factor-of-forty error that looks entirely
    plausible on a commercial account.
    """

    register_id: str
    meter_id: str
    unit: Unit
    digits: int = 5
    multiplier: str = "1"
    channel: ChannelKind = ChannelKind.DELIVERED
    tou_bucket: str = ""
    """The time-of-use bucket this dial accumulates, if the meter splits."""

    label: str = ""
    decimals: int = 0
    """Decimal places physically present on the dial."""

    def __post_init__(self) -> None:
        if not 1 <= self.digits <= 12:
            raise ConfigurationError(
                "register width out of range",
                register=self.register_id,
                digits=self.digits,
            )
        if self.decimals < 0 or self.decimals >= self.digits:
            raise ConfigurationError(
                "register decimals must fit inside its width",
                register=self.register_id,
                decimals=self.decimals,
                digits=self.digits,
            )
        if D(self.multiplier) <= 0:
            raise ConfigurationError(
                "register multiplier must be positive",
                register=self.register_id,
                multiplier=self.multiplier,
            )

    @property
    def factor(self) -> Decimal:
        """Return the multiplier as a decimal."""

        return D(self.multiplier)

    @property
    def rollover_at(self) -> Decimal:
        """Return the value at which the dial wraps back to zero."""

        return D(10) ** (self.digits - self.decimals)

    @property
    def is_tou(self) -> bool:
        """Return ``True`` when the dial accumulates one TOU bucket only."""

        return bool(self.tou_bucket)

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the identifier."""

        return self.label or self.register_id

    def raw_delta(self, earlier: Decimal, later: Decimal) -> Decimal:
        """Return the dial difference, without applying the multiplier."""

        return D(later) - D(earlier)

    def apply_multiplier(self, dial_delta: Decimal) -> Decimal:
        """Convert a dial difference into billable units."""

        return D(dial_delta) * self.factor

    def wrapped_delta(self, earlier: Decimal, later: Decimal) -> Decimal:
        """Return the delta assuming exactly one rollover occurred."""

        return self.raw_delta(earlier, later) + self.rollover_at

    def plausible_maximum(self, hours: Decimal) -> Decimal:
        """Return the largest delta a full dial could represent in ``hours``.

        Used by the rollover heuristics: a delta implying more than a full
        turn of the dial in the elapsed time is not a rollover, it is a bad
        read or a register change.
        """

        del hours  # the bound is the dial width, not a rate
        return self.rollover_at * self.factor

    def describe(self) -> str:
        """Return a one-line description for reports."""

        parts = [f"{self.display_name}: {self.digits}-digit {self.unit}"]
        if self.factor != ONE:
            parts.append(f"x{self.factor}")
        if self.is_tou:
            parts.append(f"bucket {self.tou_bucket}")
        if self.channel is not ChannelKind.DELIVERED:
            parts.append(self.channel.value)
        return ", ".join(parts)
