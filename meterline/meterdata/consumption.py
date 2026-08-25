"""Consumption records: usage attributed to a span."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

from ..core.decimals import ZERO, D, safe_divide
from ..core.quantity import Quantity
from ..core.units import Unit
from ..model.quality import QualityCode, QualityMergeRule, merge_quality
from ..timeline.spans import Span

__all__ = ["Consumption", "total_quantity", "merge_consumption_quality", "clip"]


@dataclass(frozen=True, slots=True)
class Consumption:
    """Usage over a span, with the provenance needed to justify it."""

    span: Span
    quantity: Quantity
    quality: QualityCode = QualityCode.VALID
    register_id: str = ""
    source: str = "register"
    note: str = ""

    @property
    def unit(self) -> Unit:
        """Return the unit of the recorded quantity."""

        return self.quantity.unit

    @property
    def daily_rate(self) -> Decimal:
        """Return the average usage per 24 hours over the span."""

        hours = self.span.hours
        if hours <= ZERO:
            return ZERO
        return safe_divide(self.quantity.value * D(24), hours)

    @property
    def is_estimated(self) -> bool:
        """Return ``True`` when the value was not directly measured."""

        return self.quality.needs_true_up

    def clipped_to(self, bounds: Span) -> "Consumption | None":
        """Return the part of this record inside ``bounds``.

        Usage is apportioned by elapsed time, which is the convention every
        utility uses when a read does not land on a cycle boundary.  It is
        also the convention that is most obviously wrong for a customer whose
        usage is not uniform, which is why the result is flagged.
        """

        overlap = self.span.intersection(bounds)
        if overlap is None or overlap.is_empty:
            return None
        if overlap.duration == self.span.duration:
            return self
        share = safe_divide(D(overlap.seconds), D(self.span.seconds))
        quality = (
            self.quality
            if self.quality.rank >= QualityCode.PARTIAL.rank
            else QualityCode.PARTIAL
        )
        return Consumption(
            overlap,
            Quantity(self.quantity.value * share, self.unit),
            quality,
            self.register_id,
            self.source,
            f"apportioned {share} of a {self.span.hours}-hour read interval",
        )

    def with_quality(self, quality: QualityCode) -> "Consumption":
        """Return a copy carrying a different quality code."""

        return Consumption(
            self.span, self.quantity, quality, self.register_id, self.source, self.note
        )

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.span.describe()} {self.quantity} ({self.quality.value})"


def clip(records: Sequence[Consumption], bounds: Span) -> list[Consumption]:
    """Return every record narrowed to ``bounds``, dropping those outside."""

    clipped: list[Consumption] = []
    for record in records:
        piece = record.clipped_to(bounds)
        if piece is not None:
            clipped.append(piece)
    return clipped


def total_quantity(records: Iterable[Consumption], unit: Unit) -> Quantity:
    """Return the total usage of a collection of records."""

    total = Quantity.zero(unit)
    for record in records:
        total = total + record.quantity.to(unit)
    return total


def merge_consumption_quality(
    records: Sequence[Consumption],
    rule: QualityMergeRule = QualityMergeRule.WORST_WINS,
) -> QualityCode:
    """Return the quality of a collection under a merge rule."""

    if not records:
        return QualityCode.MISSING
    return merge_quality(
        [(record.quality, record.quantity.value) for record in records], rule
    )
