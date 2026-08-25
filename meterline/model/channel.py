"""Channels: the directional streams a meter records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..constants import DEFAULT_INTERVAL_MINUTES, SUPPORTED_INTERVAL_MINUTES
from ..core.units import Unit, UnitKind
from ..errors import ConfigurationError

__all__ = ["ChannelKind", "ChannelSpec"]


class ChannelKind(str, Enum):
    """What a channel measures, and in which direction."""

    DELIVERED = "delivered"
    """Energy flowing from the grid to the customer."""

    RECEIVED = "received"
    """Energy flowing from the customer to the grid (export)."""

    NET = "net"
    """A single signed channel; positive is delivered.

    A net channel cannot be decomposed back into delivered and received
    without the interval detail, which is why a tariff that prices export
    differently from import must refuse to rate one.
    """

    DEMAND = "demand"
    """Integrated demand, usually recorded at the same interval width."""

    REACTIVE = "reactive"
    """Reactive energy, used for power-factor charges."""

    @property
    def is_export(self) -> bool:
        """Return ``True`` for channels measuring customer-to-grid flow."""

        return self is ChannelKind.RECEIVED

    @property
    def is_signed(self) -> bool:
        """Return ``True`` when negative values are meaningful."""

        return self is ChannelKind.NET


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """The shape of an interval data stream."""

    channel_id: str
    meter_id: str
    kind: ChannelKind
    unit: Unit
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    multiplier: str = "1"
    label: str = ""

    def __post_init__(self) -> None:
        if self.interval_minutes not in SUPPORTED_INTERVAL_MINUTES:
            raise ConfigurationError(
                "unsupported interval width",
                channel=self.channel_id,
                minutes=self.interval_minutes,
                supported=", ".join(str(m) for m in SUPPORTED_INTERVAL_MINUTES),
            )
        if self.kind is ChannelKind.DEMAND and self.unit.kind is not UnitKind.POWER:
            raise ConfigurationError(
                "a demand channel must record a power unit",
                channel=self.channel_id,
                unit=str(self.unit),
            )

    @property
    def intervals_per_day(self) -> int:
        """Return how many intervals make up a nominal 24-hour day."""

        return (24 * 60) // self.interval_minutes

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the identifier."""

        return self.label or self.channel_id

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{self.display_name}: {self.kind.value} {self.unit} "
            f"at {self.interval_minutes}-minute intervals"
        )
