"""The dataset: everything one run of the engine reads.

A dataset is a closed world.  Loading one and rating from it must not touch
the filesystem, the network or the clock, because that is what makes a run
reproducible; the loader in :mod:`meterline.io` is the only place a file is
opened, and it produces one of these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .core.diagnostics import DiagnosticBag, Severity
from .errors import UnknownReferenceError
from .model.account import Account
from .model.enrollment import EnrollmentHistory
from .model.meter import Meter
from .model.premise import Premise
from .model.reading import MeterRead, RegisterChange
from .model.series import IntervalSeries
from .model.service_point import ServicePoint
from .policy.profile import UtilityProfile
from .tariff.catalog import TariffCatalog
from .tax.exemption import ExemptionSet
from .tax.jurisdiction import JurisdictionSet
from .timeline.cycles import BillingCycle
from .timeline.holidays import HolidayCalendar, us_federal_calendar
from .timeline.spans import Span
from .timeline.zones import Zone, ZoneRegistry

__all__ = ["Dataset"]


@dataclass(slots=True)
class Dataset:
    """Every record the engine can read, indexed for lookup."""

    name: str = "dataset"
    profile: UtilityProfile = field(default_factory=UtilityProfile)
    catalog: TariffCatalog = field(default_factory=TariffCatalog)
    zones: ZoneRegistry = field(default_factory=ZoneRegistry)
    accounts: dict[str, Account] = field(default_factory=dict)
    premises: dict[str, Premise] = field(default_factory=dict)
    service_points: dict[str, ServicePoint] = field(default_factory=dict)
    meters: dict[str, Meter] = field(default_factory=dict)
    reads: tuple[MeterRead, ...] = ()
    changes: tuple[RegisterChange, ...] = ()
    series: dict[str, IntervalSeries] = field(default_factory=dict)
    enrollments: dict[str, EnrollmentHistory] = field(default_factory=dict)
    cycles: dict[str, tuple[BillingCycle, ...]] = field(default_factory=dict)
    jurisdictions: JurisdictionSet = field(default_factory=JurisdictionSet)
    exemptions: ExemptionSet = field(default_factory=ExemptionSet)
    holidays: HolidayCalendar = field(default_factory=us_federal_calendar)

    # -- lookups --------------------------------------------------------

    def account(self, account_id: str) -> Account:
        """Return an account by identifier."""

        try:
            return self.accounts[account_id]
        except KeyError:
            raise UnknownReferenceError(
                "no such account", kind="account", identifier=account_id
            ) from None

    def service_point(self, service_point_id: str) -> ServicePoint:
        """Return a service point by identifier."""

        try:
            return self.service_points[service_point_id]
        except KeyError:
            raise UnknownReferenceError(
                "no such service point",
                kind="service_point",
                identifier=service_point_id,
            ) from None

    def meter(self, meter_id: str) -> Meter:
        """Return a meter by identifier."""

        try:
            return self.meters[meter_id]
        except KeyError:
            raise UnknownReferenceError(
                "no such meter", kind="meter", identifier=meter_id
            ) from None

    def premise(self, premise_id: str) -> Premise:
        """Return a premise by identifier."""

        try:
            return self.premises[premise_id]
        except KeyError:
            raise UnknownReferenceError(
                "no such premise", kind="premise", identifier=premise_id
            ) from None

    def zone_of(self, service_point_id: str) -> Zone:
        """Return the timezone of a service point."""

        return self.zones.get(self.service_point(service_point_id).zone_name)

    def enrollment(self, service_point_id: str) -> EnrollmentHistory:
        """Return the tariff enrolment history of a service point."""

        found = self.enrollments.get(service_point_id)
        if found is None:
            raise UnknownReferenceError(
                "no tariff enrolment for this service point",
                kind="enrollment",
                identifier=service_point_id,
            )
        return found

    # -- collections ----------------------------------------------------

    def meters_of(self, service_point_id: str) -> list[Meter]:
        """Return the meters installed at a service point, sorted."""

        return [
            self.meters[meter_id]
            for meter_id in sorted(self.meters)
            if self.meters[meter_id].service_point_id == service_point_id
        ]

    def reads_of(
        self, meter_id: str, register_id: str = "", span: Span | None = None
    ) -> list[MeterRead]:
        """Return the reads of a meter, optionally narrowed."""

        found = [read for read in self.reads if read.meter_id == meter_id]
        if register_id:
            found = [read for read in found if read.register_id == register_id]
        if span is not None:
            found = [read for read in found if span.contains(read.at)]
        return sorted(found, key=lambda read: read.key)

    def reads_around(
        self, meter_id: str, register_id: str, span: Span
    ) -> list[MeterRead]:
        """Return the reads of a register inside ``span`` plus its neighbours.

        Deriving consumption for a cycle needs the read that closed the
        previous cycle, which by definition sits outside the span; fetching
        it here keeps that off-by-one out of the derivation code.
        """

        series = [
            read
            for read in self.reads
            if read.meter_id == meter_id and read.register_id == register_id
        ]
        series.sort(key=lambda read: read.at)
        inside = [read for read in series if span.contains(read.at)]
        before = [read for read in series if read.at <= span.start]
        after = [read for read in series if read.at >= span.end]
        result = list(inside)
        if before:
            result.insert(0, before[-1])
        if after:
            result.append(after[0])
        return sorted(set(result), key=lambda read: (read.at, read.read_id))

    def changes_of(self, meter_id: str, register_id: str = "") -> list[RegisterChange]:
        """Return the register changes of a meter, sorted."""

        found = [change for change in self.changes if change.meter_id == meter_id]
        if register_id:
            found = [change for change in found if change.register_id == register_id]
        return sorted(found, key=lambda change: (change.at, change.change_id))

    def series_of(self, meter_id: str) -> list[IntervalSeries]:
        """Return the interval series belonging to a meter's channels."""

        meter = self.meter(meter_id)
        channel_ids = {channel.channel_id for channel in meter.channels}
        return [
            self.series[channel_id]
            for channel_id in sorted(self.series)
            if channel_id in channel_ids
        ]

    def cycles_of(self, service_point_id: str) -> tuple[BillingCycle, ...]:
        """Return the billing cycles of a service point."""

        return self.cycles.get(service_point_id, ())

    def cycle_containing(
        self, service_point_id: str, moment: datetime
    ) -> BillingCycle | None:
        """Return the cycle containing an instant, if any."""

        for cycle in self.cycles_of(service_point_id):
            if cycle.contains(moment):
                return cycle
        return None

    # -- mutation -------------------------------------------------------

    def add_reads(self, reads: Iterable[MeterRead]) -> None:
        """Add reads, keeping the collection sorted and unique."""

        merged = {read.read_id: read for read in self.reads}
        for read in reads:
            merged[read.read_id] = read
        self.reads = tuple(sorted(merged.values(), key=lambda read: read.key))

    def add_series(self, series: IntervalSeries) -> None:
        """Add or replace an interval series."""

        self.series[series.channel_id] = series

    # -- summary --------------------------------------------------------

    def counts(self) -> dict[str, int]:
        """Return the record counts, for the ``validate`` command."""

        return {
            "accounts": len(self.accounts),
            "premises": len(self.premises),
            "service_points": len(self.service_points),
            "meters": len(self.meters),
            "reads": len(self.reads),
            "register_changes": len(self.changes),
            "interval_series": len(self.series),
            "tariffs": len(self.catalog),
            "jurisdictions": len(self.jurisdictions.codes()),
        }

    def check_references(self) -> DiagnosticBag:
        """Report records pointing at identifiers that do not exist."""

        bag = DiagnosticBag()
        for point_id in sorted(self.service_points):
            point = self.service_points[point_id]
            if point.account_id not in self.accounts:
                bag.emit(
                    "dataset.missing_account",
                    "a service point names an account that is not in the dataset",
                    Severity.ERROR,
                    point_id,
                    account=point.account_id,
                )
            if point.premise_id and point.premise_id not in self.premises:
                bag.emit(
                    "dataset.missing_premise",
                    "a service point names a premise that is not in the dataset",
                    Severity.ERROR,
                    point_id,
                    premise=point.premise_id,
                )
            if point.zone_name not in self.zones.zones:
                bag.emit(
                    "dataset.unknown_zone",
                    "a service point names an unknown timezone",
                    Severity.ERROR,
                    point_id,
                    zone=point.zone_name,
                )
            if point_id not in self.enrollments:
                bag.emit(
                    "dataset.no_enrollment",
                    "a service point has no tariff enrolment",
                    Severity.WARNING,
                    point_id,
                )
        for meter_id in sorted(self.meters):
            meter = self.meters[meter_id]
            if meter.service_point_id not in self.service_points:
                bag.emit(
                    "dataset.missing_service_point",
                    "a meter names a service point that is not in the dataset",
                    Severity.ERROR,
                    meter_id,
                    service_point=meter.service_point_id,
                )
        known_meters = set(self.meters)
        for read in self.reads:
            if read.meter_id not in known_meters:
                bag.emit(
                    "dataset.orphan_read",
                    "a meter read names a meter that is not in the dataset",
                    Severity.ERROR,
                    read.read_id,
                    meter=read.meter_id,
                )
        known_jurisdictions = set(self.jurisdictions.codes())
        for premise_id in sorted(self.premises):
            code = self.premises[premise_id].jurisdiction
            if code and code not in known_jurisdictions:
                bag.emit(
                    "dataset.unknown_jurisdiction",
                    "a premise names a jurisdiction that is not in the dataset",
                    Severity.ERROR,
                    premise_id,
                    jurisdiction=code,
                )
        for point_id in sorted(self.enrollments):
            for code in self.enrollments[point_id].codes():
                if code not in self.catalog:
                    bag.emit(
                        "dataset.unknown_tariff",
                        "an enrolment names a tariff that is not in the catalog",
                        Severity.ERROR,
                        point_id,
                        tariff=code,
                    )
        return bag
