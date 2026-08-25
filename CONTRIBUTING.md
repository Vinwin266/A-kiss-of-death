# Contributing

## Running things

```
python -m unittest discover -s tests -t .          # the suite
python -m meterline validate --dataset examples/riverside.json
python -m meterline replay   --dataset examples/riverside.json --passes 3
python tools/make_examples.py                      # regenerate the examples
```

No third-party tools are needed for any of it, and none should become
needed. The engine's claim is that the same inputs produce the same bytes
years later; every dependency added underneath it is one more thing that can
quietly change.

## House rules

**Decimals, never floats.** A float that reaches a bill is a defect.
`core.decimals.D` is the one conversion boundary and it is searchable on
purpose.

**Sorted traversal.** Do not iterate a set, or an unsorted dict, when the
order can reach output. `core.ordering` has the helpers.

**No clock, no randomness.** A test enforces this by reading every module.
If you need "now", take it as an argument.

**Diagnostics for data, exceptions for configuration.** A gap in the meter
record is a diagnostic. A tariff with no components is an exception. When in
doubt: could a well-formed dataset produce this? Then it is a diagnostic.

**Conventions go in the profile.** If two competent implementations of the
same rate sheet could disagree about it, it is a convention. Add it to
`policy/conventions.py`, give it a field on `UtilityProfile`, and write its
one-line meaning into `policy/describe.py` — a convention with no explanation
is a configuration flag nobody can find later.

## Adding a component

1. A module under `tariff/components/`, subclassing `Component`.
2. Build lines through `LineItemBuilder` so they arrive with a trace and a
   deterministic id.
3. Register it in `tariff/loader.py`'s `COMPONENT_KINDS`.
4. Add whatever static check it deserves to `tariff/validate.py`.
5. Export it from `tariff/components/__init__.py`.
6. Tests: the ordinary case, the zero case, and the case where the relevant
   convention is set the other way.

## Tests

Assert through public interfaces and observable output — a bill's line codes
and totals, a diagnostic's code, a rendered table — rather than private
helpers or attribute names. Every test datum should be reachable from the
builders in `tests/support.py`; if a fixture hides which read closed which
cycle, it cannot be used to diagnose an off-by-one.

The examples in `examples/` are generated. Edit `tools/make_examples.py` and
re-run it; CI regenerates them and fails on a diff.
