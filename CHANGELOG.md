# Changelog

All notable changes to meterline. The format loosely follows Keep a
Changelog; versions are dated by the release commit rather than by any
schedule.

## 0.12.0

- `compare` renders the conventions that changed alongside the money.
- Tariff versions are implicitly closed by their successors, so a cycle that
  straddles a rate change is rated once per segment rather than twice in full.
- Enrolments are closed the same way.
- Sequential tax compounding folds already-applied taxes into the base
  explicitly, rather than relying on a basis that excludes them.
- Interval lookups are computed arithmetically instead of by scanning, which
  took the example suite from a hundred seconds to under three.

## 0.11.0

- Budget billing: level payments, a deferred balance, re-levelling on drift
  and settlement in a nominated month.
- Assistance discounts, with pre-tax and post-tax placement as a convention.
- `export` writes a dataset back out as canonical JSON, and the round trip is
  covered by a test.

## 0.10.0

- Credit banking: dated lots, oldest-first draw, rolling expiry, annual
  true-up with cash-out or forfeit.
- Negative-bill policy: carry forward, refund, or clamp at zero.

## 0.9.0

- Demand charges, demand windows (block, rolling, highest interval) and
  ratchets over an annual, seasonal or contractual basis.
- The demand window widens to what the interval data can actually support,
  and says so, rather than refusing the bill.

## 0.8.0

- Time-of-use: windows, seasons, day types, holiday calendars with
  observed-day rules, and three window-precedence conventions.
- Bucketing walks real instants rather than wall-clock minutes, so a
  25-hour autumn day contributes 25 hours of buckets.

## 0.7.0

- Taxes: jurisdictions that nest, percentage, per-unit and flat rules,
  parallel and sequential compounding, partial and capped exemptions.

## 0.6.0

- Meter data validation, estimation strategies and the gap policy.
- Quality codes and four ways to merge them across a period.

## 0.5.0

- Register rollover conventions, register exchanges, and consumption
  apportioned to cycle boundaries.

## 0.4.0

- The rating engine: component stages, three rounding stages, minimum
  charges, riders and export credits.

## 0.3.0

- Tariffs: blocks (marginal and stepped), fixed charges, catalogs and dated
  versions.

## 0.2.0

- Billing cycles, read schedules and read-day shift rules.
- Timezones with explicit daylight-saving rules; no dependency on tzdata.

## 0.1.0

- Money, quantities, units, rounding conventions and diagnostics.
