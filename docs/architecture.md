# Architecture

## The two halves

The engine has exactly one seam that matters, and everything else is
arranged around it.

```
reads, interval data          determinants              line items
        │                          │                        │
   meterdata/  ───────────►  charge/DeterminantSet  ────►  tariff/ + rating/
   "what was used"                                        "what that costs"
```

`meterdata` produces named quantities. `tariff` prices them. Neither imports
the other. The reason is not tidiness: the two halves fail differently. A
rating bug produces an obviously wrong number — a $4,000 residential bill.
A meter-data bug produces a plausible one, and plausible wrong numbers are
the ones that reach a customer.

A tariff component receives a
[`RatingContext`](../meterline/charge/context.py) and nothing else. It cannot
read a meter, cannot decide what day it is, and cannot consult a policy other
than the one the bill is being produced under. Everything it produces is in
the line items it returns.

## Package dependencies

The import graph is a tree, checked by the fact that each package imports
only from those above it:

```
core        money, quantities, units, rounding, ids, diagnostics, tables
  ↑
timeline    zones, spans, day counts, holidays, cycles
  ↑
model       accounts, premises, meters, registers, reads, series
  ↑
policy      conventions, profiles, presets
  ↑
charge      line items, determinants, bases, traces, contexts, scaling
  ↑
tariff      components, windows, seasons, schedules, catalog
  ↑
meterdata   rollover, derivation, gaps, estimation, validation, demand
  ↑
rating      sequencing, netting, banking, adjustments, budgets
tax         jurisdictions, rules, exemptions
  ↑
report      rendering    io   files    audit   journal
  ↑
cli         one module per command
```

`charge` exists to break what would otherwise be a cycle: both `tariff` and
`rating` need the same nouns — a line item, a subtotal basis, a trace — and
neither should own them.

## The dataset is a closed world

[`Dataset`](../meterline/dataset.py) holds everything a run reads. Loading
one and rating from it touches no file, no network and no clock. The loader
in `io/` is the only place a path is opened, and it produces a plain
in-memory dataset — the same object a test assembles by hand. That is what
lets the suite avoid fixtures without diverging from the path the CLI takes.

## Diagnostics rather than exceptions

Data problems are diagnostics; configuration problems are exceptions.

| Situation | What happens |
| --- | --- |
| A gap in the meter record | `meterdata.gap` warning, then the gap policy |
| A dial that went backwards | `meterdata.rollover.*`, per the rollover policy |
| A tariff bucket with no usage | `tariff.tou.missing_bucket` notice |
| A premise in an unknown jurisdiction | `rating.tax.unknown_jurisdiction` error, no tax |
| A tariff with no components | `TariffError` |
| A naive datetime | `TimelineError` |
| Two currencies added together | `CurrencyMismatch` |

Every diagnostic carries a stable dotted code. Codes are part of the public
surface and safe to branch on; messages are not.

Results come back as an [`Outcome`](../meterline/core/outcome.py): a value
paired with the diagnostics produced while computing it. Pairing them is
deliberate — neither can be dropped by accident.

## Determinism, mechanically

- Identifiers are SHA-256 content hashes, never UUIDs.
- Money is `Decimal` throughout; no float reaches a bill.
- Every traversal is over a sorted collection.
- Timezone rules are data in the repository, not a lookup in a database that
  ships with the operating system.
- The audit journal carries no timestamps, so two runs of the same data
  produce the same journal digest.

See [determinism.md](determinism.md).

## Where a change usually goes

| You want to… | Touch |
| --- | --- |
| Add a charge shape | `tariff/components/`, the loader registry, the validator |
| Add a convention | `policy/conventions.py`, `policy/profile.py`, `policy/describe.py`, the code that reads it |
| Add a determinant | `meterdata/determinants.py`, and whatever prices it |
| Change how a bill looks | `report/` only — nothing there computes a number |
| Add a command | `cli/commands/`, `cli/args.py`, the handler table |
