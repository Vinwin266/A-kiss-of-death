#!/usr/bin/env python3
"""Regenerate the example datasets in ``examples/``.

The examples are checked in, and CI re-runs this script and fails if the
result differs.  That keeps the fixtures honest: an example that no longer
matches the generator is either a stale file or an undocumented change to
the dataset format, and both are worth knowing about.

Nothing here uses randomness or the clock.  Interval data is produced from a
fixed shape and a fixed weekly modulation, so the same script produces the
same bytes on any machine.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from meterline.io.jsonio import canonical_dumps  # noqa: E402
from meterline.timeline.calendars import MonthKey  # noqa: E402
from meterline.timeline.cycles import CycleSchedule  # noqa: E402
from meterline.timeline.zones import common_zone  # noqa: E402

EXAMPLES = ROOT / "examples"

ZONE_NAME = "America/New_York"
ZONE = common_zone(ZONE_NAME)

# Hourly shape used for the commercial interval channel, in kWh per hour for
# a nominal day.  Weekday and weekend are given separately because a bill
# that treats Saturday as a working day is one of the conventions the
# examples are meant to exercise.
WEEKDAY_SHAPE = [
    "4.2", "4.0", "3.9", "3.9", "4.1", "5.4",
    "9.8", "16.5", "21.2", "23.4", "23.9", "23.6",
    "22.1", "23.0", "23.3", "22.4", "18.9", "13.2",
    "9.4", "7.1", "5.9", "5.0", "4.6", "4.3",
]
WEEKEND_SHAPE = ["4.4"] * 7 + ["6.1"] * 10 + ["4.8"] * 7


def instant(value: datetime) -> str:
    """Render an instant the way the dataset format expects."""

    return value.isoformat().replace("+00:00", "Z")


def cycle_bounds(read_day: int, first_month: MonthKey, count: int) -> list[datetime]:
    """Return the ``count + 1`` cycle boundaries of a read schedule."""

    schedule = CycleSchedule("R1", read_day, ZONE)
    cycles = schedule.cycles("sp", first_month, count)
    return [cycles[0].span.start] + [cycle.span.end for cycle in cycles]


def register_reads(
    meter_id: str,
    register_id: str,
    bounds: list[datetime],
    start_value: int,
    steps: list[int],
    *,
    read_type: str = "actual",
    quality: str = "valid",
) -> list[dict[str, Any]]:
    """Return dial readings implied by a starting value and per-cycle usage."""

    reads: list[dict[str, Any]] = []
    value = start_value
    for index, moment in enumerate(bounds):
        reads.append(
            {
                "meter_id": meter_id,
                "register_id": register_id,
                "at": instant(moment),
                "value": str(value),
                "read_type": read_type if index else "actual",
                "quality": quality if index else "valid",
                "source": "route",
            }
        )
        if index < len(steps):
            value += steps[index]
    return reads


def hourly_values(start: datetime, hours: int) -> list[str]:
    """Return a deterministic hourly consumption series."""

    values: list[str] = []
    for offset in range(hours):
        moment = start + timedelta(hours=offset)
        local = ZONE.to_local(moment)
        shape = WEEKDAY_SHAPE if local.weekday() < 5 else WEEKEND_SHAPE
        base = Decimal(shape[local.hour])
        # A small, fixed weekly modulation so the series is not perfectly
        # periodic; deliberately a function of the date, never of the clock.
        modulation = Decimal(1) + Decimal(local.toordinal() % 5) / Decimal(200)
        values.append(str((base * modulation).quantize(Decimal("0.001"))))
    return values


def cycle_sums(
    values: list[str], start: datetime, bounds: list[datetime]
) -> list[int]:
    """Return the whole-unit total of an hourly series over each cycle."""

    totals: list[int] = []
    for opening, closing in zip(bounds, bounds[1:]):
        begin = int((opening - start).total_seconds() // 3600)
        finish = int((closing - start).total_seconds() // 3600)
        total = sum(
            (Decimal(value) for value in values[begin:finish]), Decimal(0)
        )
        totals.append(int(total.to_integral_value()))
    return totals


def residential_tariff(version: str, effective_from: datetime, energy: str) -> dict[str, Any]:
    """Return the standard residential tariff at a given set of rates."""

    return {
        "code": "RES-STD",
        "version": version,
        "name": "Residential Service",
        "description": "Standard residential rate with a two-block energy charge.",
        "effective_from": instant(effective_from),
        "currency": "USD",
        "service_kinds": ["residential"],
        "energy_unit": "kWh",
        "components": [
            {
                "kind": "fixed",
                "code": "res.basic",
                "label": "Basic service charge",
                "amount": "14.75",
                "per": "month",
                "side": "delivery",
            },
            {
                "kind": "tiered",
                "code": "res.energy",
                "label": "Energy charge",
                "determinant": "energy.total",
                "side": "supply",
                "blocks": [
                    {"limit": "600", "rate": energy, "label": "first 600 kWh"},
                    {"limit": None, "rate": "0.13140", "label": "over 600 kWh"},
                ],
            },
            {
                "kind": "rider",
                "code": "res.ee",
                "label": "Energy efficiency rider",
                "rate": "0.00412",
                "rider_kind": "per_unit",
                "determinant": "energy.total",
            },
            {
                "kind": "rider",
                "code": "res.storm",
                "label": "Storm recovery rider",
                "rate": "1.9",
                "rider_kind": "percent",
                "basis": "before_credits",
            },
            {
                "kind": "minimum",
                "code": "res.minimum",
                "label": "Minimum charge",
                "amount": "22.00",
            },
            {
                "kind": "discount",
                "code": "res.assist",
                "label": "Customer assistance discount",
                "percent": "18",
                "cap": "35.00",
                "programme": "LIHEAP",
                "basis": "subtotal",
            },
        ],
    }


def solar_tariff(effective_from: datetime) -> dict[str, Any]:
    """Return the residential net-metering tariff."""

    return {
        "code": "RES-NEM",
        "version": "1",
        "name": "Residential Net Metering",
        "description": "Residential service for customers with on-site generation.",
        "effective_from": instant(effective_from),
        "currency": "USD",
        "service_kinds": ["residential"],
        "components": [
            {
                "kind": "fixed",
                "code": "nem.basic",
                "label": "Basic service charge",
                "amount": "18.50",
                "per": "month",
                "side": "delivery",
            },
            {
                "kind": "tiered",
                "code": "nem.energy",
                "label": "Energy charge",
                "side": "supply",
                "blocks": [
                    {"limit": "600", "rate": "0.11480", "label": "first 600 kWh"},
                    {"limit": None, "rate": "0.14020", "label": "over 600 kWh"},
                ],
            },
            {
                "kind": "credit",
                "code": "nem.export",
                "label": "Export credit",
                "retail_rate": "0.11480",
                "avoided_cost_rate": "0.03910",
            },
            {
                "kind": "minimum",
                "code": "nem.minimum",
                "label": "Minimum charge",
                "amount": "18.50",
                "prorate": True,
            },
        ],
    }


def commercial_tariff(effective_from: datetime) -> dict[str, Any]:
    """Return the general-service time-of-use tariff."""

    return {
        "code": "GS-TOU",
        "version": "1",
        "name": "General Service — Time of Use",
        "description": "Small commercial service billed on time of use and demand.",
        "effective_from": instant(effective_from),
        "currency": "USD",
        "service_kinds": ["small_commercial", "large_commercial"],
        "default_bucket": "offpeak",
        "seasons": [
            {
                "code": "summer",
                "start_month": 6,
                "start_day": 1,
                "end_month": 9,
                "end_day": 30,
                "label": "Summer",
            },
            {
                "code": "winter",
                "start_month": 10,
                "start_day": 1,
                "end_month": 5,
                "end_day": 31,
                "label": "Winter",
            },
        ],
        "windows": [
            {
                "bucket": "peak",
                "start": "14:00",
                "end": "19:00",
                "day_types": ["weekday"],
                "season": "summer",
            },
            {
                "bucket": "peak",
                "start": "07:00",
                "end": "11:00",
                "day_types": ["weekday"],
                "season": "winter",
            },
            {
                "bucket": "shoulder",
                "start": "07:00",
                "end": "22:00",
                "day_types": ["weekday"],
            },
        ],
        "components": [
            {
                "kind": "fixed",
                "code": "gs.customer",
                "label": "Customer charge",
                "amount": "1.85",
                "per": "day",
                "side": "delivery",
            },
            {
                "kind": "tou",
                "code": "gs.energy",
                "label": "Energy charge",
                "side": "supply",
                "rates": {
                    "peak": "0.18640",
                    "shoulder": "0.10920",
                    "offpeak": "0.07310",
                },
            },
            {
                "kind": "demand",
                "code": "gs.demand",
                "label": "Demand charge",
                "rate": "13.40",
                "side": "delivery",
            },
            {
                "kind": "reactive",
                "code": "gs.pf",
                "label": "Reactive energy charge",
                "rate": "0.0121",
                "allowance_fraction": "0.35",
            },
            {
                "kind": "rider",
                "code": "gs.storm",
                "label": "Storm recovery rider",
                "rate": "1.9",
                "rider_kind": "percent",
                "basis": "before_credits",
            },
            {
                "kind": "minimum",
                "code": "gs.minimum",
                "label": "Minimum charge",
                "amount": "95.00",
            },
        ],
    }


def jurisdictions() -> list[dict[str, Any]]:
    """Return the tax jurisdictions used by the examples."""

    return [
        {
            "code": "us-ny",
            "label": "New York State",
            "rules": [
                {
                    "code": "tax.state",
                    "label": "State utility tax",
                    "kind": "percent",
                    "rate": "2.35",
                    "basis": "subtotal",
                    "order": 10,
                }
            ],
        },
        {
            "code": "us-ny-riverside",
            "label": "Riverside",
            "parent": "us-ny",
            "rules": [
                {
                    "code": "tax.local",
                    "label": "Local gross receipts tax",
                    "kind": "percent",
                    "rate": "1.40",
                    "basis": "subtotal",
                    "order": 20,
                },
                {
                    "code": "fee.reliability",
                    "label": "System reliability fee",
                    "kind": "per_unit",
                    "rate": "0.00061",
                    "determinant": "energy.total",
                    "order": 30,
                },
            ],
        },
    ]


def riverside() -> dict[str, Any]:
    """Build the larger worked example."""

    bounds = cycle_bounds(18, MonthKey(2025, 2), 6)
    first = bounds[0]
    interval_start = bounds[0]
    interval_hours = int((bounds[6] - interval_start).total_seconds() // 3600)
    interval_values = hourly_values(interval_start, interval_hours)
    # The commercial meter's register reads are derived from its own
    # interval data, so the two agree to the whole kilowatt-hour and the
    # interval-sum validation has something real to check.
    energy_steps = cycle_sums(interval_values, interval_start, bounds)
    reactive_steps = [int(step * 31 // 100) for step in energy_steps]

    reads: list[dict[str, Any]] = []
    reads += register_reads("mt-1001", "rg-1001", bounds, 41820, [612, 548, 501, 664, 918, 874])
    # The second household is billed from an estimated read in April, which
    # the following actual read corrects.
    solar_import = register_reads(
        "mt-1002", "rg-1002", bounds, 22140, [498, 441, 402, 377, 486, 521]
    )
    solar_import[3]["read_type"] = "estimated"
    solar_import[3]["quality"] = "estimated"
    solar_import[3]["source"] = "estimate"
    reads += solar_import
    reads += register_reads(
        "mt-1002", "rg-1003", bounds, 8100, [212, 268, 341, 402, 455, 431]
    )
    reads += register_reads("mt-1003", "rg-1004", bounds, 158400, energy_steps)
    reads += register_reads("mt-1003", "rg-1005", bounds, 44100, reactive_steps)
    # The fourth service point had its meter exchanged part way through.
    # The old dial keeps counting up to the exchange, and the register
    # change below supplies both its closing value and the new dial's
    # opening one; no read is written at the exchange instant itself.
    reads += register_reads("mt-1004", "rg-1006", bounds[:3], 99120, [742, 690])
    reads += register_reads("mt-1004", "rg-1006", bounds[4:], 728, [705, 731])

    return {
        "meterline": "0.12",
        "name": "riverside",
        "profile": {"base": "model-rules"},
        "observed_rule": "nearest_weekday",
        "premises": [
            {
                "premise_id": "pr-1",
                "address": "18 Mill Race",
                "locality": "Riverside",
                "region": "NY",
                "postcode": "12401",
                "jurisdiction": "us-ny-riverside",
                "climate_zone": "4A",
            },
            {
                "premise_id": "pr-2",
                "address": "44 Weir Lane",
                "locality": "Riverside",
                "region": "NY",
                "postcode": "12401",
                "jurisdiction": "us-ny-riverside",
                "climate_zone": "4A",
            },
            {
                "premise_id": "pr-3",
                "address": "2 Tannery Yard",
                "locality": "Riverside",
                "region": "NY",
                "postcode": "12402",
                "jurisdiction": "us-ny-riverside",
                "climate_zone": "4A",
            },
            {
                "premise_id": "pr-4",
                "address": "7 Lock Keeper's Row",
                "locality": "Riverside",
                "region": "NY",
                "postcode": "12401",
                "jurisdiction": "us-ny",
                "climate_zone": "4A",
            },
        ],
        "accounts": [
            {
                "account_id": "ac-100",
                "name": "H. Ambrose",
                "service_point_ids": ["sp-100"],
            },
            {
                "account_id": "ac-200",
                "name": "R. Fenwick",
                "service_point_ids": ["sp-200"],
            },
            {
                "account_id": "ac-300",
                "name": "Tannery Yard Workshops",
                "service_point_ids": ["sp-300"],
                "tax_exemption_codes": ["ex-manufacturing"],
            },
            {
                "account_id": "ac-400",
                "name": "M. Threlfall",
                "service_point_ids": ["sp-400"],
                "assistance_program": "LIHEAP",
            },
        ],
        "service_points": [
            {
                "service_point_id": "sp-100",
                "account_id": "ac-100",
                "premise_id": "pr-1",
                "zone": ZONE_NAME,
                "kind": "residential",
                "route": "R1",
                "meter_ids": ["mt-1001"],
                "label": "Mill Race",
            },
            {
                "service_point_id": "sp-200",
                "account_id": "ac-200",
                "premise_id": "pr-2",
                "zone": ZONE_NAME,
                "kind": "residential",
                "route": "R1",
                "meter_ids": ["mt-1002"],
                "has_generation": True,
                "generation_capacity_kw": "6.4",
                "label": "Weir Lane",
            },
            {
                "service_point_id": "sp-300",
                "account_id": "ac-300",
                "premise_id": "pr-3",
                "zone": ZONE_NAME,
                "kind": "small_commercial",
                "route": "R2",
                "meter_ids": ["mt-1003"],
                "label": "Tannery Yard",
            },
            {
                "service_point_id": "sp-400",
                "account_id": "ac-400",
                "premise_id": "pr-4",
                "zone": ZONE_NAME,
                "kind": "residential",
                "route": "R1",
                "meter_ids": ["mt-1004"],
                "label": "Lock Keeper's Row",
            },
        ],
        "meters": [
            {
                "meter_id": "mt-1001",
                "service_point_id": "sp-100",
                "kind": "electric",
                "serial": "A-441027",
                "registers": [{"register_id": "rg-1001", "unit": "kWh", "digits": 5}],
            },
            {
                "meter_id": "mt-1002",
                "service_point_id": "sp-200",
                "kind": "electric",
                "serial": "A-518866",
                "registers": [
                    {"register_id": "rg-1002", "unit": "kWh", "digits": 5},
                    {
                        "register_id": "rg-1003",
                        "unit": "kWh",
                        "digits": 5,
                        "channel": "received",
                        "label": "Export",
                    },
                ],
            },
            {
                "meter_id": "mt-1003",
                "service_point_id": "sp-300",
                "kind": "electric",
                "serial": "C-100394",
                "registers": [
                    {
                        "register_id": "rg-1004",
                        "unit": "kWh",
                        "digits": 5,
                        "multiplier": "1",
                    },
                    {
                        "register_id": "rg-1005",
                        "unit": "kvarh",
                        "digits": 5,
                        "channel": "reactive",
                    },
                ],
                "channels": [
                    {
                        "channel_id": "ch-1003",
                        "kind": "delivered",
                        "unit": "kWh",
                        "interval_minutes": 60,
                        "label": "Delivered energy",
                    }
                ],
            },
            {
                "meter_id": "mt-1004",
                "service_point_id": "sp-400",
                "kind": "electric",
                "serial": "A-330915",
                "registers": [{"register_id": "rg-1006", "unit": "kWh", "digits": 5}],
            },
        ],
        "reads": reads,
        "register_changes": [
            {
                "meter_id": "mt-1004",
                "register_id": "rg-1006",
                "at": instant(bounds[3]),
                "final_value": "101254",
                "initial_value": "40",
                "reason": "meter exchange",
            }
        ],
        "series": [
            {
                "channel_id": "ch-1003",
                "start": instant(interval_start),
                "interval_minutes": 60,
                "unit": "kWh",
                "values": interval_values,
            }
        ],
        "tariffs": [
            residential_tariff("1", first, "0.10920"),
            residential_tariff("2", bounds[3], "0.11360"),
            solar_tariff(first),
            commercial_tariff(first),
        ],
        "enrollments": [
            {"service_point_id": "sp-100", "tariff": "RES-STD", "from": instant(first)},
            {"service_point_id": "sp-200", "tariff": "RES-NEM", "from": instant(first)},
            {"service_point_id": "sp-300", "tariff": "GS-TOU", "from": instant(first)},
            {"service_point_id": "sp-400", "tariff": "RES-STD", "from": instant(first)},
        ],
        "jurisdictions": jurisdictions(),
        "exemptions": [
            {
                "code": "ex-manufacturing",
                "tax_code": "tax.local",
                "percent": "60",
                "label": "Manufacturing partial exemption",
            }
        ],
        "cycle_schedules": [
            {
                "service_point_id": "sp-100",
                "route": "R1",
                "read_day": 18,
                "first_month": "2025-02",
                "count": 6,
            },
            {
                "service_point_id": "sp-200",
                "route": "R1",
                "read_day": 18,
                "first_month": "2025-02",
                "count": 6,
            },
            {
                "service_point_id": "sp-300",
                "route": "R2",
                "read_day": 18,
                "first_month": "2025-02",
                "count": 6,
            },
            {
                "service_point_id": "sp-400",
                "route": "R1",
                "read_day": 18,
                "first_month": "2025-02",
                "count": 6,
            },
        ],
    }


def tiny() -> dict[str, Any]:
    """Build the smallest dataset that still produces a bill."""

    bounds = cycle_bounds(10, MonthKey(2025, 5), 3)
    return {
        "meterline": "0.12",
        "name": "tiny",
        "profile": {"base": "legacy-cooperative"},
        "premises": [
            {
                "premise_id": "pr-t1",
                "address": "1 Short Row",
                "locality": "Riverside",
                "region": "NY",
                "jurisdiction": "us-ny",
            }
        ],
        "accounts": [
            {"account_id": "ac-t1", "name": "Example Customer", "service_point_ids": ["sp-t1"]}
        ],
        "service_points": [
            {
                "service_point_id": "sp-t1",
                "account_id": "ac-t1",
                "premise_id": "pr-t1",
                "zone": ZONE_NAME,
                "kind": "residential",
                "route": "T1",
                "meter_ids": ["mt-t1"],
            }
        ],
        "meters": [
            {
                "meter_id": "mt-t1",
                "service_point_id": "sp-t1",
                "kind": "electric",
                "registers": [{"register_id": "rg-t1", "unit": "kWh", "digits": 5}],
            }
        ],
        "reads": register_reads("mt-t1", "rg-t1", bounds, 1000, [430, 512, 388]),
        "tariffs": [residential_tariff("1", bounds[0], "0.10920")],
        "enrollments": [
            {"service_point_id": "sp-t1", "tariff": "RES-STD", "from": instant(bounds[0])}
        ],
        "jurisdictions": jurisdictions()[:1],
        "cycle_schedules": [
            {
                "service_point_id": "sp-t1",
                "route": "T1",
                "read_day": 10,
                "first_month": "2025-05",
                "count": 3,
            }
        ],
    }


def main() -> int:
    """Write both examples and report what changed."""

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for name, builder in (("riverside", riverside), ("tiny", tiny)):
        target = EXAMPLES / f"{name}.json"
        rendered = canonical_dumps(builder())
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(rendered, encoding="utf-8")
        state = "unchanged" if previous == rendered else "written"
        print(f"{target.relative_to(ROOT)}: {state} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
