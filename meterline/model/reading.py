"""Meter reads and register change events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..core.decimals import D
from ..core.ids import stable_id
from ..timeline.instants import ensure_utc, format_instant
from .quality import QualityCode, ReadType

__all__ = ["MeterRead", "RegisterChange"]


@dataclass(frozen=True, slots=True)
class MeterRead:
    """One observation of one register's dial at one instant."""

    read_id: str
    meter_id: str
    register_id: str
    at: datetime
    value: Decimal
    read_type: ReadType = ReadType.ACTUAL
    quality: QualityCode = QualityCode.VALID
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", ensure_utc(self.at, what="read timestamp"))
        object.__setattr__(self, "value", D(self.value))

    @classmethod
    def build(
        cls,
        meter_id: str,
        register_id: str,
        at: datetime,
        value: Decimal | str | int,
        read_type: ReadType = ReadType.ACTUAL,
        quality: QualityCode = QualityCode.VALID,
        source: str = "",
        note: str = "",
    ) -> "MeterRead":
        """Build a read with a deterministic identifier."""

        moment = ensure_utc(at, what="read timestamp")
        read_id = stable_id(
            "rd", meter_id, register_id, moment.isoformat(), str(D(value))
        )
        return cls(
            read_id,
            meter_id,
            register_id,
            moment,
            D(value),
            read_type,
            quality,
            source,
            note,
        )

    @property
    def key(self) -> tuple[str, str, datetime]:
        """Return the natural ordering key for a read."""

        return (self.meter_id, self.register_id, self.at)

    @property
    def is_billable(self) -> bool:
        """Return ``True`` when the read may be used to close a cycle."""

        return self.read_type.bills_by_default and self.quality.is_billable

    def with_quality(self, quality: QualityCode) -> "MeterRead":
        """Return a copy carrying a different quality code."""

        return MeterRead(
            self.read_id,
            self.meter_id,
            self.register_id,
            self.at,
            self.value,
            self.read_type,
            quality,
            self.source,
            self.note,
        )

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{format_instant(self.at)} {self.register_id} = {self.value} "
            f"({self.read_type.value}/{self.quality.value})"
        )


@dataclass(frozen=True, slots=True)
class RegisterChange:
    """A meter exchange or a dial reset.

    Consumption across a change is the old register's final delta plus the
    new register's initial delta.  Treating the two dial values as a single
    series instead produces a negative or an enormous reading, which the
    rollover heuristics will then confidently misclassify.
    """

    change_id: str
    meter_id: str
    register_id: str
    at: datetime
    final_value: Decimal
    initial_value: Decimal
    reason: str = "exchange"
    new_register_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", ensure_utc(self.at, what="change timestamp"))
        object.__setattr__(self, "final_value", D(self.final_value))
        object.__setattr__(self, "initial_value", D(self.initial_value))

    @classmethod
    def build(
        cls,
        meter_id: str,
        register_id: str,
        at: datetime,
        final_value: Decimal | str | int,
        initial_value: Decimal | str | int,
        reason: str = "exchange",
        new_register_id: str = "",
    ) -> "RegisterChange":
        """Build a change event with a deterministic identifier."""

        moment = ensure_utc(at, what="change timestamp")
        change_id = stable_id("chg", meter_id, register_id, moment.isoformat())
        return cls(
            change_id,
            meter_id,
            register_id,
            moment,
            D(final_value),
            D(initial_value),
            reason,
            new_register_id,
        )

    @property
    def target_register_id(self) -> str:
        """Return the register the series continues on after the change."""

        return self.new_register_id or self.register_id

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{format_instant(self.at)} {self.register_id}: "
            f"{self.final_value} -> {self.initial_value} ({self.reason})"
        )
