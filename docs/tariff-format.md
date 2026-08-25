# Tariff format

A tariff is a code, a name and an ordered list of components. Each component
answers one question — what the standing charge comes to, what the first 500
kWh cost — and returns line items.

`meterline tariff --dataset PATH --code RES-STD` describes one and runs the
static checks over it.

## Stages

Components run in stage order, then in declaration order. The stages are
numeric so a tariff can insert something between two of them:

| Stage | Number | Typical components |
| --- | --- | --- |
| fixed | 10 | standing and customer charges |
| energy | 20 | tiered, stepped and time-of-use charges |
| demand | 30 | demand charges |
| reactive | 35 | power-factor charges |
| rider | 50 | surcharges on a basis |
| credit | 60 | export credits |
| minimum | 70 | minimum-charge make-up |
| discount | 80 | assistance discounts |

Order is itself a convention: a rider assessed on the energy subtotal sees a
different number depending on whether the minimum make-up has been added yet.

## Components

### fixed

```json
{ "kind": "fixed", "code": "res.basic", "label": "Basic service charge",
  "amount": "14.75", "per": "month", "side": "delivery", "taxable": true }
```

`per` is `month`, `day` or `bill`. The per-month form is what the proration
convention acts on.

### tiered

Marginal blocks — each block prices only the usage inside it.

```json
{ "kind": "tiered", "code": "res.energy", "determinant": "energy.total",
  "blocks": [
    { "limit": "600", "rate": "0.10920", "label": "first 600 kWh" },
    { "limit": null,  "rate": "0.13140", "label": "over 600 kWh" }
  ] }
```

Limits must ascend and the final block must be open, or usage above it would
be unpriced.

### stepped

The whole quantity at the rate of the band it lands in. Crossing a threshold
raises the price of every unit — water utilities use it deliberately as a
conservation signal. Same block syntax as `tiered`.

### tou

```json
{ "kind": "tou", "code": "gs.energy",
  "rates": { "peak": "0.18640", "shoulder": "0.10920", "offpeak": "0.07310" },
  "prefix": "energy.bucket", "require_all": false }
```

Reads `energy.bucket.<name>` determinants. The component does not decide
which hours are peak; the window set does, when the determinants are derived.

### demand

```json
{ "kind": "demand", "code": "gs.demand", "rate": "13.40",
  "determinant": "demand.peak", "floor_determinant": "demand.ratchet_floor",
  "minimum_billed": "0" }
```

The ratchet floor arrives as a determinant, because computing it needs
cross-cycle history that has no business inside a tariff.

### reactive

```json
{ "kind": "reactive", "code": "gs.pf", "rate": "0.0121",
  "mode": "kvarh", "allowance_fraction": "0.35" }
```

`mode` is `kvarh` (a rate above an allowance expressed as a fraction of real
energy) or `power_factor` (a penalty scaled by the shortfall against
`target_power_factor`).

### rider

```json
{ "kind": "rider", "code": "res.storm", "rate": "1.9",
  "rider_kind": "percent", "basis": "before_credits" }
```

`rider_kind` is `per_unit`, `percent` or `flat`. The basis matters: a
percentage of `subtotal` shrinks when the customer generates, because it sees
the export credit; the same rider on `before_credits` does not.

### credit

```json
{ "kind": "credit", "code": "nem.export",
  "retail_rate": "0.11480", "avoided_cost_rate": "0.03910" }
```

Both rates live on the component so switching the valuation convention does
not need a different tariff. Banking is not handled here — a credit larger
than the bill needs state from outside the cycle.

### minimum

```json
{ "kind": "minimum", "code": "res.minimum", "amount": "22.00",
  "prorate": true, "basis_override": null }
```

Which subtotal the floor is compared against comes from the profile unless
`basis_override` insists.

### discount

```json
{ "kind": "discount", "code": "res.assist", "percent": "18",
  "cap": "35.00", "programme": "LIHEAP", "basis": "subtotal" }
```

Applies only to accounts enrolled in the named programme.

## Windows and seasons

```json
"seasons": [
  { "code": "summer", "start_month": 6, "start_day": 1,
    "end_month": 9, "end_day": 30 },
  { "code": "winter", "start_month": 10, "start_day": 1,
    "end_month": 5, "end_day": 31 }
],
"windows": [
  { "bucket": "peak", "start": "14:00", "end": "19:00",
    "day_types": ["weekday"], "season": "summer" },
  { "bucket": "shoulder", "start": "07:00", "end": "22:00",
    "day_types": ["weekday"] }
],
"default_bucket": "offpeak",
"precedence": "most_specific"
```

A season may wrap the year end, and a window may wrap midnight. Minutes no
window claims fall into `default_bucket`. `precedence` overrides the profile
for this tariff only.

## What the validator checks

`validate_tariff` reports, without ever raising:

- windows that overlap, and which precedence resolves them;
- parts of a day no window claims;
- buckets the windows produce that no component prices, and rates for
  buckets that never occur;
- a season set with a hole and no default;
- more than one minimum charge;
- a percentage rider assessed after a minimum make-up;
- declining or negative block rates;
- an export credit with no avoided-cost rate, which would credit nothing if
  the valuation convention changed.
