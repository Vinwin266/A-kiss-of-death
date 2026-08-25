# Conventions

Every setting on a [`UtilityProfile`](../meterline/policy/profile.py) is a
choice that reasonable implementations make differently. This is the
catalogue: what each one does, and where it bites.

Run `meterline policy --profile model-rules` to see the whole set with a
one-line explanation of each, or `meterline policy --profile A --diff B` to
see where two disagree.

## Periods and proration

**`proration`** — how a charge quoted per month is scaled to a partial period.

| Value | A 10-day final bill on a $12 monthly charge |
| --- | --- |
| `none` | $12.00 |
| `full_if_any_day` | $12.00 |
| `daily_actual` | $12 × 10 ÷ days in the calendar month |
| `daily_nominal_30` | $4.00 |
| `cycle_fraction` | $12 × 10 ÷ the cycle's own length |

`daily_actual` divides by the length of the calendar month the period *ends*
in. For a 31-day cycle attributed to February that produces a factor above
one — 31/28 — and the standing charge exceeds a month. This is not a bug; it
is what systems that prorate against the calendar month actually do.
`cycle_fraction` is the convention that cannot exceed one.

**`tier_basis`** — whether a block threshold moves with the cycle length.

Under `cycle` a 35-day cycle gets the same cheap first block as a 26-day one,
which quietly rewards long cycles. Under `daily` the threshold is quoted per
day and multiplied out. `month_prorated` and `normalized_30` scale it by
cycle days over month days, or over thirty.

**`enrollment_resolution`** — how a cycle spanning a tariff change is rated:
`split` each sub-period, or apply the tariff in force `at_start`, `at_end`,
or over the `majority` of days.

**`day_count`** — `actual` counts a half-open range; `actual_inclusive`
counts both endpoints, so "the 1st to the 1st" is 31 days rather than 30.

## Money

**`rounding_mode`** — where ties go. `half_up`, `half_even`, `half_down`,
`up`, `down`, `ceiling`, `floor`. Only the last three are unambiguously in
one party's favour, and the tariff validator can check that claim.

**`rounding_stage`** — how often rounding happens: `per_line`,
`per_component`, or `on_total`. On a bill with six lines this is worth up to
three cents, and it is the single most common cause of a one-cent difference
between two systems rating the same tariff.

**`total_increment`** — snap the total to a nickel, or to a dollar. Zero
disables it.

**`negative_bill`** — a bill that totals below zero is `carry_forward`,
`refund`, or `zero_floor`.

## Meter data

**`rollover`** — a dial that reads lower than the one before it.

| Value | Meaning |
| --- | --- |
| `assume_rollover` | Always add one dial width. Simple, and wrong for a bad read. |
| `threshold` | Accept a wrap only if the implied usage stays under `rollover_threshold_factor` of a dial. |
| `treat_as_reset` | The dial was reset; usage is the later value alone. |
| `reject` | Refuse, and ask an operator. |

**`gaps`** — a period no data covers: `estimate`, `zero_fill`, `exclude`, or
`fail`. Note that `zero_fill` bills a hole as no usage, which is not the same
statement as no data.

**`estimation`** — `prior_period`, `trailing_average`, `profile`, or `zero`.
The last exists to make an estimate visible by its absence.

**`suspect_data`** — data that failed validation but exists:
`bill_anyway`, `estimate_instead`, or `hold`.

**`quality_merge`** — the quality of a whole from the quality of its parts:
`worst_wins`, `dominant_share`, `measured_wins`, or `majority_valid`.
`measured_wins` is how an "estimated" flag quietly disappears from bills that
are mostly guesses.

**`true_up`** — what happens when an estimate is replaced by an actual read:
`none`, `next_actual` (a delta line), or `cancel_rebill` (reverse the whole
bill and reissue).

## Time of use

**`window_precedence`** — two windows both claim 18:00 on a summer weekday.
`first_match` takes declaration order, `last_match` lets later entries
override, `most_specific` takes the narrowest.

**`day_types`** — whether Saturday counts as a weekend day at all, whether a
holiday is distinct from a weekend, and which wins when a holiday falls on
one.

**`holiday_calendar`** — the named set of holidays, and separately the
observed-day rule: `none`, `nearest_weekday`, `following_monday`, or `both`.

Windows are applied to *real time*, not to wall-clock minutes: a 25-hour
autumn day contributes 25 hours of buckets and a 23-hour spring day
contributes 23.

## Demand

**`demand_method`** — `highest_interval` reads the largest single interval;
`block` uses fixed windows aligned to the start of the period; `rolling`
slides one interval at a time and can only ever find a peak at least as high.

**`demand_window_minutes`** — widened automatically when the interval data is
coarser, with a notice, rather than refusing the bill.

**`ratchet`** — `none`, `annual_peak`, `season_peak`, or `contract`, at
`ratchet_percent` over `ratchet_lookback_months`. The lookback excludes the
current month; including it would make the ratchet never bind.

## Charges

**`minimum_basis`** — which subtotal the floor is compared against:
`energy_only`, `delivery_only`, `energy_and_fixed`, or `all_before_tax`. The
same rate-sheet sentence — "a minimum charge of $12.00 per month" — is
implemented all four ways in the field.

**`assistance_stage`** — a discount applied `pre_tax` reduces the tax too; a
discount applied `post_tax` is exactly its stated amount.

**`tax_compounding`** — `parallel` (every rule sees the same base) or
`sequential` (each sees the base plus the taxes already added, in the order
declared on the rule).

## Net metering

**`netting`** — the period over which imports and exports offset. Only
`cycle` is implemented; the profile refuses `daily` and `interval` at retail
valuation rather than producing cycle-netted numbers under another name.

**`credit_valuation`** — `retail`, `avoided_cost`, or
`percent_of_retail`. These differ by a factor of three or more, and it is the
single most contested number in distributed generation.

**`bank_expiry`** — `never`, `annual_true_up` in `true_up_month`, or
`rolling_months`. Under a rolling expiry the bank draws its oldest lot first;
drawing the newest would leave the about-to-expire credit in place, which is
what a single running balance does by accident.

**`cash_out`** — at the true-up: `none`, `forfeit`, or
`annual_avoided_cost`.

## The presets

| Preset | In one line |
| --- | --- |
| `model-rules` | What a modern tariff order tends to say: prorate everything, net over the cycle, round once. |
| `legacy-cooperative` | Nothing is prorated, tiers are per bill, rounding happens on every line. |
| `strict-municipal` | Refuses to guess: gaps fail the bill, suspect data is held, demand is measured on a rolling window. |
| `permissive-retailer` | Optimised for a bill that never surprises: estimates fill anything missing, credits never expire. |
