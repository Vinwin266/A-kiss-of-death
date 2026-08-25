"""Read types, quality codes and how they combine.

Quality is not a boolean.  A cycle's usage can be part actual, part
estimated and part edited, and the question "what quality is the total?"
has three defensible answers that real systems ship:

* the worst part wins, so one estimated day makes the bill estimated;
* the dominant part wins, by share of usage;
* actual wins if any part is actual, which is what makes an "estimated"
  flag quietly disappear from bills that are mostly guesses.

The engine implements all three and makes the choice explicit.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Iterable, Sequence

from ..core.decimals import ZERO, D

__all__ = ["ReadType", "QualityCode", "QualityMergeRule", "merge_quality"]


class ReadType(str, Enum):
    """How a register value came to be known."""

    ACTUAL = "actual"
    """A meter reader or an AMI endpoint reported the dial."""

    ESTIMATED = "estimated"
    """The engine or the upstream system produced the value."""

    CUSTOMER = "customer"
    """The customer supplied the value; trusted, but flagged."""

    CHECK = "check"
    """A verification read, not used to bill unless it is the only one."""

    PRORATED = "prorated"
    """A value interpolated to a cycle boundary from surrounding reads."""

    SYSTEM = "system"
    """A value written by a meter exchange or a register reset."""

    @property
    def is_measured(self) -> bool:
        """Return ``True`` when a physical dial was actually observed."""

        return self in (ReadType.ACTUAL, ReadType.CUSTOMER, ReadType.CHECK)

    @property
    def bills_by_default(self) -> bool:
        """Return ``True`` when the read may close a cycle on its own."""

        return self is not ReadType.CHECK


class QualityCode(str, Enum):
    """The confidence attached to a value, ordered by severity."""

    VALID = "valid"
    """Measured, validated, unmodified."""

    ESTIMATED = "estimated"
    """Filled in by a model rather than measured."""

    EDITED = "edited"
    """Measured, then changed by a human with a reason code."""

    PARTIAL = "partial"
    """Covers less than the span it is attached to."""

    SUSPECT = "suspect"
    """Failed a validation rule but was retained."""

    MISSING = "missing"
    """No value at all; the span is a hole."""

    @property
    def rank(self) -> int:
        """Return a severity rank; higher is worse."""

        return _RANKS[self]

    @property
    def is_billable(self) -> bool:
        """Return ``True`` when the value may appear on a bill as-is."""

        return self is not QualityCode.MISSING

    @property
    def needs_true_up(self) -> bool:
        """Return ``True`` when a later actual read should correct this."""

        return self in (QualityCode.ESTIMATED, QualityCode.PARTIAL)


_RANKS = {
    QualityCode.VALID: 0,
    QualityCode.EDITED: 1,
    QualityCode.ESTIMATED: 2,
    QualityCode.PARTIAL: 3,
    QualityCode.SUSPECT: 4,
    QualityCode.MISSING: 5,
}


class QualityMergeRule(str, Enum):
    """How the quality of a whole is derived from the quality of its parts."""

    WORST_WINS = "worst_wins"
    """The most severe part sets the result; the conservative reading."""

    DOMINANT_SHARE = "dominant_share"
    """The quality carrying the most usage sets the result."""

    MEASURED_WINS = "measured_wins"
    """Any valid part makes the whole valid; the most permissive reading."""

    MAJORITY_VALID = "majority_valid"
    """Valid when strictly more than half the usage is valid."""


def merge_quality(
    parts: Sequence[tuple[QualityCode, Decimal]],
    rule: QualityMergeRule = QualityMergeRule.WORST_WINS,
) -> QualityCode:
    """Combine ``(quality, weight)`` pairs into one quality code.

    Weights are usage magnitudes.  Zero-usage parts still count for
    :data:`QualityMergeRule.WORST_WINS` — an estimated day of zero usage is
    still an estimate — but cannot win a share-based rule.
    """

    if not parts:
        return QualityCode.MISSING
    if rule is QualityMergeRule.WORST_WINS:
        return max((code for code, _ in parts), key=lambda code: code.rank)
    totals: dict[QualityCode, Decimal] = {}
    for code, weight in parts:
        totals[code] = totals.get(code, ZERO) + abs(D(weight))
    grand = sum(totals.values(), ZERO)
    if rule is QualityMergeRule.MEASURED_WINS:
        return (
            QualityCode.VALID
            if QualityCode.VALID in totals
            else max(totals, key=lambda code: code.rank)
        )
    if rule is QualityMergeRule.MAJORITY_VALID:
        valid = totals.get(QualityCode.VALID, ZERO)
        if grand > ZERO and valid * 2 > grand:
            return QualityCode.VALID
        return max(totals, key=lambda code: code.rank)
    if grand == ZERO:
        return max(totals, key=lambda code: code.rank)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0].rank))
    return ranked[0][0]


def worst_of(codes: Iterable[QualityCode]) -> QualityCode:
    """Return the most severe code in ``codes``, or ``VALID`` when empty."""

    materialised = list(codes)
    if not materialised:
        return QualityCode.VALID
    return max(materialised, key=lambda code: code.rank)
