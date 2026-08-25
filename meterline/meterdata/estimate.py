"""Estimating usage for a period with no data.

Every estimate is a guess dressed as a number, so each one carries the
strategy that produced it and a quality code that survives into the bill.
The strategies differ in what they assume: that last month resembles this
month, that last year does, or that the shape of a day is stable even when
its total is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from ..constants import MAX_ESTIMATION_DAYS
from ..core.decimals import ZERO, D, dsum, mean, safe_divide
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.outcome import Outcome
from ..core.quantity import Quantity
from ..core.units import Unit
from ..model.quality import QualityCode
from ..policy.conventions import EstimationStrategy
from ..policy.profile import UtilityProfile
from ..timeline.daytypes import classify_day
from ..timeline.holidays import HolidayCalendar
from ..timeline.spans import Span
from ..timeline.zones import Zone
from .consumption import Consumption
from .shapes import FLAT_SHAPE, LoadShape

__all__ = ["EstimationInput", "estimate_span"]


@dataclass(slots=True)
class EstimationInput:
    """Everything the estimators may look at."""

    history: tuple[Consumption, ...] = ()
    """Prior consumption records, oldest first."""

    zone: Zone | None = None
    holidays: HolidayCalendar | None = None
    shape: LoadShape = FLAT_SHAPE

    def recent(self, limit: int) -> list[Consumption]:
        """Return the most recent ``limit`` usable records."""

        usable = [
            record
            for record in self.history
            if record.quality.is_billable and record.quality is not QualityCode.SUSPECT
        ]
        return usable[-limit:] if limit > 0 else usable

    def same_period_last_year(self, span: Span) -> list[Consumption]:
        """Return the records overlapping the same span one year earlier."""

        shifted = Span(span.start - timedelta(days=365), span.end - timedelta(days=365))
        return [
            record
            for record in self.history
            if record.span.overlaps(shifted) and record.quality.is_billable
        ]


def _daily_rates(records: Sequence[Consumption]) -> list[Decimal]:
    """Return the daily usage rate implied by each record."""

    return [record.daily_rate for record in records if record.span.hours > ZERO]


def estimate_span(
    span: Span,
    unit: Unit,
    profile: UtilityProfile,
    inputs: EstimationInput,
    *,
    subject: str = "",
) -> Outcome[Consumption]:
    """Return an estimated consumption record covering ``span``."""

    bag = DiagnosticBag()
    days = safe_divide(D(span.seconds), D(86400))
    if days > D(MAX_ESTIMATION_DAYS):
        bag.emit(
            "meterdata.estimate.too_long",
            "the period is longer than the estimators will attempt",
            Severity.ERROR,
            subject,
            days=str(days),
        )
        return Outcome(
            Consumption(span, Quantity.zero(unit), QualityCode.MISSING, source="estimate"),
            bag,
        )

    strategy = profile.estimation
    if strategy is EstimationStrategy.ZERO:
        bag.emit(
            "meterdata.estimate.zero",
            "the policy estimates nothing, so the period contributes no usage",
            Severity.WARNING,
            subject,
            span=span.describe(),
        )
        return Outcome(
            Consumption(
                span,
                Quantity.zero(unit),
                QualityCode.ESTIMATED,
                source="estimate",
                note="zero strategy",
            ),
            bag,
        )

    if strategy is EstimationStrategy.PRIOR_PERIOD:
        matched = inputs.same_period_last_year(span)
        if matched:
            total = dsum(record.quantity.to(unit).value for record in matched)
            matched_days = dsum(
                safe_divide(D(record.span.seconds), D(86400)) for record in matched
            )
            scaled = (
                safe_divide(total * days, matched_days) if matched_days > ZERO else total
            )
            bag.emit(
                "meterdata.estimate.prior_period",
                "usage was estimated from the same period one year earlier",
                Severity.WARNING,
                subject,
                basis=str(total),
                days=str(days),
            )
            return Outcome(
                Consumption(
                    span,
                    Quantity(scaled, unit),
                    QualityCode.ESTIMATED,
                    source="estimate",
                    note="prior period",
                ),
                bag,
            )
        bag.emit(
            "meterdata.estimate.no_prior_period",
            "no data from a year ago; the trailing average was used instead",
            Severity.NOTICE,
            subject,
        )

    recent = inputs.recent(profile.estimation_lookback_cycles)
    rates = _daily_rates(recent)
    if not rates:
        bag.emit(
            "meterdata.estimate.no_history",
            "no usable history, so the estimate is zero",
            Severity.ERROR,
            subject,
            span=span.describe(),
        )
        return Outcome(
            Consumption(
                span,
                Quantity.zero(unit),
                QualityCode.ESTIMATED,
                source="estimate",
                note="no history",
            ),
            bag,
        )

    average = mean(rates)
    total = average * days
    note = f"trailing average of {len(rates)} period(s)"

    if strategy is EstimationStrategy.PROFILE and inputs.zone is not None:
        local_days = [
            (day, classify_day(day, inputs.holidays))
            for day, _ in span.local_days(inputs.zone)
        ]
        allocated = inputs.shape.allocate(total, local_days)
        total = dsum(allocated)
        note = f"{note}, shaped by {inputs.shape.code}"

    bag.emit(
        "meterdata.estimate.trailing_average",
        "usage was estimated from recent history",
        Severity.WARNING,
        subject,
        daily=str(average),
        days=str(days),
        strategy=strategy.value,
    )
    return Outcome(
        Consumption(
            span,
            Quantity(total, unit),
            QualityCode.ESTIMATED,
            source="estimate",
            note=note,
        ),
        bag,
    )
