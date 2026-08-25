"""Builders for the small datasets the tests rate.

Every test dataset is assembled in memory through the same model classes the
JSON loader produces, so a test never exercises a path the CLI does not.
The helpers here are deliberately explicit rather than clever: a fixture
that hides which read closed which cycle is a fixture that cannot be used to
diagnose an off-by-one.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

from meterline.core.units import Unit
from meterline.dataset import Dataset
from meterline.model.account import Account
from meterline.model.channel import ChannelKind, ChannelSpec
from meterline.model.enrollment import EnrollmentHistory, TariffEnrollment
from meterline.model.meter import Meter, MeterKind
from meterline.model.premise import Premise
from meterline.model.quality import QualityCode, ReadType
from meterline.model.reading import MeterRead
from meterline.model.register import Register
from meterline.model.series import IntervalSeries
from meterline.model.service_point import ServiceKind, ServicePoint
from meterline.policy.presets import preset
from meterline.policy.profile import UtilityProfile
from meterline.tariff.catalog import TariffCatalog
from meterline.tariff.components.base import Component
from meterline.tariff.components.blocks import Block
from meterline.tariff.components.credit import ExportCredit
from meterline.tariff.components.demand import DemandCharge
from meterline.tariff.components.fixed import FixedCharge
from meterline.tariff.components.minimum import MinimumCharge
from meterline.tariff.components.tiered import TieredCharge
from meterline.tariff.components.tou import TouCharge
from meterline.tariff.model import Tariff
from meterline.tariff.seasons import Season, SeasonSet
from meterline.tariff.windows import TimeWindow, WindowSet
from meterline.timeline.calendars import MonthKey
from meterline.timeline.cycles import BillingCycle, CycleSchedule
from meterline.timeline.daytypes import DayType
from meterline.timeline.spans import Span
from meterline.timeline.zones import Zone, common_zone

ZONE_NAME = "America/New_York"


def zone() -> Zone:
    """Return the zone every test dataset uses."""

    return common_zone(ZONE_NAME)


def cycles_for(
    service_point_id: str = "sp-1",
    read_day: int = 15,
    first_month: MonthKey | None = None,
    count: int = 3,
) -> list[BillingCycle]:
    """Return a run of consecutive billing cycles."""

    schedule = CycleSchedule("R1", read_day, zone())
    return schedule.cycles(
        service_point_id, first_month or MonthKey(2025, 4), count
    )


def boundaries(cycles: Sequence[BillingCycle]) -> list[datetime]:
    """Return the instants that open and close a run of cycles."""

    return [cycles[0].span.start] + [cycle.span.end for cycle in cycles]


def reads_from_steps(
    meter_id: str,
    register_id: str,
    moments: Sequence[datetime],
    start_value: int,
    steps: Sequence[int],
    *,
    read_type: ReadType = ReadType.ACTUAL,
    quality: QualityCode = QualityCode.VALID,
) -> list[MeterRead]:
    """Return dial readings implied by a start value and per-period usage."""

    reads: list[MeterRead] = []
    value = start_value
    for index, moment in enumerate(moments):
        reads.append(
            MeterRead.build(
                meter_id,
                register_id,
                moment,
                Decimal(value),
                read_type if index else ReadType.ACTUAL,
                quality if index else QualityCode.VALID,
                source="test",
            )
        )
        if index < len(steps):
            value += steps[index]
    return reads


def residential_tariff(
    code: str = "RES",
    *,
    with_minimum: bool = True,
    first_block_rate: str = "0.10",
    extra: Sequence[Component] = (),
) -> Tariff:
    """Return a simple two-block residential tariff."""

    components: list[Component] = [
        FixedCharge("basic", "Basic service charge", "12.00"),
        TieredCharge(
            "energy",
            "Energy charge",
            [
                Block.of(500, first_block_rate, "first 500 kWh"),
                Block.of(None, "0.15", "over 500 kWh"),
            ],
        ),
    ]
    if with_minimum:
        components.append(MinimumCharge("minimum", "Minimum charge", "20.00"))
    components.extend(extra)
    return Tariff(code, "Residential Service", tuple(components))


def solar_tariff(code: str = "NEM") -> Tariff:
    """Return a residential tariff that credits exported energy."""

    return Tariff(
        code,
        "Residential Net Metering",
        (
            FixedCharge("basic", "Basic service charge", "15.00"),
            TieredCharge(
                "energy",
                "Energy charge",
                [Block.of(None, "0.12", "all usage")],
            ),
            ExportCredit(
                "export",
                "Export credit",
                retail_rate="0.12",
                avoided_cost_rate="0.04",
            ),
        ),
    )


def tou_tariff(code: str = "TOU") -> Tariff:
    """Return a time-of-use tariff with a demand charge."""

    windows = WindowSet(
        (
            TimeWindow.between("peak", "14:00", "19:00", (DayType.WEEKDAY,)),
            TimeWindow.between("shoulder", "07:00", "22:00", (DayType.WEEKDAY,)),
        ),
        "offpeak",
    )
    seasons = SeasonSet(
        (
            Season("summer", 6, 1, 9, 30),
            Season("winter", 10, 1, 5, 31),
        )
    )
    return Tariff(
        code,
        "General Service — Time of Use",
        (
            FixedCharge("customer", "Customer charge", "1.50", per="day"),
            TouCharge(
                "energy",
                "Energy charge",
                {"peak": "0.20", "shoulder": "0.11", "offpeak": "0.07"},
            ),
            DemandCharge("demand", "Demand charge", "12.00"),
        ),
        windows=windows,
        seasons=seasons,
        service_kinds=(ServiceKind.SMALL_COMMERCIAL,),
    )


def build_dataset(
    *,
    tariff: Tariff | None = None,
    profile: UtilityProfile | None = None,
    steps: Sequence[int] = (450, 620, 380),
    read_day: int = 15,
    kind: ServiceKind = ServiceKind.RESIDENTIAL,
    jurisdiction: str = "",
    assistance: str = "",
    export_steps: Sequence[int] | None = None,
    connected_at: datetime | None = None,
    disconnected_at: datetime | None = None,
) -> Dataset:
    """Assemble a one-customer dataset with the given usage."""

    active_tariff = tariff or residential_tariff()
    cycles = cycles_for(count=len(steps), read_day=read_day)
    marks = boundaries(cycles)

    registers = [Register("rg-1", "mt-1", Unit.KWH, digits=5)]
    if export_steps is not None:
        registers.append(
            Register("rg-2", "mt-1", Unit.KWH, digits=5, channel=ChannelKind.RECEIVED)
        )

    dataset = Dataset(
        name="test",
        profile=profile or preset("model-rules"),
        catalog=TariffCatalog.single_version([active_tariff], marks[0]),
    )
    dataset.premises["pm-1"] = Premise("pm-1", "1 Test Row", jurisdiction=jurisdiction)
    dataset.accounts["ac-1"] = Account(
        "ac-1",
        "Test Customer",
        "USD",
        service_point_ids=("sp-1",),
        assistance_program=assistance,
    )
    dataset.service_points["sp-1"] = ServicePoint(
        "sp-1",
        "ac-1",
        "pm-1",
        ZONE_NAME,
        kind,
        route="R1",
        meter_ids=("mt-1",),
        connected_at=connected_at,
        disconnected_at=disconnected_at,
        has_generation=export_steps is not None,
    )
    dataset.meters["mt-1"] = Meter(
        "mt-1", "sp-1", MeterKind.ELECTRIC, tuple(registers), serial="TEST-1"
    )
    reads = reads_from_steps("mt-1", "rg-1", marks, 10000, steps)
    if export_steps is not None:
        reads += reads_from_steps("mt-1", "rg-2", marks, 500, export_steps)
    dataset.add_reads(reads)
    dataset.enrollments["sp-1"] = EnrollmentHistory.of(
        "sp-1", [TariffEnrollment("sp-1", active_tariff.code, marks[0])]
    )
    dataset.cycles["sp-1"] = tuple(cycles)
    return dataset


def flat_series(
    channel_id: str,
    start: datetime,
    hours: int,
    per_hour: str = "2.5",
    *,
    interval_minutes: int = 60,
    unit: Unit = Unit.KWH,
) -> IntervalSeries:
    """Return an interval series with a constant value in every interval."""

    count = hours * 60 // interval_minutes
    return IntervalSeries(
        channel_id,
        start,
        interval_minutes,
        tuple(Decimal(per_hour) for _ in range(count)),
        unit,
    )


def shaped_series(
    channel_id: str,
    start: datetime,
    hours: int,
    shape: Sequence[str],
    *,
    interval_minutes: int = 60,
) -> IntervalSeries:
    """Return an interval series repeating an hourly shape."""

    count = hours * 60 // interval_minutes
    per_hour = 60 // interval_minutes
    values = [Decimal(shape[(index // per_hour) % len(shape)]) for index in range(count)]
    return IntervalSeries(channel_id, start, interval_minutes, tuple(values))


def attach_channel(
    dataset: Dataset,
    series: IntervalSeries,
    *,
    meter_id: str = "mt-1",
    kind: ChannelKind = ChannelKind.DELIVERED,
) -> None:
    """Attach an interval channel and its series to an existing meter."""

    meter = dataset.meters[meter_id]
    channel = ChannelSpec(
        series.channel_id, meter_id, kind, series.unit, series.interval_minutes
    )
    dataset.meters[meter_id] = Meter(
        meter.meter_id,
        meter.service_point_id,
        meter.kind,
        meter.registers,
        meter.channels + (channel,),
        meter.serial,
        meter.installed_at,
        meter.removed_at,
    )
    dataset.add_series(series)


def span_of_days(start: datetime, days: int) -> Span:
    """Return a span of whole days from ``start``."""

    return Span(start, start + timedelta(days=days))
