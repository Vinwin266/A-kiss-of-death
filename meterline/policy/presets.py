"""Named profiles that stand for recognisable ways of doing things.

These are not "good" and "bad" configurations.  Each is internally coherent
and each is in production somewhere; they exist so that a test can say "and
under the legacy conventions this bill is $4.18 higher" and mean something.
"""

from __future__ import annotations

from ..core.rounding import RoundingMode
from ..errors import PolicyError
from ..model.enrollment import EnrollmentResolution
from ..model.quality import QualityMergeRule
from ..timeline.daycount import DayCount
from ..timeline.daytypes import DayTypeRules
from .conventions import (
    AssistanceStage,
    BankExpiry,
    CashOutPolicy,
    CreditValuation,
    DemandMethod,
    EstimationStrategy,
    GapPolicy,
    MinimumBasis,
    NegativeBillPolicy,
    ProrationBasis,
    RatchetBasis,
    RolloverPolicy,
    RoundingStage,
    SuspectDataPolicy,
    TaxCompounding,
    TierBasis,
    TrueUpPolicy,
    WindowPrecedence,
)
from .profile import UtilityProfile

__all__ = ["PRESETS", "preset", "preset_names"]


MODEL_RULES = UtilityProfile(
    name="model-rules",
    description=(
        "The conventions a modern regulator tends to write into a tariff "
        "order: prorate everything, net over the cycle, round once."
    ),
    rounding_mode=RoundingMode.HALF_EVEN,
    rounding_stage=RoundingStage.ON_TOTAL,
    proration=ProrationBasis.DAILY_ACTUAL,
    tier_basis=TierBasis.MONTH_PRORATED,
    enrollment_resolution=EnrollmentResolution.SPLIT,
    window_precedence=WindowPrecedence.MOST_SPECIFIC,
    rollover=RolloverPolicy.THRESHOLD,
    gaps=GapPolicy.ESTIMATE,
    estimation=EstimationStrategy.TRAILING_AVERAGE,
    quality_merge=QualityMergeRule.WORST_WINS,
    true_up=TrueUpPolicy.NEXT_ACTUAL,
    minimum_basis=MinimumBasis.ENERGY_AND_FIXED,
    assistance_stage=AssistanceStage.PRE_TAX,
    tax_compounding=TaxCompounding.PARALLEL,
    credit_valuation=CreditValuation.RETAIL,
    bank_expiry=BankExpiry.ANNUAL_TRUE_UP,
    cash_out=CashOutPolicy.ANNUAL_AVOIDED_COST,
)

LEGACY_COOPERATIVE = UtilityProfile(
    name="legacy-cooperative",
    description=(
        "A long-established rural cooperative: nothing is prorated, tiers "
        "are per bill, and rounding happens on every line."
    ),
    rounding_mode=RoundingMode.HALF_UP,
    rounding_stage=RoundingStage.PER_LINE,
    day_count=DayCount.ACTUAL_INCLUSIVE,
    proration=ProrationBasis.FULL_IF_ANY_DAY,
    tier_basis=TierBasis.CYCLE,
    enrollment_resolution=EnrollmentResolution.AT_END,
    window_precedence=WindowPrecedence.FIRST_MATCH,
    rollover=RolloverPolicy.ASSUME_ROLLOVER,
    gaps=GapPolicy.ESTIMATE,
    estimation=EstimationStrategy.PRIOR_PERIOD,
    quality_merge=QualityMergeRule.MEASURED_WINS,
    true_up=TrueUpPolicy.NONE,
    minimum_basis=MinimumBasis.ENERGY_ONLY,
    assistance_stage=AssistanceStage.POST_TAX,
    tax_compounding=TaxCompounding.SEQUENTIAL,
    demand_method=DemandMethod.HIGHEST_INTERVAL,
    ratchet=RatchetBasis.ANNUAL_PEAK,
    ratchet_percent="75",
    credit_valuation=CreditValuation.AVOIDED_COST,
    bank_expiry=BankExpiry.ANNUAL_TRUE_UP,
    cash_out=CashOutPolicy.FORFEIT,
    negative_bill=NegativeBillPolicy.ZERO_FLOOR,
)

STRICT_MUNICIPAL = UtilityProfile(
    name="strict-municipal",
    description=(
        "A municipal utility that refuses to guess: gaps fail the bill, "
        "suspect data is held, and demand uses a rolling window."
    ),
    rounding_mode=RoundingMode.HALF_EVEN,
    rounding_stage=RoundingStage.PER_COMPONENT,
    proration=ProrationBasis.CYCLE_FRACTION,
    tier_basis=TierBasis.DAILY,
    day_types=DayTypeRules(saturday_is_weekend=False),
    rollover=RolloverPolicy.REJECT,
    gaps=GapPolicy.FAIL,
    estimation=EstimationStrategy.ZERO,
    suspect_data=SuspectDataPolicy.HOLD,
    quality_merge=QualityMergeRule.WORST_WINS,
    true_up=TrueUpPolicy.CANCEL_REBILL,
    demand_method=DemandMethod.ROLLING,
    demand_window_minutes=30,
    ratchet=RatchetBasis.SEASON_PEAK,
    ratchet_percent="80",
    minimum_basis=MinimumBasis.ALL_BEFORE_TAX,
    credit_valuation=CreditValuation.PERCENT_OF_RETAIL,
    credit_percent_of_retail="85",
    bank_expiry=BankExpiry.ROLLING_MONTHS,
    bank_rolling_months=6,
    negative_bill=NegativeBillPolicy.REFUND,
)

PERMISSIVE_RETAILER = UtilityProfile(
    name="permissive-retailer",
    description=(
        "A competitive retailer optimising for a bill that never surprises: "
        "estimates fill anything missing and credits never expire."
    ),
    rounding_mode=RoundingMode.FLOOR,
    rounding_stage=RoundingStage.ON_TOTAL,
    proration=ProrationBasis.DAILY_NOMINAL_30,
    tier_basis=TierBasis.NORMALIZED_30,
    enrollment_resolution=EnrollmentResolution.MAJORITY,
    window_precedence=WindowPrecedence.LAST_MATCH,
    rollover=RolloverPolicy.TREAT_AS_RESET,
    gaps=GapPolicy.ZERO_FILL,
    estimation=EstimationStrategy.PROFILE,
    suspect_data=SuspectDataPolicy.ESTIMATE_INSTEAD,
    quality_merge=QualityMergeRule.DOMINANT_SHARE,
    minimum_basis=MinimumBasis.DELIVERY_ONLY,
    assistance_stage=AssistanceStage.PRE_TAX,
    bank_expiry=BankExpiry.NEVER,
    cash_out=CashOutPolicy.NONE,
    negative_bill=NegativeBillPolicy.CARRY_FORWARD,
)


PRESETS: dict[str, UtilityProfile] = {
    profile.name: profile
    for profile in (
        MODEL_RULES,
        LEGACY_COOPERATIVE,
        STRICT_MUNICIPAL,
        PERMISSIVE_RETAILER,
    )
}


def preset(name: str) -> UtilityProfile:
    """Return a preset profile by name."""

    try:
        return PRESETS[name]
    except KeyError:
        raise PolicyError(
            "unknown profile preset",
            name=name,
            known=", ".join(sorted(PRESETS)),
        ) from None


def preset_names() -> list[str]:
    """Return the available preset names, sorted."""

    return sorted(PRESETS)
