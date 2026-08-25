"""Validation rules over derived consumption.

The industry calls this the "V" of VEE — validation, estimation, editing.
Each rule answers one question about whether a number is believable, and
none of them can prove that it is; a rule's job is to raise its hand, not to
decide what happens next.  What happens next is the suspect-data policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

from ..core.decimals import ZERO, D, is_zero, mean, safe_divide
from ..core.diagnostics import Diagnostic, DiagnosticBag, Severity
from ..core.quantity import Quantity
from ..model.quality import QualityCode
from ..model.series import IntervalSeries
from ..policy.profile import UtilityProfile
from ..timeline.spans import Span
from .consumption import Consumption

__all__ = ["ValidationRule", "validate_consumption", "RULES"]


@dataclass(frozen=True, slots=True)
class ValidationRule:
    """One named check over a period's consumption."""

    code: str
    label: str
    check: Callable[["ValidationInput"], list[Diagnostic]]

    def run(self, inputs: "ValidationInput") -> list[Diagnostic]:
        """Apply the rule."""

        return self.check(inputs)


@dataclass(slots=True)
class ValidationInput:
    """The material a validation rule may inspect."""

    span: Span
    records: tuple[Consumption, ...]
    history: tuple[Consumption, ...]
    profile: UtilityProfile
    subject: str = ""
    series: IntervalSeries | None = None

    @property
    def total(self) -> Decimal:
        """Return the total usage of the period."""

        return sum((record.quantity.value for record in self.records), ZERO)

    @property
    def days(self) -> Decimal:
        """Return the period length in days."""

        return safe_divide(D(self.span.seconds), D(86400))

    @property
    def daily_rate(self) -> Decimal:
        """Return the period's average daily usage."""

        return safe_divide(self.total, self.days)

    def historic_daily_rate(self) -> Decimal:
        """Return the average daily usage of the history."""

        rates = [
            record.daily_rate
            for record in self.history
            if record.quality.is_billable and record.span.hours > ZERO
        ]
        return mean(rates)


def _negative_usage(inputs: ValidationInput) -> list[Diagnostic]:
    """Flag any record with negative usage on a non-net register."""

    found: list[Diagnostic] = []
    for record in inputs.records:
        if record.quantity.value < ZERO:
            found.append(
                Diagnostic.make(
                    "meterdata.validate.negative",
                    "usage went backwards over this interval",
                    Severity.WARNING,
                    inputs.subject,
                    span=record.span.describe(),
                    value=str(record.quantity.value),
                )
            )
    return found


def _spike(inputs: ValidationInput) -> list[Diagnostic]:
    """Flag a period well above its own history."""

    baseline = inputs.historic_daily_rate()
    if is_zero(baseline):
        return []
    limit = baseline * inputs.profile.spike_multiple
    if inputs.daily_rate > limit:
        return [
            Diagnostic.make(
                "meterdata.validate.spike",
                "usage is far above this meter's recent history",
                Severity.WARNING,
                inputs.subject,
                daily=str(inputs.daily_rate),
                baseline=str(baseline),
                factor=str(inputs.profile.spike_factor),
            )
        ]
    return []


def _dropout(inputs: ValidationInput) -> list[Diagnostic]:
    """Flag a period well below its own history."""

    baseline = inputs.historic_daily_rate()
    if is_zero(baseline) or is_zero(inputs.daily_rate):
        return []
    ratio = safe_divide(inputs.daily_rate, baseline)
    if ratio < safe_divide(D(1), inputs.profile.spike_multiple):
        return [
            Diagnostic.make(
                "meterdata.validate.dropout",
                "usage is far below this meter's recent history",
                Severity.NOTICE,
                inputs.subject,
                daily=str(inputs.daily_rate),
                baseline=str(baseline),
            )
        ]
    return []


def _stopped_meter(inputs: ValidationInput) -> list[Diagnostic]:
    """Flag a long stretch of exactly zero usage."""

    if not is_zero(inputs.total):
        return []
    if inputs.days < D(inputs.profile.zero_usage_days):
        return []
    return [
        Diagnostic.make(
            "meterdata.validate.stopped",
            "no usage at all over a long period; the meter may have stopped",
            Severity.WARNING,
            inputs.subject,
            days=str(inputs.days),
        )
    ]


def _interval_sum(inputs: ValidationInput) -> list[Diagnostic]:
    """Compare interval totals against the register-derived total."""

    if inputs.series is None:
        return []
    if not inputs.series.span.contains_span(inputs.span):
        # Comparing a register delta against a series that covers only part
        # of the period would flag every cycle at the edges of the interval
        # data, which is noise rather than a finding.
        return []
    interval_total = inputs.series.total_in(inputs.span).value
    register_total = inputs.total
    if is_zero(register_total):
        return []
    difference = abs(interval_total - register_total)
    relative = safe_divide(difference, abs(register_total))
    tolerance = D(inputs.profile.interval_sum_tolerance)
    if relative > tolerance:
        return [
            Diagnostic.make(
                "meterdata.validate.interval_mismatch",
                "interval data and the register disagree about total usage",
                Severity.WARNING,
                inputs.subject,
                interval=str(interval_total),
                register=str(register_total),
                relative=str(relative),
                tolerance=str(tolerance),
            )
        ]
    return []


def _quality_mix(inputs: ValidationInput) -> list[Diagnostic]:
    """Note when a period is billed from more than one kind of data."""

    codes = {record.quality for record in inputs.records}
    if len(codes) > 1:
        return [
            Diagnostic.make(
                "meterdata.validate.mixed_quality",
                "the period combines data of different quality",
                Severity.NOTICE,
                inputs.subject,
                codes=", ".join(sorted(code.value for code in codes)),
                merge=inputs.profile.quality_merge.value,
            )
        ]
    return []


RULES: tuple[ValidationRule, ...] = (
    ValidationRule("negative", "usage went backwards", _negative_usage),
    ValidationRule("spike", "usage far above history", _spike),
    ValidationRule("dropout", "usage far below history", _dropout),
    ValidationRule("stopped", "no usage for a long period", _stopped_meter),
    ValidationRule("interval_sum", "intervals disagree with the register", _interval_sum),
    ValidationRule("quality_mix", "mixed data quality", _quality_mix),
)


def validate_consumption(
    span: Span,
    records: Sequence[Consumption],
    profile: UtilityProfile,
    *,
    history: Sequence[Consumption] = (),
    subject: str = "",
    series: IntervalSeries | None = None,
    rules: Sequence[ValidationRule] = RULES,
) -> DiagnosticBag:
    """Run every rule and return the diagnostics they produced."""

    inputs = ValidationInput(
        span, tuple(records), tuple(history), profile, subject, series
    )
    bag = DiagnosticBag()
    for rule in rules:
        bag.extend(rule.run(inputs))
    return bag


def apply_suspect_policy(
    records: Sequence[Consumption], flagged: bool, profile: UtilityProfile
) -> list[Consumption]:
    """Mark records suspect when validation flagged the period.

    Deciding what to do about suspect data — bill it, re-estimate it or hold
    the bill — is the caller's job; this only stamps the quality code so the
    decision has something to read.
    """

    if not flagged:
        return list(records)
    del profile
    return [
        record
        if record.quality.rank >= QualityCode.SUSPECT.rank
        else record.with_quality(QualityCode.SUSPECT)
        for record in records
    ]


def total_of(records: Sequence[Consumption], unit) -> Quantity:  # noqa: ANN001
    """Return the total usage of a set of records."""

    total = Quantity.zero(unit)
    for record in records:
        total = total + record.quantity.to(unit)
    return total
