"""Building tariffs from plain data.

The registry is explicit: a document naming a component kind the engine does
not know fails loudly with the list of kinds it does know, rather than being
skipped and producing a bill that is quietly missing a charge.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ..charge.basis import Basis
from ..charge.classes import ChargeClass, ChargeSide
from ..core.units import Unit
from ..errors import TariffError, UnknownComponentError
from ..model.service_point import ServiceKind
from ..policy.conventions import WindowPrecedence
from ..timeline.daytypes import DayType
from .components.base import Component, Stage
from .components.blocks import Block
from .components.credit import ExportCredit
from .components.demand import DemandCharge
from .components.discount import AssistanceDiscount
from .components.fixed import FixedCharge
from .components.minimum import MinimumCharge
from .components.reactive import PowerFactorCharge
from .components.rider import Rider, RiderKind
from .components.step import SteppedCharge
from .components.tiered import TieredCharge
from .components.tou import TouCharge
from .model import Tariff
from .seasons import Season, SeasonSet
from .windows import TimeWindow, WindowSet

__all__ = ["tariff_from_dict", "component_from_dict", "COMPONENT_KINDS"]


def _blocks(raw: Sequence[Mapping[str, Any]], component: str) -> list[Block]:
    """Build a block list from raw data."""

    if not raw:
        raise TariffError("a block schedule needs blocks", component=component)
    return [
        Block.of(entry.get("limit"), entry["rate"], str(entry.get("label", "")))
        for entry in raw
    ]


def _side(raw: Mapping[str, Any], default: ChargeSide) -> ChargeSide:
    """Read an optional charge side."""

    value = raw.get("side")
    return ChargeSide(value) if value else default


def _unit(raw: Mapping[str, Any], default: Unit) -> Unit:
    """Read an optional unit."""

    value = raw.get("unit")
    return Unit(value) if value else default


def _stage(raw: Mapping[str, Any], default: int) -> int:
    """Read an optional stage override."""

    return int(raw.get("stage", default))


def _fixed(raw: Mapping[str, Any]) -> Component:
    return FixedCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        raw["amount"],
        per=str(raw.get("per", "month")),
        side=_side(raw, ChargeSide.DELIVERY),
        stage=_stage(raw, Stage.FIXED),
        taxable=bool(raw.get("taxable", True)),
    )


def _tiered(raw: Mapping[str, Any]) -> Component:
    return TieredCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        _blocks(raw.get("blocks", ()), raw["code"]),
        determinant=str(raw.get("determinant", "energy.total")),
        unit=_unit(raw, Unit.KWH),
        side=_side(raw, ChargeSide.SUPPLY),
        stage=_stage(raw, Stage.ENERGY),
    )


def _stepped(raw: Mapping[str, Any]) -> Component:
    return SteppedCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        _blocks(raw.get("blocks", ()), raw["code"]),
        determinant=str(raw.get("determinant", "energy.total")),
        unit=_unit(raw, Unit.KWH),
        side=_side(raw, ChargeSide.SUPPLY),
        stage=_stage(raw, Stage.ENERGY),
    )


def _tou(raw: Mapping[str, Any]) -> Component:
    return TouCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        dict(raw.get("rates", {})),
        prefix=str(raw.get("prefix", "energy.bucket")),
        unit=_unit(raw, Unit.KWH),
        side=_side(raw, ChargeSide.SUPPLY),
        stage=_stage(raw, Stage.ENERGY),
        require_all=bool(raw.get("require_all", False)),
    )


def _demand(raw: Mapping[str, Any]) -> Component:
    return DemandCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        raw["rate"],
        determinant=str(raw.get("determinant", "demand.peak")),
        floor_determinant=str(raw.get("floor_determinant", "demand.ratchet_floor")),
        unit=_unit(raw, Unit.KW),
        side=_side(raw, ChargeSide.DELIVERY),
        stage=_stage(raw, Stage.DEMAND),
        minimum_billed=raw.get("minimum_billed", "0"),
    )


def _reactive(raw: Mapping[str, Any]) -> Component:
    return PowerFactorCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        raw["rate"],
        allowance_fraction=raw.get("allowance_fraction", "0.3"),
        target_power_factor=raw.get("target_power_factor", "0.95"),
        mode=str(raw.get("mode", "kvarh")),
        reactive_determinant=str(raw.get("reactive_determinant", "reactive.total")),
        energy_determinant=str(raw.get("energy_determinant", "energy.total")),
        side=_side(raw, ChargeSide.DELIVERY),
        stage=_stage(raw, Stage.REACTIVE),
    )


def _rider(raw: Mapping[str, Any]) -> Component:
    return Rider(
        raw["code"],
        raw.get("label", raw["code"]),
        raw["rate"],
        rider_kind=RiderKind(str(raw.get("rider_kind", "per_unit"))),
        determinant=str(raw.get("determinant", "energy.total")),
        unit=_unit(raw, Unit.KWH),
        basis=Basis(str(raw.get("basis", "before_credits"))),
        side=_side(raw, ChargeSide.DELIVERY),
        stage=_stage(raw, Stage.RIDER),
        taxable=bool(raw.get("taxable", True)),
    )


def _credit(raw: Mapping[str, Any]) -> Component:
    return ExportCredit(
        raw["code"],
        raw.get("label", raw["code"]),
        retail_rate=raw["retail_rate"],
        avoided_cost_rate=raw.get("avoided_cost_rate", "0"),
        determinant=str(raw.get("determinant", "energy.exported")),
        unit=_unit(raw, Unit.KWH),
        side=_side(raw, ChargeSide.SUPPLY),
        stage=_stage(raw, Stage.CREDIT),
    )


def _minimum(raw: Mapping[str, Any]) -> Component:
    override = raw.get("basis_override")
    return MinimumCharge(
        raw["code"],
        raw.get("label", raw["code"]),
        raw["amount"],
        prorate=bool(raw.get("prorate", True)),
        side=_side(raw, ChargeSide.DELIVERY),
        stage=_stage(raw, Stage.MINIMUM),
        basis_override=Basis(str(override)) if override else None,
    )


def _discount(raw: Mapping[str, Any]) -> Component:
    return AssistanceDiscount(
        raw["code"],
        raw.get("label", raw["code"]),
        percent=raw.get("percent", "0"),
        flat_amount=raw.get("flat_amount", "0"),
        cap=raw.get("cap", "0"),
        basis=Basis(str(raw.get("basis", "subtotal"))),
        prorate=bool(raw.get("prorate", True)),
        programme=str(raw.get("programme", "")),
        side=_side(raw, ChargeSide.OTHER),
        stage=_stage(raw, Stage.DISCOUNT),
    )


COMPONENT_KINDS: dict[str, Callable[[Mapping[str, Any]], Component]] = {
    "fixed": _fixed,
    "tiered": _tiered,
    "stepped": _stepped,
    "tou": _tou,
    "demand": _demand,
    "reactive": _reactive,
    "rider": _rider,
    "credit": _credit,
    "minimum": _minimum,
    "discount": _discount,
}


def component_from_dict(raw: Mapping[str, Any]) -> Component:
    """Build one component from its document form."""

    kind = str(raw.get("kind", ""))
    builder = COMPONENT_KINDS.get(kind)
    if builder is None:
        raise UnknownComponentError(
            "unknown component kind",
            kind=kind or "(missing)",
            known=", ".join(sorted(COMPONENT_KINDS)),
        )
    if "code" not in raw:
        raise TariffError("every component needs a code", kind=kind)
    return builder(raw)


def _windows(raw: Mapping[str, Any]) -> WindowSet | None:
    """Build a window set from its document form."""

    entries = raw.get("windows")
    if not entries:
        return None
    windows = tuple(
        TimeWindow.between(
            entry["bucket"],
            entry["start"],
            entry["end"],
            tuple(DayType(value) for value in entry.get("day_types", ())),
            str(entry.get("season", "")),
            str(entry.get("label", "")),
        )
        for entry in entries
    )
    precedence = raw.get("precedence")
    return WindowSet(
        windows,
        str(raw.get("default_bucket", "offpeak")),
        WindowPrecedence(precedence) if precedence else None,
    )


def _seasons(raw: Mapping[str, Any]) -> SeasonSet | None:
    """Build a season set from its document form."""

    entries = raw.get("seasons")
    if not entries:
        return None
    seasons = tuple(
        Season(
            entry["code"],
            int(entry["start_month"]),
            int(entry["start_day"]),
            int(entry["end_month"]),
            int(entry["end_day"]),
            str(entry.get("label", "")),
        )
        for entry in entries
    )
    return SeasonSet(seasons, str(raw.get("default_season", "")))


def tariff_from_dict(raw: Mapping[str, Any]) -> Tariff:
    """Build a whole tariff from its document form."""

    if "code" not in raw:
        raise TariffError("a tariff needs a code")
    components = tuple(
        component_from_dict(entry) for entry in raw.get("components", ())
    )
    kinds = tuple(ServiceKind(value) for value in raw.get("service_kinds", ()))
    metadata = tuple(
        sorted((str(key), str(value)) for key, value in dict(raw.get("metadata", {})).items())
    )
    return Tariff(
        str(raw["code"]),
        str(raw.get("name", raw["code"])),
        components,
        str(raw.get("currency", "USD")),
        kinds,
        _windows(raw),
        _seasons(raw),
        Unit(raw["energy_unit"]) if raw.get("energy_unit") else Unit.KWH,
        str(raw.get("description", "")),
        metadata,
    )
