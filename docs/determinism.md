# Determinism

The claim: **the same dataset and the same profile produce the same bytes**,
on any machine, in any year. Everything below is what it takes to hold that
claim up, and how the repository checks it.

## What the engine does not do

| Not used | Why |
| --- | --- |
| `random`, `uuid4` | An identifier that changes between runs makes two bills impossible to diff. |
| `datetime.now()`, `time.time()` | A run stamped with the wall clock cannot be compared byte-for-byte with the same run an hour later. |
| `zoneinfo` / the IANA database | A bill has to be reproducible years later. Rerun a 2019 bill on a machine with 2026 tzdata, in a jurisdiction that abolished daylight saving in between, and every peak hour re-buckets. |
| `float` | `0.1 + 0.2` is not `0.3`, and a rate is not an approximation. |
| Network or filesystem access below `io/` | A dataset is a closed world; the loader is the only door. |

A test asserts the first two directly by reading every module in the package
and refusing `import random`, `datetime.now(`, `time.time(` and `uuid4`.

## What it does instead

**Identifiers are content hashes.** `stable_id("bill", account, start, end)`
is a truncated SHA-256 of the normalised inputs. Two runs produce identical
ids; changing any input changes the id, which makes a diff of two bills point
at exactly what moved.

**Time is explicit.** An instant is always a timezone-aware UTC
`datetime`; a wall-clock time is always naive, plus a `Zone`. Mixing the two
is the bug that puts an hour of usage in the wrong bucket twice a year, so
the type of a value says which it is. Naive datetimes reaching the engine are
refused rather than assumed.

**Zones are data.** A `Zone` is a standard offset plus optional
`DstRule`s expressed as calendar rules — "the second Sunday in March at 02:00
local standard time". The rules live in the repository and are versioned with
everything else.

**Every traversal is sorted.** No part of the codebase iterates a set, or an
unsorted dict, when the order can reach the output. `core/ordering.py` exists
to make the sorted traversal the path of least effort.

**Rounding happens where it is declared.** The rounding stage is a
convention, not a side effect of the order lines happen to be produced in.

**The journal carries no timestamps.** Two runs of the same data produce the
same journal digest, which is what makes the digest worth comparing.

## Daylight saving, concretely

A local day is 23, 24 or 25 hours long, and the engine measures it that way:

```python
zone = common_zone("America/New_York")
zone.day_length_hours(date(2025, 3, 9))   # 23
zone.day_length_hours(date(2025, 11, 2))  # 25
zone.day_length_hours(date(2025, 6, 1))   # 24
```

`Span.local_days` returns each day's *actual* extent, so a cycle containing
an autumn transition has 25 hours in that day's buckets. Time-of-use
bucketing walks real instants and re-derives the wall clock at each step,
rather than turning "14:00 to 19:00" into a span by adding minutes to
midnight — which would silently drop or duplicate an hour.

The repeated hour in autumn is resolved by `fold`; the skipped hour in
spring is either shifted forward past the gap or refused, and the caller
says which.

## Checking it

```
meterline replay --dataset examples/riverside.json --passes 3
```

Rates the dataset three times from scratch and compares the rendered bytes.
CI runs it on both examples, and separately runs the same `compare` command
twice and diffs the two files.

The test suite adds:

- every example rated under every preset, twice, byte-compared;
- bill and line identifiers compared across independent loads of the same
  file;
- rendered and explained bills compared with themselves;
- the dataset fingerprint compared across independent loads;
- the whole suite run three times in CI, to catch ordering that happens to
  work once.

## Where determinism would break first

If a change makes a run non-reproducible, the likely causes, in order:

1. A new identifier built from something other than content.
2. A dict or set iterated without sorting, where the order reaches output.
3. A `float` introduced at a boundary — usually reading JSON without
   `str()`.
4. A default that reads the clock, such as `datetime.now()` in a factory.
5. A dependency added that does any of the above underneath you. There are
   none, and that is the cheapest way to keep it true.
