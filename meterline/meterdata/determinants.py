"""Turning a service point's meter data into billing determinants.

This module is the seam between the two halves of the engine.  Everything
above it deals in dials, intervals and quality codes; everything below it
deals in named quantities and rates.  The policy decisions taken here — what
to do about a gap, whether suspect data may be billed, how a bucket split is
derived without an interval meter — are the ones that most often explain why
two systems produce different bills from identical meter records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from ..charge.determinant import DeterminantSet
from ..core.decimals import ZERO, D
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.outcome import Outcome
from ..core.quantity import Quantity
from ..core.units import Unit
from ..dataset import Dataset
from ..model.channel import ChannelKind
from ..model.quality import QualityCode, merge_quality
from ..model.series import IntervalSeries
from ..policy.conventions import GapPolicy, RatchetBasis, SuspectDataPolicy
from ..policy.profile import UtilityProfile
from ..tariff.model import Tariff
from ..timeline.calendars import MonthKey
from ..timeline.daycount import billing_days
from ..timeline.spans import Span
from .aggregate import bucket_totals, bucket_totals_from_consumption
from .consumption import Consumption, total_quantity
from .demand import DemandPeak, effective_window, peak_demand, ratchet_floor
from .derive import derive_consumption
from .estimate import EstimationInput, estimate_span
from .gaps import find_gaps, report_gaps
from .validate import apply_suspect_policy, validate_consumption

__all__ = ["MeterDataResult", "build_determinants"]

_HISTORY_DAYS = 400


@dataclass(slots=True)
class MeterDataResult:
    """Everything the meter-data layer produced for one period."""

    determinants: DeterminantSet = field(default_factory=DeterminantSet)
    consumption: tuple[Consumption, ...] = ()
    exported: tuple[Consumption, ...] = ()
    peak: DemandPeak | None = None
    quality: QualityCode = QualityCode.VALID
    estimated_spans: tuple[Span, ...] = ()
    held: bool = False
    """True when the suspect-data policy refuses to produce a bill."""

    @property
    def is_estimated(self) -> bool:
        """Return ``True`` when any part of the period was estimated."""

        return bool(self.estimated_spans)


def _channel_series(dataset: Dataset, meter_id: str, kind: ChannelKind) -> IntervalSeries | None:
    """Return the first interval series of a given kind on a meter."""

    meter = dataset.meter(meter_id)
    for channel in meter.channels:
        if channel.kind is kind:
            found = dataset.series.get(channel.channel_id)
            if found is not None:
                return found
    return None


def _history_for(
    dataset: Dataset, meter_id: str, register, span: Span, profile: UtilityProfile
) -> list[Consumption]:
    """Return prior consumption for estimation and validation."""

    window = Span(span.start - timedelta(days=_HISTORY_DAYS), span.start)
    reads = dataset.reads_around(meter_id, register.register_id, window)
    if len(reads) < 2:
        return []
    outcome = derive_consumption(
        register,
        reads,
        window,
        profile,
        changes=dataset.changes_of(meter_id, register.register_id),
    )
    return outcome.value


def _fill_gaps(
    span: Span,
    records: list[Consumption],
    unit: Unit,
    profile: UtilityProfile,
    history: Sequence[Consumption],
    dataset: Dataset,
    service_point_id: str,
    bag: DiagnosticBag,
) -> tuple[list[Consumption], list[Span], bool]:
    """Apply the gap policy, returning records, estimated spans and a hold."""

    tolerate_suspect = profile.suspect_data is SuspectDataPolicy.BILL_ANYWAY
    gaps = find_gaps(span, records, include_suspect=tolerate_suspect)
    if not gaps:
        return records, [], False
    bag.merge(report_gaps(gaps, service_point_id))
    policy = profile.gaps
    if policy is GapPolicy.FAIL:
        bag.emit(
            "meterdata.gap.fatal",
            "the policy refuses to bill a period with missing data",
            Severity.ERROR,
            service_point_id,
            gaps=len(gaps),
        )
        return records, [], True
    if policy is GapPolicy.EXCLUDE:
        bag.emit(
            "meterdata.gap.excluded",
            "the uncovered part of the period was cut out of the bill",
            Severity.NOTICE,
            service_point_id,
            gaps=len(gaps),
        )
        return records, [], False
    if policy is GapPolicy.ZERO_FILL:
        filled = list(records)
        for gap in gaps:
            filled.append(
                Consumption(
                    gap.span,
                    Quantity.zero(unit),
                    QualityCode.ESTIMATED,
                    source="zero-fill",
                    note="policy fills gaps with zero",
                )
            )
        bag.emit(
            "meterdata.gap.zero_filled",
            "missing data was billed as no usage",
            Severity.WARNING,
            service_point_id,
            gaps=len(gaps),
        )
        return filled, [gap.span for gap in gaps], False

    inputs = EstimationInput(
        tuple(history), dataset.zone_of(service_point_id), dataset.holidays
    )
    filled = list(records)
    estimated: list[Span] = []
    for gap in gaps:
        outcome = estimate_span(
            gap.span, unit, profile, inputs, subject=service_point_id
        )
        bag.merge(outcome.diagnostics)
        filled.append(outcome.value)
        estimated.append(gap.span)
    return filled, estimated, False


def _ratchet_history(
    dataset: Dataset, meter_id: str, month: MonthKey, profile: UtilityProfile
) -> dict[MonthKey, Decimal]:
    """Return the monthly demand peaks a ratchet may look back at."""

    series = _channel_series(dataset, meter_id, ChannelKind.DEMAND) or _channel_series(
        dataset, meter_id, ChannelKind.DELIVERED
    )
    if series is None:
        return {}
    zone = dataset.zone_of(dataset.meter(meter_id).service_point_id)
    history: dict[MonthKey, Decimal] = {}
    for offset in range(1, profile.ratchet_lookback_months + 1):
        key = month.shift(-offset)
        window = Span(zone.day_start(key.start()), zone.day_start(key.end() + timedelta(days=1)))
        overlap = window.intersection(series.span)
        if overlap is None:
            continue
        window, _ = effective_window(series, profile.demand_window_minutes)
        found = peak_demand(
            series, overlap, method=profile.demand_method, window_minutes=window
        )
        if not found.is_zero:
            history[key] = found.value
    return history


def build_determinants(
    dataset: Dataset,
    service_point_id: str,
    span: Span,
    cycle_span: Span,
    tariff: Tariff,
    profile: UtilityProfile,
) -> Outcome[MeterDataResult]:
    """Return the determinants a tariff needs for one period."""

    bag = DiagnosticBag()
    result = MeterDataResult()
    point = dataset.service_point(service_point_id)
    zone = dataset.zone_of(service_point_id)
    unit = tariff.energy_unit

    delivered: list[Consumption] = []
    exported: list[Consumption] = []
    reactive: list[Consumption] = []
    bucket_registers: dict[str, list[Consumption]] = {}
    history: list[Consumption] = []

    for meter in dataset.meters_of(service_point_id):
        if not meter.was_installed_during(span):
            continue
        for register in meter.registers:
            reads = dataset.reads_around(meter.meter_id, register.register_id, span)
            outcome = derive_consumption(
                register,
                reads,
                span,
                profile,
                changes=dataset.changes_of(meter.meter_id, register.register_id),
            )
            bag.merge(outcome.diagnostics)
            records = outcome.value
            if register.channel is ChannelKind.RECEIVED:
                exported.extend(records)
            elif register.channel is ChannelKind.REACTIVE:
                reactive.extend(records)
            elif register.is_tou:
                bucket_registers.setdefault(register.tou_bucket, []).extend(records)
                delivered.extend(records)
            else:
                delivered.extend(records)
                history.extend(
                    _history_for(dataset, meter.meter_id, register, span, profile)
                )

    validation = validate_consumption(
        span,
        delivered,
        profile,
        history=history,
        subject=service_point_id,
        series=_channel_series(dataset, point.meter_ids[0], ChannelKind.DELIVERED)
        if point.meter_ids
        else None,
    )
    bag.merge(validation)
    flagged = bool(validation.warnings)
    if flagged and profile.suspect_data is SuspectDataPolicy.HOLD:
        bag.emit(
            "meterdata.suspect.held",
            "the policy holds bills whose data failed validation",
            Severity.ERROR,
            service_point_id,
        )
        result.held = True
    elif flagged and profile.suspect_data is SuspectDataPolicy.ESTIMATE_INSTEAD:
        delivered = [
            record.with_quality(QualityCode.SUSPECT) for record in delivered
        ]
        bag.emit(
            "meterdata.suspect.re_estimated",
            "suspect measured data was discarded in favour of an estimate",
            Severity.WARNING,
            service_point_id,
        )
        delivered = []
    elif flagged:
        delivered = apply_suspect_policy(delivered, True, profile)

    delivered, estimated_spans, held = _fill_gaps(
        span, delivered, unit, profile, history, dataset, service_point_id, bag
    )
    result.held = result.held or held
    result.estimated_spans = tuple(estimated_spans)

    total = total_quantity(delivered, unit)
    quality = merge_quality(
        [(record.quality, record.quantity.value) for record in delivered],
        profile.quality_merge,
    )
    result.quality = quality
    result.consumption = tuple(sorted(delivered, key=lambda record: record.span.start))
    result.exported = tuple(sorted(exported, key=lambda record: record.span.start))

    determinants = DeterminantSet()
    determinants.put("energy.total", total, quality, "register")
    determinants.put(
        "days.served",
        Quantity(D(billing_days(span, zone, profile.day_count)), Unit.DAY),
        QualityCode.VALID,
        "calendar",
    )
    if exported:
        exported_total = total_quantity(exported, unit)
        determinants.put(
            "energy.exported",
            Quantity(abs(exported_total.value), unit),
            merge_quality(
                [(record.quality, record.quantity.value) for record in exported],
                profile.quality_merge,
            ),
            "register",
        )
    if reactive:
        determinants.put(
            "reactive.total",
            total_quantity(reactive, Unit.KVARH),
            QualityCode.VALID,
            "register",
        )

    if tariff.is_time_of_use and tariff.windows is not None:
        series = None
        for meter in dataset.meters_of(service_point_id):
            series = _channel_series(dataset, meter.meter_id, ChannelKind.DELIVERED)
            if series is not None:
                break
        if bucket_registers:
            for bucket in sorted(bucket_registers):
                determinants.put(
                    f"energy.bucket.{bucket}",
                    total_quantity(bucket_registers[bucket], unit),
                    quality,
                    "tou-register",
                )
        elif series is not None:
            totals = bucket_totals(
                series,
                span,
                zone,
                tariff.windows,
                seasons=tariff.seasons,
                holidays=dataset.holidays,
                day_rules=profile.day_types,
                precedence=profile.window_precedence,
            )
            for bucket in sorted(totals):
                determinants.put(
                    f"energy.bucket.{bucket}", totals[bucket], quality, "interval"
                )
        else:
            bag.emit(
                "meterdata.tou.no_interval_data",
                "buckets were split by hours because no interval data exists",
                Severity.WARNING,
                service_point_id,
                tariff=tariff.code,
            )
            totals = bucket_totals_from_consumption(
                delivered,
                span,
                zone,
                tariff.windows,
                unit,
                seasons=tariff.seasons,
                holidays=dataset.holidays,
                day_rules=profile.day_types,
                precedence=profile.window_precedence,
            )
            for bucket in sorted(totals):
                determinants.put(
                    f"energy.bucket.{bucket}",
                    totals[bucket],
                    QualityCode.ESTIMATED,
                    "hours-split",
                )

    if tariff.is_demand_billed:
        for meter in dataset.meters_of(service_point_id):
            series = _channel_series(
                dataset, meter.meter_id, ChannelKind.DEMAND
            ) or _channel_series(dataset, meter.meter_id, ChannelKind.DELIVERED)
            if series is None:
                continue
            window, note = effective_window(series, profile.demand_window_minutes)
            if note:
                bag.emit(
                    "meterdata.demand.window_widened",
                    "the demand window was widened to match the interval data",
                    Severity.NOTICE,
                    service_point_id,
                    detail=note,
                )
            found = peak_demand(
                series, span, method=profile.demand_method, window_minutes=window
            )
            if result.peak is None or found.value > result.peak.value:
                result.peak = found
        if result.peak is not None and not result.peak.is_zero:
            determinants.put(
                "demand.peak",
                result.peak.quantity,
                result.peak.quality,
                "interval",
                method=result.peak.method.value,
                window=result.peak.window_minutes,
            )
        else:
            bag.emit(
                "meterdata.demand.no_interval_data",
                "the tariff bills demand but no interval data was available",
                Severity.WARNING,
                service_point_id,
                tariff=tariff.code,
            )
        if profile.ratchet is not RatchetBasis.NONE and point.meter_ids:
            month = MonthKey.of(zone.local_date(span.end - timedelta(microseconds=1)))
            history_peaks = _ratchet_history(
                dataset, point.meter_ids[0], month, profile
            )
            floor = ratchet_floor(
                history_peaks,
                month,
                basis=profile.ratchet,
                lookback_months=profile.ratchet_lookback_months,
            )
            if floor > ZERO:
                determinants.put(
                    "demand.ratchet_floor",
                    Quantity(floor, Unit.KW),
                    QualityCode.VALID,
                    "history",
                    months=len(history_peaks),
                )

    result.determinants = determinants
    return Outcome(result, bag)
