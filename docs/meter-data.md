# Meter data

How dial readings and interval streams become the named quantities a tariff
prices. This is the half of the engine whose bugs produce *plausible* wrong
numbers, so every step records what it assumed.

## The pipeline

```
reads ─► rollover ─► consumption ─► validation ─► gaps ─► estimation ─┐
                          │                                          │
interval series ──────────┴────► bucketing ────► demand ─────────────┴─► determinants
```

## Deriving consumption

Two consecutive readings of a register give a delta. The register's
`multiplier` converts it into billed units, and its `digits` say where the
dial wraps.

When the later reading is lower, exactly one of four things happened and the
meter cannot say which: the dial wrapped, the dial was reset, the meter was
exchanged, or somebody wrote the digits down wrong. The `rollover` convention
chooses — see [conventions.md](conventions.md).

A **register change** supplies the old dial's closing value and the new
dial's opening one, and the derivation splits the surrounding pair around it.
Treating the two dial values as a single series instead produces a negative
or an enormous reading, which the rollover heuristics then confidently
misclassify.

Reads rarely land on a cycle boundary. A record that overlaps the period is
apportioned by elapsed time and flagged `partial` — the only assumption
available without finer data, and obviously wrong for a customer whose usage
is not uniform, which is why the flag travels with it.

## Quality

Quality is not a boolean. A cycle can be part actual, part estimated and part
edited.

| Code | Meaning |
| --- | --- |
| `valid` | Measured, validated, unmodified |
| `edited` | Measured, then changed by a human with a reason code |
| `estimated` | Produced by a model rather than measured |
| `partial` | Covers less than the span it is attached to |
| `suspect` | Failed a validation rule but was retained |
| `missing` | No value at all |

The quality of a whole comes from `quality_merge`. Under `worst_wins` one
estimated day makes the bill estimated; under `measured_wins` any measured
part makes it valid, which is how an estimate flag quietly disappears.

## Validation

Each rule raises its hand; none of them decides what happens next. That is
the `suspect_data` convention's job.

| Rule | Flags |
| --- | --- |
| `negative` | Usage went backwards on a non-net register |
| `spike` | Daily usage above `spike_factor` × the trailing average |
| `dropout` | Daily usage far below it |
| `stopped` | `zero_usage_days` of exactly zero |
| `interval_sum` | Interval totals disagree with the register delta beyond `interval_sum_tolerance` |
| `quality_mix` | The period combines data of different quality |

`interval_sum` only fires when the series actually covers the period.
Comparing a register delta against partial interval coverage would flag every
cycle at the edges of the data, which is noise rather than a finding.

## Gaps and estimation

A gap is a stretch of the period no *usable* record covers. Records whose
quality is unusable count as absent — so a period covered entirely by a
rejected rollover is a gap, not a silent zero.

Estimation strategies:

- **`trailing_average`** — the mean daily rate of the most recent
  `estimation_lookback_cycles` complete periods, times the gap length.
- **`prior_period`** — the same period one year earlier, scaled by days.
  Falls back to the trailing average, with a notice, when a year ago is
  missing.
- **`profile`** — a magnitude from the trailing average, distributed across
  the gap's local days by a load shape.
- **`zero`** — estimates nothing, making the absence visible.

Every estimate is flagged `estimated`, which sets `needs_true_up`, which is
what the `true_up` convention acts on when a real read arrives.

## Time-of-use bucketing

With interval data, each interval is placed in the bucket its own timestamp
falls in; where a boundary cuts an interval, its energy splits in proportion
to time.

Without interval data, a month's total is split between buckets in proportion
to the **hours** each bucket occupies. That systematically under-states peak
usage for a customer who peaks in the evening — which is exactly why tariffs
with real time-of-use rates require an interval meter. The engine will do it
if asked, flags the result `estimated`, and emits
`meterdata.tou.no_interval_data`.

## Demand

Demand is a rate, not a total, so it depends on the window it is measured
over. The same day of data yields three different peaks at 15 minutes, 30
minutes and an hour, and a rolling window can only ever find a peak at least
as high as a block window over the same data.

If the tariff asks for a window finer than the meter records, the window
widens to what the data supports and the reason travels with the
determinant. No amount of arithmetic recovers a quarter-hour peak from an
hourly total.

A **ratchet** bills a percentage of a past peak whenever this period's peak
is lower. A plant that ran hot for one August afternoon then idled all winter
pays for that afternoon eleven more times. The lookback excludes the current
month — including it would make the ratchet never bind.

## Determinants

The output. Each is a name, a quantity and a quality code:

| Name | Unit | Produced when |
| --- | --- | --- |
| `energy.total` | kWh | Always |
| `energy.exported` | kWh | A `received` register exists |
| `energy.bucket.<name>` | kWh | The tariff declares windows |
| `reactive.total` | kvarh | A `reactive` register exists |
| `demand.peak` | kW | The tariff bills demand and interval data exists |
| `demand.ratchet_floor` | kW | A ratchet is configured and history exists |
| `days.served` | day | Always |

Absence and zero are not the same thing. A missing export channel is
genuinely zero export; a missing energy channel is not zero usage, and the
engine will not silently collapse the second into the first.
