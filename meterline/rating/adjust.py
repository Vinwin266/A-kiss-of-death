"""Corrections to a bill that has already been issued.

Two shapes are in use and they are not interchangeable.  A *cancel and
rebill* reverses every line of the original and issues a replacement, so the
customer's statement shows the whole history.  A *delta adjustment* posts
only the difference as a single line on the next bill, which is tidier and
loses the detail of what changed.  Regulators tend to require the first for
anything material and permit the second for small corrections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..charge.classes import ChargeClass, ChargeSide
from ..charge.lineitem import LineItem, LineItemBuilder
from ..core.decimals import is_zero
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.money import Money
from ..policy.conventions import TrueUpPolicy
from ..policy.profile import UtilityProfile
from .invoice import Invoice

__all__ = ["AdjustmentResult", "cancel_and_rebill", "delta_adjustment", "true_up"]


@dataclass(slots=True)
class AdjustmentResult:
    """The lines a correction contributes, and why."""

    lines: tuple[LineItem, ...]
    difference: Money
    diagnostics: DiagnosticBag

    @property
    def is_material(self) -> bool:
        """Return ``True`` when the correction changes the amount due."""

        return not is_zero(self.difference.amount)


def cancel_and_rebill(original: Invoice, replacement: Invoice) -> AdjustmentResult:
    """Return reversal lines for ``original`` plus ``replacement``'s lines."""

    bag = DiagnosticBag()
    reversals = [line.negated() for line in original.ordered_lines()]
    difference = replacement.total - original.total
    bag.emit(
        "rating.adjust.cancel_rebill",
        "an earlier bill was reversed in full and reissued",
        Severity.NOTICE,
        original.service_point_id,
        original_bill=original.bill_id,
        original_total=original.total.format(),
        new_total=replacement.total.format(),
    )
    return AdjustmentResult(
        tuple(reversals) + tuple(replacement.ordered_lines()), difference, bag
    )


def delta_adjustment(
    original: Invoice, replacement: Invoice, *, code: str = "adjust.delta"
) -> AdjustmentResult:
    """Return a single line for the difference between two bills."""

    bag = DiagnosticBag()
    difference = replacement.total - original.total
    if is_zero(difference.amount):
        bag.emit(
            "rating.adjust.no_change",
            "the recomputed bill matches the original; no adjustment was posted",
            Severity.INFO,
            original.service_point_id,
            bill=original.bill_id,
        )
        return AdjustmentResult((), difference, bag)
    builder = LineItemBuilder(
        code,
        f"Adjustment for {original.span.start.date().isoformat()}",
        ChargeClass.ADJUSTMENT,
        "adjustment",
        ChargeSide.OTHER,
    )
    builder.note("original total", "", original.total.format())
    builder.note("recomputed total", "", replacement.total.format())
    builder.exempt()
    bag.emit(
        "rating.adjust.delta",
        "the difference from an earlier bill was posted as one line",
        Severity.NOTICE,
        original.service_point_id,
        original_bill=original.bill_id,
        difference=difference.format(),
    )
    return AdjustmentResult((builder.seal(difference),), difference, bag)


def true_up(
    original: Invoice,
    replacement: Invoice,
    profile: UtilityProfile,
) -> AdjustmentResult:
    """Correct an estimated bill under the profile's true-up convention."""

    bag = DiagnosticBag()
    if profile.true_up is TrueUpPolicy.NONE:
        bag.emit(
            "rating.true_up.skipped",
            "the policy leaves estimated bills uncorrected",
            Severity.WARNING,
            original.service_point_id,
            bill=original.bill_id,
        )
        return AdjustmentResult((), replacement.total - original.total, bag)
    if profile.true_up is TrueUpPolicy.CANCEL_REBILL:
        result = cancel_and_rebill(original, replacement)
        result.diagnostics.merge(bag)
        return result
    result = delta_adjustment(original, replacement)
    result.diagnostics.merge(bag)
    return result


def combined_total(lines: Sequence[LineItem], currency: str) -> Money:
    """Return the total of a set of adjustment lines."""

    total = Money.zero(currency)
    for line in lines:
        total = total + line.amount
    return total
