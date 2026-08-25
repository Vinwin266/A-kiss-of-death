# meterline

A deterministic utility metering and tariff rating engine, in pure Python with
no runtime dependencies.

meterline answers two questions about a billing period and shows its working
for both:

- **what was used** — from dial readings and interval data, through rollover,
  register exchanges, validation, estimation and time-of-use bucketing;
- **what that costs** — from a versioned tariff, through blocks, windows,
  demand ratchets, riders, minimum charges, export credits and taxes.

The interesting part is not the arithmetic. It is that almost every step has
more than one defensible answer, and real utilities pick differently. A
30-day cycle that ends in February: does a monthly standing charge get
prorated by 30/28, by 30/31, by 30/30, or not at all? A dial that reads lower
than last month: did it wrap, did it reset, or is the reading wrong? An
export credit larger than the bill: is it banked, refunded, or forfeited at
the next true-up?

meterline names every one of those choices, puts them in an explicit
[`UtilityProfile`](meterline/policy/profile.py), records which profile
produced a bill, and can rate the same data twice to show you the
difference.

```
$ meterline compare --dataset examples/riverside.json --against legacy-cooperative

service point  period      model-rules  legacy-cooperative  difference
-------------  ----------  -----------  ------------------  ----------
sp-100         2025-01-19        94.44               92.03       -2.41
...

net difference: 179.26 USD

conventions that changed:
  - proration: daily_actual -> full_if_any_day — one day of service is charged as a full month
  - tier_basis: month_prorated -> cycle — block thresholds are per bill and do not move with cycle length
  - rounding_stage: on_total -> per_line — each line item is rounded before it is added up
  - minimum_basis: energy_and_fixed -> energy_only — the minimum charge looks only at energy
```

## Determinism

The same dataset and the same profile produce the same bytes, on any machine,
in any year. Nothing in the engine reads the clock, the network, a random
source or the IANA timezone database — daylight-saving rules are data, and
identifiers are content hashes rather than UUIDs. The `replay` command exists
to prove it, and CI runs it on every push:

```
$ meterline replay --dataset examples/riverside.json --passes 3
replay ok: 3 passes produced identical output (195804 bytes each)
```

## Install

```
python -m pip install .
```

Python 3.11 or newer. There are no dependencies to install with it.

## Using it

```
meterline validate --dataset examples/riverside.json     # references and tariffs
meterline rate     --dataset examples/riverside.json     # produce the bills
meterline explain  --dataset examples/tiny.json          # every number, with its working
meterline meters   --dataset examples/riverside.json     # reads, consumption, gaps
meterline tariff   --dataset examples/riverside.json     # describe and check the rate sheets
meterline policy   --profile model-rules                 # what the conventions mean
meterline compare  --dataset examples/tiny.json --against strict-municipal
meterline replay   --dataset examples/tiny.json --passes 3
meterline export   --dataset examples/tiny.json          # canonical JSON, round-trips
```

As a library:

```python
from meterline import Session
from meterline.io.files import load_dataset

session = Session.of(load_dataset("examples/riverside.json"))
outcome = session.rate_all()

for invoice in outcome.value:
    print(invoice.service_point_id, invoice.total, invoice.quality.value)

for diagnostic in outcome.diagnostics.sorted_items():
    print(diagnostic.render())
```

Nothing raises for bad *data*. A gap in the meter record, a dial that went
backwards, a tariff that prices a bucket its windows never produce: all of
those are diagnostics attached to the result, because they are ordinary
outcomes that belong on the bill's record rather than in a traceback. The
engine raises only for bad *configuration* — a tariff with no components, a
naive datetime, two amounts in different currencies.

## How it is put together

```
meterline/
  core/         money, quantities, units, rounding, diagnostics, tables
  timeline/     zones with explicit DST rules, spans, day counts, cycles
  model/        the inert record types: accounts, meters, registers, reads
  policy/       the conventions, the profiles, and what each one means
  charge/       the vocabulary tariffs and the engine share: lines, bases, traces
  tariff/       rate schedules: blocks, windows, seasons, components, versions
  meterdata/    dials to determinants: rollover, gaps, estimation, VEE, demand
  rating/       assembly: sequencing, rounding, netting, adjustments, budgets
  tax/          jurisdictions, rules, exemptions, compounding
  report/       rendering: bills, explanations, meter data, CSV
  io/           the only part that touches a file
  audit/        fingerprints and the run journal
  cli/          one module per command
```

The two halves of the engine are kept strictly apart. `meterdata` decides
what was used; `rating` decides what it costs. They meet at
[`DeterminantSet`](meterline/charge/determinant.py), a bag of named
quantities each carrying its own quality code. A tariff component can only
see that bag — it cannot reach for a meter read, and it cannot decide what
day it is.

More detail in [docs/architecture.md](docs/architecture.md), and a catalogue
of the conventions in [docs/conventions.md](docs/conventions.md).

## Not implemented

Deliberate gaps. Each is a feature the engine plausibly *should* have, is
scoped, and is not there yet; the profile refuses rather than pretending
where the distinction matters (see `UtilityProfile.__post_init__`).

1. **Sub-cycle net metering.** `NettingGranularity.DAILY` and `.INTERVAL`
   are named but only `CYCLE` is implemented. Daily netting needs the import
   and export halves per local day and a bank that moves within a bill.
2. **Coincident-peak demand.** Demand is measured per service point. A
   customer with several points billed on the system coincident peak needs an
   aggregation the engine has no home for yet.
3. **Weather-normalised estimation.** `EstimationStrategy` has prior-period,
   trailing-average and profile shapes. Degree-day driven estimation needs a
   weather series on the premise and a per-customer sensitivity.
4. **Gas volume correction.** `Unit.CCF` and `Unit.THERM` exist and do not
   convert into each other, because doing so needs a heating value and a
   pressure/temperature correction that belong to the meter.
5. **Cascading rebills.** `true_up` corrects one bill against one
   replacement. A corrected read that invalidates six months of estimates
   should walk forward through every affected cycle and re-issue in order.
6. **Time-varying export credits.** `ExportCredit` holds one retail rate and
   one avoided cost. A value-stack schedule prices each hour separately and
   needs the export determinant split by window.
7. **Payment allocation and arrears.** Bills are produced; nothing tracks
   what was paid, in what order arrears age, or how a partial payment is
   split across charge classes.
8. **Prepay metering.** A balance that depletes as usage accrues, with
   friendly-hours disconnection rules, is a different billing model rather
   than a variation on this one.
9. **Interval data import.** Datasets carry interval series inline. A real
   deployment reads them from a meter data management system in a
   format-specific dialect with its own quality-code mapping.
10. **Unbundled supplier bills.** `ChargeSide` splits delivery from supply on
    one bill; issuing two documents to two companies from one rating run is
    not modelled.

## Tests

```
python -m unittest discover -s tests -t .
```

617 tests, no third-party runner, about four seconds. The suite includes a
determinism check that rates every example under every preset and compares
the bytes, and a check that no module in the package imports `random` or
calls `datetime.now()`.

## Licence

MIT. See [LICENSE](LICENSE).
