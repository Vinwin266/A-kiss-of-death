"""Deriving consumption records from a register's read history."""

from __future__ import annotations

from typing import Sequence

from ..core.diagnostics import DiagnosticBag, Severity
from ..core.outcome import Outcome
from ..core.quantity import Quantity
from ..model.quality import QualityCode
from ..model.reading import MeterRead, RegisterChange
from ..model.register import Register
from ..policy.profile import UtilityProfile
from ..timeline.spans import Span
from .consumption import Consumption, clip
from .rollover import register_delta

__all__ = ["derive_consumption", "billable_reads"]


def billable_reads(reads: Sequence[MeterRead]) -> list[MeterRead]:
    """Return the reads that may close a period, in time order.

    Check reads are dropped unless nothing else is available for the same
    instant: their purpose is to verify a route, and letting one close a
    cycle produces a bill nobody scheduled.
    """

    ordered = sorted(reads, key=lambda read: (read.at, read.read_id))
    by_instant: dict[str, list[MeterRead]] = {}
    for read in ordered:
        by_instant.setdefault(read.at.isoformat(), []).append(read)
    kept: list[MeterRead] = []
    for key in sorted(by_instant):
        group = by_instant[key]
        billable = [read for read in group if read.is_billable]
        kept.append(billable[0] if billable else group[0])
    return kept


def _apply_changes(
    reads: Sequence[MeterRead],
    changes: Sequence[RegisterChange],
) -> list[tuple[MeterRead, MeterRead]]:
    """Return consecutive read pairs, split around register changes.

    A change contributes two synthetic reads at the same instant — the old
    dial's final value and the new dial's initial value — so that the pair
    either side of it is compared against the right endpoint.
    """

    pairs: list[tuple[MeterRead, MeterRead]] = []
    ordered_changes = sorted(changes, key=lambda change: change.at)
    for earlier, later in zip(reads, reads[1:]):
        between = [
            change
            for change in ordered_changes
            if earlier.at < change.at <= later.at
        ]
        if not between:
            pairs.append((earlier, later))
            continue
        cursor = earlier
        for change in between:
            closing = MeterRead.build(
                change.meter_id,
                change.register_id,
                change.at,
                change.final_value,
                cursor.read_type,
                cursor.quality,
                source="register-change",
                note=change.reason,
            )
            pairs.append((cursor, closing))
            cursor = MeterRead.build(
                change.meter_id,
                change.target_register_id,
                change.at,
                change.initial_value,
                later.read_type,
                later.quality,
                source="register-change",
                note=change.reason,
            )
        if cursor.at < later.at:
            pairs.append((cursor, later))
        # When the exchange happened at the moment of the closing read there
        # is nothing left to measure on the new dial; appending the pair
        # anyway would produce a zero-length interval and a spurious
        # "two reads share an instant" warning.
    return pairs


def derive_consumption(
    register: Register,
    reads: Sequence[MeterRead],
    span: Span,
    profile: UtilityProfile,
    *,
    changes: Sequence[RegisterChange] = (),
) -> Outcome[list[Consumption]]:
    """Return the consumption records covering ``span``.

    Reads outside the span are used as endpoints and the resulting records
    are apportioned back to the span, which is how a cycle gets billed when
    the meter was read three days late.
    """

    bag = DiagnosticBag()
    usable = billable_reads(reads)
    if len(usable) < 2:
        bag.emit(
            "meterdata.derive.insufficient_reads",
            "at least two reads are needed to derive consumption",
            Severity.WARNING,
            register.register_id,
            found=len(usable),
        )
        return Outcome([], bag)

    records: list[Consumption] = []
    for earlier, later in _apply_changes(usable, changes):
        if later.at <= earlier.at:
            bag.emit(
                "meterdata.derive.duplicate_instant",
                "two reads share an instant and cannot be ordered",
                Severity.WARNING,
                register.register_id,
                at=later.at.isoformat(),
            )
            continue
        outcome = register_delta(register, earlier, later, profile)
        bag.merge(outcome.diagnostics)
        delta = outcome.value
        quality = delta.quality
        if earlier.read_type.value == "estimated" or later.read_type.value == "estimated":
            quality = max(
                (quality, QualityCode.ESTIMATED), key=lambda code: code.rank
            )
        records.append(
            Consumption(
                Span(earlier.at, later.at),
                Quantity(delta.value, register.unit),
                quality,
                register.register_id,
                "register",
                delta.note,
            )
        )

    inside = clip(records, span)
    if not inside:
        bag.emit(
            "meterdata.derive.no_coverage",
            "no read interval overlaps the period being billed",
            Severity.WARNING,
            register.register_id,
            span=span.describe(),
        )
    return Outcome(inside, bag)


def coverage(records: Sequence[Consumption]) -> list[Span]:
    """Return the spans covered by a set of consumption records."""

    return [record.span for record in records]
