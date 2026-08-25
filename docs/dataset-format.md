# Dataset format

A dataset is one JSON object describing a closed world: the customers, the
meters, the readings, the rate schedules, the taxes and the conventions.
`meterline validate --dataset PATH` checks one without billing from it, and
`meterline export` writes one back out in canonical form.

Numbers are written as **strings**. `"0.10920"` survives a round trip; `0.1092`
depends on the reader's float behaviour, and a rate is not a float.

Instants are ISO-8601 with an explicit offset or a trailing `Z`. A timestamp
without one is refused rather than assumed.

## Top level

```json
{
  "meterline": "0.12",
  "name": "riverside",
  "profile": { "base": "model-rules", "tier_basis": "daily" },
  "observed_rule": "nearest_weekday",
  "premises": [], "accounts": [], "service_points": [], "meters": [],
  "reads": [], "register_changes": [], "series": [],
  "tariffs": [], "enrollments": [],
  "jurisdictions": [], "exemptions": [],
  "cycle_schedules": []
}
```

`profile` names a preset in `base` and overrides individual conventions.
Naming a base is recommended: a profile written from scratch silently
inherits the engine's own defaults for anything it forgets to mention.

## Premises and accounts

```json
{ "premise_id": "pr-1", "address": "18 Mill Race", "locality": "Riverside",
  "region": "NY", "postcode": "12401", "jurisdiction": "us-ny-riverside" }

{ "account_id": "ac-100", "name": "H. Ambrose", "currency": "USD",
  "status": "active", "service_point_ids": ["sp-100"],
  "assistance_program": "LIHEAP", "tax_exemption_codes": ["ex-manufacturing"] }
```

The premise carries the tax jurisdiction, because tax follows the place and
not the customer.

## Service points

```json
{ "service_point_id": "sp-200", "account_id": "ac-200", "premise_id": "pr-2",
  "zone": "America/New_York", "kind": "residential", "route": "R1",
  "meter_ids": ["mt-1002"],
  "connected_at": "2025-03-01T05:00:00Z",
  "has_generation": true, "generation_capacity_kw": "6.4" }
```

`connected_at` and `disconnected_at` shorten the served portion of a cycle,
which is what a move-in or a final bill prorates against.

Zone names are resolved against the engine's own registry, not the operating
system's; see [determinism.md](determinism.md).

## Meters, registers and channels

```json
{ "meter_id": "mt-1002", "service_point_id": "sp-200", "kind": "electric",
  "serial": "A-518866",
  "registers": [
    { "register_id": "rg-1002", "unit": "kWh", "digits": 5, "multiplier": "1" },
    { "register_id": "rg-1003", "unit": "kWh", "digits": 5, "channel": "received" }
  ],
  "channels": [
    { "channel_id": "ch-1003", "kind": "delivered", "unit": "kWh",
      "interval_minutes": 60 }
  ] }
```

A **register** is a cumulative dial: `digits` sets where it wraps and
`multiplier` converts dial units into billed units. Getting the multiplier
wrong is a factor-of-forty error that looks entirely plausible on a
commercial account.

`channel` is `delivered`, `received`, `net`, `demand` or `reactive`. A
register with a `tou_bucket` accumulates one time-of-use bucket only.

A **channel** is an interval stream. `interval_minutes` must be one of 1, 5,
10, 15, 30 or 60.

## Reads and register changes

```json
{ "meter_id": "mt-1001", "register_id": "rg-1001",
  "at": "2025-04-19T04:00:00Z", "value": "42432",
  "read_type": "actual", "quality": "valid", "source": "route" }

{ "meter_id": "mt-1004", "register_id": "rg-1006",
  "at": "2025-04-19T04:00:00Z",
  "final_value": "101254", "initial_value": "40", "reason": "meter exchange" }
```

`read_type` is `actual`, `estimated`, `customer`, `check`, `prorated` or
`system`. A `check` read verifies a route and does not close a cycle on its
own.

A register change supplies both the old dial's closing value and the new
dial's opening one. Do not also write a read at the same instant: the change
already provides both endpoints.

## Interval series

```json
{ "channel_id": "ch-1003", "start": "2025-01-19T05:00:00Z",
  "interval_minutes": 60, "unit": "kWh",
  "values": ["4.221", "4.020", null, "3.918"],
  "qualities": ["valid", "valid", "missing", "valid"] }
```

A series is a start plus a contiguous run of values. A hole is an explicit
`null`, so a missing row cannot masquerade as an absent one. `qualities` is
optional and defaults to `valid` for present values.

## Tariffs

See [tariff-format.md](tariff-format.md). Each entry is a dated version:

```json
{ "code": "RES-STD", "version": "2", "effective_from": "2025-04-19T04:00:00Z",
  "name": "Residential Service", "components": [ ... ] }
```

A version with no `effective_to` is closed automatically when the next one
begins.

## Enrolments

```json
{ "service_point_id": "sp-100", "tariff": "RES-STD",
  "from": "2025-01-19T05:00:00Z", "to": null }
```

Also closed automatically by the next entry: a customer is on one tariff at a
time.

## Jurisdictions and exemptions

```json
{ "code": "us-ny-riverside", "label": "Riverside", "parent": "us-ny",
  "rules": [
    { "code": "tax.local", "label": "Local gross receipts tax",
      "kind": "percent", "rate": "1.40", "basis": "subtotal", "order": 20 }
  ] }

{ "code": "ex-manufacturing", "tax_code": "tax.local", "percent": "60" }
```

Jurisdictions nest through `parent`; a premise names the innermost one and
the engine resolves the chain. `order` fixes the sequence under sequential
compounding, so it does not depend on the order the file happens to list
them in.

## Cycle schedules

```json
{ "service_point_id": "sp-100", "route": "R1", "read_day": 18,
  "shift": "none", "first_month": "2025-02", "count": 6 }
```

Cycles are generated rather than listed. A cycle closes at local midnight
*after* the read date, so the read date itself is billed. `shift` is `none`,
`forward`, `backward` or `nearest`, and moves a scheduled read off a weekend
or a holiday.
