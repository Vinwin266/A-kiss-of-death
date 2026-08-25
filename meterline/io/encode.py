"""Rendering datasets and bills back into plain documents.

Encoding exists for two reasons: the ``export`` command, and the round-trip
test.  A dataset that cannot survive being written out and read back in has
a field the decoder is quietly ignoring, and the round-trip is the cheapest
way to find out which one.
"""

from __future__ import annotations

from typing import Any

from ..dataset import Dataset
from ..model.series import IntervalSeries
from ..rating.invoice import Invoice
from ..version import VERSION

__all__ = ["dataset_to_dict", "invoice_to_dict", "series_to_dict"]


def series_to_dict(series: IntervalSeries) -> dict[str, Any]:
    """Return a document form of an interval series."""

    return {
        "channel_id": series.channel_id,
        "start": series.start.isoformat(),
        "interval_minutes": series.interval_minutes,
        "unit": str(series.unit),
        "values": [None if value is None else str(value) for value in series.values],
        "qualities": [quality.value for quality in series.qualities],
    }


def dataset_to_dict(dataset: Dataset) -> dict[str, Any]:
    """Return a document form of a whole dataset."""

    return {
        "meterline": VERSION,
        "name": dataset.name,
        "profile": dataset.profile.as_dict(),
        "premises": [
            {
                "premise_id": premise.premise_id,
                "address": premise.address,
                "locality": premise.locality,
                "region": premise.region,
                "postcode": premise.postcode,
                "jurisdiction": premise.jurisdiction,
                "climate_zone": premise.climate_zone,
            }
            for premise in [dataset.premises[key] for key in sorted(dataset.premises)]
        ],
        "accounts": [
            {
                "account_id": account.account_id,
                "name": account.name,
                "currency": account.currency,
                "status": account.status.value,
                "service_point_ids": list(account.service_point_ids),
                "assistance_program": account.assistance_program,
                "budget_plan_id": account.budget_plan_id,
                "tax_exemption_codes": list(account.tax_exemption_codes),
            }
            for account in [dataset.accounts[key] for key in sorted(dataset.accounts)]
        ],
        "service_points": [
            {
                "service_point_id": point.service_point_id,
                "account_id": point.account_id,
                "premise_id": point.premise_id,
                "zone": point.zone_name,
                "kind": point.kind.value,
                "route": point.route,
                "meter_ids": list(point.meter_ids),
                "connected_at": point.connected_at.isoformat() if point.connected_at else None,
                "disconnected_at": (
                    point.disconnected_at.isoformat() if point.disconnected_at else None
                ),
                "voltage_level": point.voltage_level,
                "has_generation": point.has_generation,
                "generation_capacity_kw": point.generation_capacity_kw,
                "label": point.label,
            }
            for point in [
                dataset.service_points[key] for key in sorted(dataset.service_points)
            ]
        ],
        "meters": [
            {
                "meter_id": meter.meter_id,
                "service_point_id": meter.service_point_id,
                "kind": meter.kind.value,
                "serial": meter.serial,
                "registers": [
                    {
                        "register_id": register.register_id,
                        "unit": str(register.unit),
                        "digits": register.digits,
                        "multiplier": register.multiplier,
                        "channel": register.channel.value,
                        "tou_bucket": register.tou_bucket,
                        "label": register.label,
                        "decimals": register.decimals,
                    }
                    for register in meter.registers
                ],
                "channels": [
                    {
                        "channel_id": channel.channel_id,
                        "kind": channel.kind.value,
                        "unit": str(channel.unit),
                        "interval_minutes": channel.interval_minutes,
                        "multiplier": channel.multiplier,
                        "label": channel.label,
                    }
                    for channel in meter.channels
                ],
            }
            for meter in [dataset.meters[key] for key in sorted(dataset.meters)]
        ],
        "reads": [
            {
                "meter_id": read.meter_id,
                "register_id": read.register_id,
                "at": read.at.isoformat(),
                "value": str(read.value),
                "read_type": read.read_type.value,
                "quality": read.quality.value,
                "source": read.source,
                "note": read.note,
            }
            for read in dataset.reads
        ],
        "register_changes": [
            {
                "meter_id": change.meter_id,
                "register_id": change.register_id,
                "at": change.at.isoformat(),
                "final_value": str(change.final_value),
                "initial_value": str(change.initial_value),
                "reason": change.reason,
                "new_register_id": change.new_register_id,
            }
            for change in dataset.changes
        ],
        "series": [series_to_dict(dataset.series[key]) for key in sorted(dataset.series)],
        "tariffs": [
            {
                **version.tariff.as_dict(),
                "version": version.version,
                "effective_from": version.effective_from.isoformat(),
                "effective_to": (
                    version.effective_to.isoformat() if version.effective_to else None
                ),
                "order_reference": version.order_reference,
            }
            for code in dataset.catalog.codes()
            for version in dataset.catalog.schedule(code).versions
        ],
        "enrollments": [
            {
                "service_point_id": point_id,
                "tariff": entry.tariff_code,
                "from": entry.effective_from.isoformat(),
                "to": entry.effective_to.isoformat() if entry.effective_to else None,
                "reason": entry.reason,
            }
            for point_id in sorted(dataset.enrollments)
            for entry in dataset.enrollments[point_id].entries
        ],
        "jurisdictions": [
            {
                "code": jurisdiction.code,
                "label": jurisdiction.label,
                "parent": jurisdiction.parent,
                "rules": [
                    {
                        "code": rule.code,
                        "label": rule.label,
                        "kind": rule.kind.value,
                        "rate": str(rule.rate),
                        "basis": rule.basis.value,
                        "determinant": rule.determinant,
                        "unit": str(rule.unit),
                        "order": rule.order,
                        "exempt_classes": [
                            charge_class.value for charge_class in rule.exempt_classes
                        ],
                        "exemption_code": rule.exemption_code,
                    }
                    for rule in jurisdiction.rules
                ],
            }
            for jurisdiction in [
                dataset.jurisdictions.get(code)
                for code in dataset.jurisdictions.codes()
            ]
        ],
        "exemptions": [
            {
                "code": exemption.code,
                "tax_code": exemption.tax_code,
                "percent": str(exemption.percent),
                "cap": str(exemption.cap),
                "label": exemption.label,
            }
            for exemption in [
                dataset.exemptions.items[code] for code in dataset.exemptions.codes()
            ]
        ],
    }


def invoice_to_dict(invoice: Invoice, places: int = 2) -> dict[str, Any]:
    """Return a document form of one bill."""

    return invoice.as_dict(places)
