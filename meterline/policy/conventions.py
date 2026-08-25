"""The named conventions a utility profile chooses between.

Every enum in this module represents a real disagreement between real
implementations.  The docstrings say what each choice does and, where it is
not obvious, who tends to prefer it — that context is the difference between
a configuration flag and a documented convention.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "AssistanceStage",
    "BankExpiry",
    "CashOutPolicy",
    "CreditValuation",
    "DemandMethod",
    "EstimationStrategy",
    "GapPolicy",
    "MinimumBasis",
    "NegativeBillPolicy",
    "NettingGranularity",
    "ProrationBasis",
    "RatchetBasis",
    "RolloverPolicy",
    "RoundingStage",
    "SuspectDataPolicy",
    "TaxCompounding",
    "TierBasis",
    "TrueUpPolicy",
    "WindowPrecedence",
]


class ProrationBasis(str, Enum):
    """How a charge quoted per month is scaled to a partial period."""

    NONE = "none"
    """Charge the full monthly amount however short the period is."""

    FULL_IF_ANY_DAY = "full_if_any_day"
    """Charge in full if service existed for even one day."""

    DAILY_ACTUAL = "daily_actual"
    """Divide by the days in the containing calendar month, times days served."""

    DAILY_NOMINAL_30 = "daily_nominal_30"
    """Divide by 30 regardless of the month; a 31-day month bills 31/30."""

    CYCLE_FRACTION = "cycle_fraction"
    """Scale by served days over the cycle's own length."""


class TierBasis(str, Enum):
    """How block thresholds respond to the length of the billing period."""

    CYCLE = "cycle"
    """Thresholds are per bill, whatever the cycle length.

    A 35-day cycle therefore gets the same cheap first block as a 26-day
    one, which quietly rewards long cycles.
    """

    DAILY = "daily"
    """Thresholds are quoted per day and multiplied by the cycle length."""

    MONTH_PRORATED = "month_prorated"
    """Thresholds scale by cycle days over days in the calendar month."""

    NORMALIZED_30 = "normalized_30"
    """Thresholds scale by cycle days over 30."""


class RoundingStage(str, Enum):
    """How often money is rounded on the way to a total."""

    PER_LINE = "per_line"
    """Round every line item; the total is the sum of rounded lines."""

    PER_COMPONENT = "per_component"
    """Round each tariff component's subtotal, not its individual lines."""

    ON_TOTAL = "on_total"
    """Carry full precision throughout and round once at the end."""


class MinimumBasis(str, Enum):
    """Which subtotal a minimum charge is compared against."""

    ENERGY_ONLY = "energy_only"
    """Only volumetric energy charges count toward the minimum."""

    DELIVERY_ONLY = "delivery_only"
    """Only delivery-side charges count; supply is excluded."""

    ENERGY_AND_FIXED = "energy_and_fixed"
    """Energy plus the standing charge, which is the common reading."""

    ALL_BEFORE_TAX = "all_before_tax"
    """Everything except taxes, including riders and credits."""


class CreditValuation(str, Enum):
    """What an exported kilowatt-hour is worth."""

    RETAIL = "retail"
    """Full retail rate for the period it was exported in."""

    AVOIDED_COST = "avoided_cost"
    """A separately published wholesale rate."""

    PERCENT_OF_RETAIL = "percent_of_retail"
    """A stated percentage of the retail rate."""


class NettingGranularity(str, Enum):
    """The period over which imports and exports offset each other."""

    CYCLE = "cycle"
    """Net over the whole bill; the most generous to the customer."""

    DAILY = "daily"
    """Net within each local day, banking the remainder."""

    INTERVAL = "interval"
    """Net within each metering interval; the least generous."""


class BankExpiry(str, Enum):
    """What happens to unused export credits over time."""

    NEVER = "never"
    """Credits accumulate indefinitely."""

    ANNUAL_TRUE_UP = "annual_true_up"
    """Credits reset at the anniversary month, subject to a cash-out rule."""

    ROLLING_MONTHS = "rolling_months"
    """Credits expire a fixed number of months after they were earned."""


class CashOutPolicy(str, Enum):
    """What the utility does with a credit balance at a true-up."""

    NONE = "none"
    """Nothing; the balance simply carries on."""

    FORFEIT = "forfeit"
    """The balance is zeroed and the customer receives nothing."""

    ANNUAL_AVOIDED_COST = "annual_avoided_cost"
    """The balance is paid out at the avoided-cost rate."""


class RolloverPolicy(str, Enum):
    """How a dial reading lower than the one before it is interpreted."""

    ASSUME_ROLLOVER = "assume_rollover"
    """Always add one dial width; simple, and wrong for a bad read."""

    THRESHOLD = "threshold"
    """Assume rollover only when the implied usage stays under a bound."""

    TREAT_AS_RESET = "treat_as_reset"
    """Assume the dial was reset; usage is the later value alone."""

    REJECT = "reject"
    """Refuse to derive consumption and require an operator decision."""


class GapPolicy(str, Enum):
    """What to do about a period with no usable meter data."""

    ESTIMATE = "estimate"
    """Fill the gap with the configured estimation strategy."""

    ZERO_FILL = "zero_fill"
    """Treat the gap as no usage, which is not the same as no data."""

    EXCLUDE = "exclude"
    """Bill only the covered part and prorate fixed charges to it."""

    FAIL = "fail"
    """Refuse to produce a bill."""


class EstimationStrategy(str, Enum):
    """How a missing quantity is estimated."""

    PRIOR_PERIOD = "prior_period"
    """Scale the same period one year earlier by the day count."""

    TRAILING_AVERAGE = "trailing_average"
    """Use the average daily usage of the most recent complete cycles."""

    PROFILE = "profile"
    """Shape a total across a stored load profile."""

    ZERO = "zero"
    """Estimate nothing; used to make an estimate visible by its absence."""


class SuspectDataPolicy(str, Enum):
    """What to do with data that failed validation but exists."""

    BILL_ANYWAY = "bill_anyway"
    """Use it and record a diagnostic."""

    ESTIMATE_INSTEAD = "estimate_instead"
    """Discard it and estimate over the same span."""

    HOLD = "hold"
    """Produce no bill and mark the account for review."""


class DemandMethod(str, Enum):
    """How a demand determinant is taken from interval data."""

    HIGHEST_INTERVAL = "highest_interval"
    """The single largest interval, scaled to an hourly rate."""

    BLOCK = "block"
    """Fixed, non-overlapping windows aligned to the hour."""

    ROLLING = "rolling"
    """A sliding window, which can only ever find a higher peak."""


class RatchetBasis(str, Enum):
    """What a demand ratchet remembers."""

    NONE = "none"
    """No ratchet; billed demand is this period's peak."""

    ANNUAL_PEAK = "annual_peak"
    """A percentage of the highest peak in the trailing eleven months."""

    SEASON_PEAK = "season_peak"
    """A percentage of the highest peak in the same season only."""

    CONTRACT = "contract"
    """A percentage of a contracted capacity, ignoring history."""


class AssistanceStage(str, Enum):
    """Where a low-income discount is applied."""

    PRE_TAX = "pre_tax"
    """Reduce the taxable subtotal, so tax falls too."""

    POST_TAX = "post_tax"
    """Apply after tax, so the discount is exactly its stated amount."""


class TaxCompounding(str, Enum):
    """Whether taxes apply to each other."""

    PARALLEL = "parallel"
    """Every tax applies to the same pre-tax base."""

    SEQUENTIAL = "sequential"
    """Each tax applies to the base plus the taxes already added."""


class WindowPrecedence(str, Enum):
    """Which time-of-use window wins when two of them match."""

    FIRST_MATCH = "first_match"
    """The first window listed in the tariff."""

    LAST_MATCH = "last_match"
    """The last window listed, letting later entries override earlier ones."""

    MOST_SPECIFIC = "most_specific"
    """The narrowest window by duration, then by day-type specificity."""


class TrueUpPolicy(str, Enum):
    """What happens when an estimate is later replaced by an actual read."""

    NONE = "none"
    """Nothing; the estimate stands and the difference lands in the next bill."""

    NEXT_ACTUAL = "next_actual"
    """The next bill absorbs the difference as an adjustment line."""

    CANCEL_REBILL = "cancel_rebill"
    """The estimated bill is reversed in full and reissued."""


class NegativeBillPolicy(str, Enum):
    """What to do when a bill totals less than zero."""

    CARRY_FORWARD = "carry_forward"
    """Show the credit and carry it to the next bill."""

    REFUND = "refund"
    """Issue the credit as a refund line."""

    ZERO_FLOOR = "zero_floor"
    """Clamp the bill at zero and bank the remainder."""
