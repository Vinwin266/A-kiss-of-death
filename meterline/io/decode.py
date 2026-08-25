"""Building a dataset from a decoded document."""

from __future__ import annotations

from typing import Any, Mapping

from ..charge.basis import Basis
from ..charge.classes import ChargeClass
from ..core.decimals import D
from ..core.units import Unit
from ..dataset import Dataset
from ..errors import SchemaError
from ..model.account import Account, AccountStatus
from ..model.channel import ChannelKind, ChannelSpec
from ..model.enrollment import EnrollmentHistory, TariffEnrollment
from ..model.meter import Meter, MeterKind
from ..model.premise import Premise
from ..model.quality import QualityCode, ReadType
from ..model.reading import MeterRead, RegisterChange
from ..model.register import Register
from ..model.series import IntervalSeries
from ..model.service_point import ServiceKind, ServicePoint
from ..policy.resolve import profile_from_dict
from ..tariff.catalog import TariffCatalog
from ..tariff.loader import tariff_from_dict
from ..tariff.schedule import TariffSchedule, TariffVersion
from ..tax.exemption import Exemption, ExemptionSet
from ..tax.jurisdiction import Jurisdiction, JurisdictionSet
from ..tax.model import TaxKind, TaxRule
from ..timeline.calendars import MonthKey
from ..timeline.cycles import CycleSchedule, ReadDayShift
from ..timeline.holidays import ObservedRule, us_federal_calendar
from ..timeline.instants import parse_instant
from ..timeline.zones import ZoneRegistry
from .schema import require_keys, take_list, take_map, take_str

__all__ = ["dataset_from_dict"]


def _optional_instant(raw: Mapping[str, Any], key: str):  # noqa: ANN201
    """Return a parsed instant, or ``None`` when the key is absent."""

    value = raw.get(key)
    return parse_instant(str(value), what=key) if value else None


def _premises(document: Mapping[str, Any]) -> dict[str, Premise]:
    """Decode the premise records."""

    result: dict[str, Premise] = {}
    for index, raw in enumerate(take_list(document, "premises")):
        require_keys(raw, ["premise_id"], context=f"premises[{index}]")
        premise = Premise(
            take_str(raw, "premise_id"),
            take_str(raw, "address", default=""),
            take_str(raw, "locality", default=""),
            take_str(raw, "region", default=""),
            take_str(raw, "postcode", default=""),
            take_str(raw, "jurisdiction", default=""),
            take_str(raw, "climate_zone", default=""),
        )
        result[premise.premise_id] = premise
    return result


def _accounts(document: Mapping[str, Any]) -> dict[str, Account]:
    """Decode the account records."""

    result: dict[str, Account] = {}
    for index, raw in enumerate(take_list(document, "accounts")):
        require_keys(raw, ["account_id"], context=f"accounts[{index}]")
        account = Account(
            take_str(raw, "account_id"),
            take_str(raw, "name", default=""),
            take_str(raw, "currency", default="USD"),
            AccountStatus(take_str(raw, "status", default="active")),
            tuple(raw.get("service_point_ids", ())),
            take_str(raw, "assistance_program", default=""),
            take_str(raw, "budget_plan_id", default=""),
            tuple(raw.get("tax_exemption_codes", ())),
            take_str(raw, "mailing_premise_id", default=""),
        )
        result[account.account_id] = account
    return result


def _service_points(document: Mapping[str, Any]) -> dict[str, ServicePoint]:
    """Decode the service point records."""

    result: dict[str, ServicePoint] = {}
    for index, raw in enumerate(take_list(document, "service_points")):
        context = f"service_points[{index}]"
        require_keys(raw, ["service_point_id", "account_id", "zone"], context=context)
        point = ServicePoint(
            take_str(raw, "service_point_id"),
            take_str(raw, "account_id"),
            take_str(raw, "premise_id", default=""),
            take_str(raw, "zone"),
            ServiceKind(take_str(raw, "kind", default="residential")),
            take_str(raw, "route", default=""),
            tuple(raw.get("meter_ids", ())),
            _optional_instant(raw, "connected_at"),
            _optional_instant(raw, "disconnected_at"),
            take_str(raw, "voltage_level", default="secondary"),
            bool(raw.get("has_generation", False)),
            str(raw.get("generation_capacity_kw", "0")),
            take_str(raw, "label", default=""),
        )
        result[point.service_point_id] = point
    return result


def _registers(raw: Mapping[str, Any], meter_id: str) -> tuple[Register, ...]:
    """Decode a meter's registers."""

    registers: list[Register] = []
    for index, entry in enumerate(take_list(raw, "registers")):
        require_keys(entry, ["register_id", "unit"], context=f"{meter_id}.registers[{index}]")
        registers.append(
            Register(
                take_str(entry, "register_id"),
                meter_id,
                Unit(take_str(entry, "unit")),
                int(entry.get("digits", 5)),
                str(entry.get("multiplier", "1")),
                ChannelKind(take_str(entry, "channel", default="delivered")),
                take_str(entry, "tou_bucket", default=""),
                take_str(entry, "label", default=""),
                int(entry.get("decimals", 0)),
            )
        )
    return tuple(registers)


def _channels(raw: Mapping[str, Any], meter_id: str) -> tuple[ChannelSpec, ...]:
    """Decode a meter's interval channels."""

    channels: list[ChannelSpec] = []
    for index, entry in enumerate(take_list(raw, "channels")):
        require_keys(entry, ["channel_id", "unit"], context=f"{meter_id}.channels[{index}]")
        channels.append(
            ChannelSpec(
                take_str(entry, "channel_id"),
                meter_id,
                ChannelKind(take_str(entry, "kind", default="delivered")),
                Unit(take_str(entry, "unit")),
                int(entry.get("interval_minutes", 15)),
                str(entry.get("multiplier", "1")),
                take_str(entry, "label", default=""),
            )
        )
    return tuple(channels)


def _meters(document: Mapping[str, Any]) -> dict[str, Meter]:
    """Decode the meter records."""

    result: dict[str, Meter] = {}
    for index, raw in enumerate(take_list(document, "meters")):
        context = f"meters[{index}]"
        require_keys(raw, ["meter_id", "service_point_id"], context=context)
        meter_id = take_str(raw, "meter_id")
        meter = Meter(
            meter_id,
            take_str(raw, "service_point_id"),
            MeterKind(take_str(raw, "kind", default="electric")),
            _registers(raw, meter_id),
            _channels(raw, meter_id),
            take_str(raw, "serial", default=""),
            _optional_instant(raw, "installed_at"),
            _optional_instant(raw, "removed_at"),
        )
        result[meter_id] = meter
    return result


def _reads(document: Mapping[str, Any]) -> tuple[MeterRead, ...]:
    """Decode the meter reads."""

    reads: list[MeterRead] = []
    for index, raw in enumerate(take_list(document, "reads")):
        context = f"reads[{index}]"
        require_keys(raw, ["meter_id", "register_id", "at", "value"], context=context)
        reads.append(
            MeterRead.build(
                take_str(raw, "meter_id"),
                take_str(raw, "register_id"),
                parse_instant(take_str(raw, "at")),
                str(raw["value"]),
                ReadType(take_str(raw, "read_type", default="actual")),
                QualityCode(take_str(raw, "quality", default="valid")),
                take_str(raw, "source", default=""),
                take_str(raw, "note", default=""),
            )
        )
    return tuple(sorted(reads, key=lambda read: read.key))


def _changes(document: Mapping[str, Any]) -> tuple[RegisterChange, ...]:
    """Decode the register change events."""

    changes: list[RegisterChange] = []
    for index, raw in enumerate(take_list(document, "register_changes")):
        context = f"register_changes[{index}]"
        require_keys(
            raw,
            ["meter_id", "register_id", "at", "final_value", "initial_value"],
            context=context,
        )
        changes.append(
            RegisterChange.build(
                take_str(raw, "meter_id"),
                take_str(raw, "register_id"),
                parse_instant(take_str(raw, "at")),
                str(raw["final_value"]),
                str(raw["initial_value"]),
                take_str(raw, "reason", default="exchange"),
                take_str(raw, "new_register_id", default=""),
            )
        )
    return tuple(changes)


def _series(document: Mapping[str, Any]) -> dict[str, IntervalSeries]:
    """Decode the interval series."""

    result: dict[str, IntervalSeries] = {}
    for index, raw in enumerate(take_list(document, "series")):
        context = f"series[{index}]"
        require_keys(raw, ["channel_id", "start", "values"], context=context)
        values = [None if value is None else str(value) for value in raw["values"]]
        qualities = tuple(
            QualityCode(code) for code in raw.get("qualities", ())
        )
        series = IntervalSeries(
            take_str(raw, "channel_id"),
            parse_instant(take_str(raw, "start")),
            int(raw.get("interval_minutes", 15)),
            tuple(values),
            Unit(take_str(raw, "unit", default="kWh")),
            qualities,
        )
        result[series.channel_id] = series
    return result


def _enrollments(document: Mapping[str, Any]) -> dict[str, EnrollmentHistory]:
    """Decode the tariff enrolments."""

    grouped: dict[str, list[TariffEnrollment]] = {}
    for index, raw in enumerate(take_list(document, "enrollments")):
        context = f"enrollments[{index}]"
        require_keys(raw, ["service_point_id", "tariff", "from"], context=context)
        point_id = take_str(raw, "service_point_id")
        grouped.setdefault(point_id, []).append(
            TariffEnrollment(
                point_id,
                take_str(raw, "tariff"),
                parse_instant(take_str(raw, "from")),
                _optional_instant(raw, "to"),
                take_str(raw, "reason", default=""),
            )
        )
    return {
        point_id: EnrollmentHistory.of(point_id, entries)
        for point_id, entries in grouped.items()
    }


def _catalog(document: Mapping[str, Any]) -> TariffCatalog:
    """Decode the tariff catalog, including dated versions."""

    grouped: dict[str, list[TariffVersion]] = {}
    for index, raw in enumerate(take_list(document, "tariffs")):
        context = f"tariffs[{index}]"
        require_keys(raw, ["code", "effective_from"], context=context)
        tariff = tariff_from_dict(raw)
        version = TariffVersion(
            str(raw.get("version", "1")),
            parse_instant(take_str(raw, "effective_from")),
            tariff,
            _optional_instant(raw, "effective_to"),
            take_str(raw, "order_reference", default=""),
        )
        grouped.setdefault(tariff.code, []).append(version)
    return TariffCatalog.of(
        TariffSchedule.of(code, versions) for code, versions in grouped.items()
    )


def _tax_rule(raw: Mapping[str, Any], jurisdiction: str, index: int) -> TaxRule:
    """Decode one tax rule."""

    context = f"jurisdictions[{jurisdiction}].rules[{index}]"
    require_keys(raw, ["code", "kind", "rate"], context=context)
    return TaxRule(
        take_str(raw, "code"),
        take_str(raw, "label", default=take_str(raw, "code")),
        TaxKind(take_str(raw, "kind")),
        str(raw["rate"]),
        jurisdiction,
        Basis(take_str(raw, "basis", default="subtotal")),
        take_str(raw, "determinant", default="energy.total"),
        Unit(take_str(raw, "unit", default="kWh")),
        int(raw.get("order", 0)),
        tuple(ChargeClass(value) for value in raw.get("exempt_classes", ())),
        take_str(raw, "exemption_code", default=""),
    )


def _jurisdictions(document: Mapping[str, Any]) -> JurisdictionSet:
    """Decode the tax jurisdictions."""

    result = JurisdictionSet()
    for index, raw in enumerate(take_list(document, "jurisdictions")):
        require_keys(raw, ["code"], context=f"jurisdictions[{index}]")
        code = take_str(raw, "code")
        rules = tuple(
            _tax_rule(entry, code, position)
            for position, entry in enumerate(take_list(raw, "rules"))
        )
        result.add(
            Jurisdiction(
                code,
                take_str(raw, "label", default=""),
                take_str(raw, "parent", default=""),
                rules,
            )
        )
    return result


def _exemptions(document: Mapping[str, Any]) -> ExemptionSet:
    """Decode the tax exemptions."""

    result = ExemptionSet()
    for index, raw in enumerate(take_list(document, "exemptions")):
        require_keys(raw, ["code", "tax_code"], context=f"exemptions[{index}]")
        result.add(
            Exemption(
                take_str(raw, "code"),
                take_str(raw, "tax_code"),
                D(str(raw.get("percent", "100"))),
                take_str(raw, "label", default=""),
                D(str(raw.get("cap", "0"))),
            )
        )
    return result


def _cycles(document: Mapping[str, Any], dataset: Dataset) -> None:
    """Generate billing cycles from the declared read schedules."""

    for index, raw in enumerate(take_list(document, "cycle_schedules")):
        context = f"cycle_schedules[{index}]"
        require_keys(
            raw, ["service_point_id", "read_day", "first_month", "count"], context=context
        )
        point_id = take_str(raw, "service_point_id")
        point = dataset.service_point(point_id)
        schedule = CycleSchedule(
            take_str(raw, "route", default=point.route),
            int(raw["read_day"]),
            dataset.zones.get(point.zone_name),
            ReadDayShift(take_str(raw, "shift", default="none")),
            dataset.holidays,
        )
        dataset.cycles[point_id] = tuple(
            schedule.cycles(
                point_id,
                MonthKey.parse(take_str(raw, "first_month")),
                int(raw["count"]),
            )
        )


def dataset_from_dict(document: Mapping[str, Any]) -> Dataset:
    """Build a :class:`~meterline.dataset.Dataset` from a decoded document."""

    if not isinstance(document, dict):
        raise SchemaError("a dataset must be a JSON object", found=type(document).__name__)
    dataset = Dataset(
        name=take_str(document, "name", default="dataset"),
        profile=profile_from_dict(take_map(document, "profile")),
        catalog=_catalog(document),
        zones=ZoneRegistry(),
        accounts=_accounts(document),
        premises=_premises(document),
        service_points=_service_points(document),
        meters=_meters(document),
        reads=_reads(document),
        changes=_changes(document),
        series=_series(document),
        enrollments=_enrollments(document),
        jurisdictions=_jurisdictions(document),
        exemptions=_exemptions(document),
        holidays=us_federal_calendar(
            ObservedRule(take_str(document, "observed_rule", default="nearest_weekday"))
        ),
    )
    _cycles(document, dataset)
    return dataset
