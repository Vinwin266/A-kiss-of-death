"""Meters: the devices carrying registers and channels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..errors import ConfigurationError, UnknownReferenceError
from ..timeline.spans import Span
from .channel import ChannelSpec
from .register import Register

__all__ = ["MeterKind", "Meter"]


from enum import Enum


class MeterKind(str, Enum):
    """The commodity a meter measures."""

    ELECTRIC = "electric"
    GAS = "gas"
    WATER = "water"

    @property
    def label(self) -> str:
        """Return a readable name."""

        return self.value.capitalize()


@dataclass(frozen=True, slots=True)
class Meter:
    """A physical device installed at a service point."""

    meter_id: str
    service_point_id: str
    kind: MeterKind
    registers: tuple[Register, ...] = ()
    channels: tuple[ChannelSpec, ...] = ()
    serial: str = ""
    installed_at: datetime | None = None
    removed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.registers and not self.channels:
            raise ConfigurationError(
                "a meter needs at least one register or channel",
                meter=self.meter_id,
            )
        seen: set[str] = set()
        for register in self.registers:
            if register.register_id in seen:
                raise ConfigurationError(
                    "duplicate register identifier",
                    meter=self.meter_id,
                    register=register.register_id,
                )
            seen.add(register.register_id)

    @property
    def has_interval_data(self) -> bool:
        """Return ``True`` when the meter records interval channels."""

        return bool(self.channels)

    @property
    def is_tou_metered(self) -> bool:
        """Return ``True`` when registers are split by time-of-use bucket."""

        return any(register.is_tou for register in self.registers)

    @property
    def service_span(self) -> Span | None:
        """Return the span the meter was installed for, when both ends known."""

        if self.installed_at is None or self.removed_at is None:
            return None
        return Span(self.installed_at, self.removed_at)

    def was_installed_during(self, span: Span) -> bool:
        """Return ``True`` when the meter served any part of ``span``."""

        if self.installed_at is not None and self.installed_at >= span.end:
            return False
        if self.removed_at is not None and self.removed_at <= span.start:
            return False
        return True

    def register(self, register_id: str) -> Register:
        """Return a register by identifier."""

        for candidate in self.registers:
            if candidate.register_id == register_id:
                return candidate
        raise UnknownReferenceError(
            "no such register on this meter",
            kind="register",
            identifier=register_id,
            meter=self.meter_id,
        )

    def channel(self, channel_id: str) -> ChannelSpec:
        """Return a channel by identifier."""

        for candidate in self.channels:
            if candidate.channel_id == channel_id:
                return candidate
        raise UnknownReferenceError(
            "no such channel on this meter",
            kind="channel",
            identifier=channel_id,
            meter=self.meter_id,
        )

    def registers_for_bucket(self, bucket: str) -> tuple[Register, ...]:
        """Return the registers accumulating a given time-of-use bucket."""

        return tuple(
            register for register in self.registers if register.tou_bucket == bucket
        )

    def describe(self) -> str:
        """Return a one-line description for reports."""

        parts = [f"{self.meter_id} ({self.kind.label})"]
        if self.serial:
            parts.append(f"serial {self.serial}")
        parts.append(f"{len(self.registers)} register(s)")
        if self.channels:
            parts.append(f"{len(self.channels)} channel(s)")
        return ", ".join(parts)
