"""Deriving a delta from two dial readings.

A register counts up and wraps.  When the later reading is lower than the
earlier one, exactly one of four things happened, and the meter cannot tell
you which: the dial wrapped, the dial was reset, the meter was exchanged, or
somebody wrote the digits down wrong.  The policy chooses.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.decimals import ZERO, D
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.outcome import Outcome
from ..model.quality import QualityCode
from ..model.reading import MeterRead
from ..model.register import Register
from ..policy.conventions import RolloverPolicy
from ..policy.profile import UtilityProfile

__all__ = ["DeltaResult", "register_delta"]


@dataclass(frozen=True, slots=True)
class DeltaResult:
    """The outcome of comparing two dial readings."""

    value: Decimal
    """The delta in billable units, after the register multiplier."""

    quality: QualityCode
    rolled_over: bool = False
    note: str = ""

    @property
    def is_usable(self) -> bool:
        """Return ``True`` when the delta may be billed."""

        return self.quality.is_billable


def register_delta(
    register: Register,
    earlier: MeterRead,
    later: MeterRead,
    profile: UtilityProfile,
) -> Outcome[DeltaResult]:
    """Return the usage implied by two readings of the same register."""

    bag = DiagnosticBag()
    raw = register.raw_delta(earlier.value, later.value)
    subject = f"{register.register_id}@{later.at.isoformat()}"
    if raw >= ZERO:
        quality = _combined_quality(earlier, later)
        return Outcome(
            DeltaResult(register.apply_multiplier(raw), quality), bag
        )

    policy = profile.rollover
    wrapped = register.wrapped_delta(earlier.value, later.value)
    threshold = register.rollover_at * profile.rollover_threshold

    if policy is RolloverPolicy.REJECT:
        bag.emit(
            "meterdata.rollover.rejected",
            "the dial went backwards and the policy refuses to guess why",
            Severity.ERROR,
            subject,
            earlier=str(earlier.value),
            later=str(later.value),
        )
        return Outcome(DeltaResult(ZERO, QualityCode.MISSING, note="rejected"), bag)

    if policy is RolloverPolicy.TREAT_AS_RESET:
        bag.emit(
            "meterdata.rollover.reset",
            "the dial went backwards and was treated as a reset to zero",
            Severity.NOTICE,
            subject,
            later=str(later.value),
        )
        return Outcome(
            DeltaResult(
                register.apply_multiplier(later.value),
                QualityCode.SUSPECT,
                note="treated as a reset",
            ),
            bag,
        )

    if policy is RolloverPolicy.THRESHOLD and wrapped > threshold:
        bag.emit(
            "meterdata.rollover.implausible",
            "a rollover would imply more usage than the threshold allows",
            Severity.WARNING,
            subject,
            implied=str(register.apply_multiplier(wrapped)),
            threshold=str(register.apply_multiplier(threshold)),
        )
        return Outcome(
            DeltaResult(
                ZERO,
                QualityCode.SUSPECT,
                note="rollover rejected as implausible",
            ),
            bag,
        )

    bag.emit(
        "meterdata.rollover.applied",
        "the dial wrapped past its maximum and one turn was added back",
        Severity.NOTICE,
        subject,
        width=str(register.rollover_at),
        implied=str(register.apply_multiplier(wrapped)),
    )
    quality = _combined_quality(earlier, later)
    return Outcome(
        DeltaResult(
            register.apply_multiplier(wrapped),
            quality,
            rolled_over=True,
            note="one dial turn added",
        ),
        bag,
    )


def _combined_quality(earlier: MeterRead, later: MeterRead) -> QualityCode:
    """Return the worse of two reads' quality codes.

    A delta is only as good as its weaker endpoint: an actual read taken
    against an estimated one produces an estimated quantity, however precise
    the later dial value is.
    """

    return max((earlier.quality, later.quality), key=lambda code: code.rank)


def implied_daily_usage(delta: Decimal, hours: Decimal) -> Decimal:
    """Return the daily rate a delta implies over a number of hours."""

    if hours <= ZERO:
        return ZERO
    return delta * D(24) / hours
