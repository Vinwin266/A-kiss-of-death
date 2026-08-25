"""Human-readable explanations of what a convention does.

The engine can always say *what* it did; this module is how it says *why*
that was the right thing under the profile in force.  Explanations are kept
next to the conventions rather than in the report layer so that adding a
convention without documenting it is visibly incomplete.
"""

from __future__ import annotations

from ..core.tables import Column, Table
from .conventions import (
    BankExpiry,
    CreditValuation,
    DemandMethod,
    GapPolicy,
    MinimumBasis,
    ProrationBasis,
    RolloverPolicy,
    RoundingStage,
    TierBasis,
    WindowPrecedence,
)
from .profile import UtilityProfile

__all__ = ["explain_convention", "profile_table", "profile_highlights"]


def _key(value: object) -> str:
    """Return a lookup key that cannot collide between two enums.

    Every convention here is a ``str`` enum, so ``ProrationBasis.NONE`` and
    ``TrueUpPolicy.NONE`` compare equal and hash alike.  Keying by the
    enum's own name as well as its value keeps a mapping from silently
    explaining one convention with another's description.
    """

    return f"{type(value).__name__}.{getattr(value, 'value', value)}"


_EXPLANATIONS: dict[str, str] = {
    _key(ProrationBasis.NONE): "monthly charges are never reduced for a short period",
    _key(ProrationBasis.FULL_IF_ANY_DAY): "one day of service is charged as a full month",
    _key(ProrationBasis.DAILY_ACTUAL): "monthly charges divide by the days in the month",
    ProrationBasis.DAILY_NOMINAL_30: "monthly charges divide by 30, whatever the month",
    _key(ProrationBasis.CYCLE_FRACTION): "monthly charges scale to the served fraction of the cycle",
    _key(TierBasis.CYCLE): "block thresholds are per bill and do not move with cycle length",
    _key(TierBasis.DAILY): "block thresholds are per day and grow with the cycle",
    _key(TierBasis.MONTH_PRORATED): "block thresholds scale by cycle days over month days",
    TierBasis.NORMALIZED_30: "block thresholds scale by cycle days over thirty",
    _key(RoundingStage.PER_LINE): "each line item is rounded before it is added up",
    _key(RoundingStage.PER_COMPONENT): "each component's subtotal is rounded, not its lines",
    _key(RoundingStage.ON_TOTAL): "full precision is carried to the total, rounded once",
    _key(RolloverPolicy.ASSUME_ROLLOVER): "a lower reading always means the dial wrapped",
    _key(RolloverPolicy.THRESHOLD): "a lower reading means a wrap only if the usage is plausible",
    _key(RolloverPolicy.TREAT_AS_RESET): "a lower reading means the dial was reset to zero",
    _key(RolloverPolicy.REJECT): "a lower reading stops the bill and asks for an operator",
    _key(GapPolicy.ESTIMATE): "periods without data are estimated and flagged",
    _key(GapPolicy.ZERO_FILL): "periods without data are billed as no usage",
    _key(GapPolicy.EXCLUDE): "periods without data are cut out of the billed span",
    _key(GapPolicy.FAIL): "periods without data prevent a bill",
    _key(MinimumBasis.ENERGY_ONLY): "the minimum charge looks only at energy",
    _key(MinimumBasis.DELIVERY_ONLY): "the minimum charge looks only at delivery charges",
    _key(MinimumBasis.ENERGY_AND_FIXED): "the minimum charge includes the standing charge",
    _key(MinimumBasis.ALL_BEFORE_TAX): "the minimum charge includes everything except tax",
    _key(DemandMethod.HIGHEST_INTERVAL): "billed demand is the single highest interval",
    _key(DemandMethod.BLOCK): "billed demand uses fixed windows aligned to the hour",
    _key(DemandMethod.ROLLING): "billed demand uses a sliding window",
    _key(WindowPrecedence.FIRST_MATCH): "the first matching time-of-use window wins",
    _key(WindowPrecedence.LAST_MATCH): "the last matching time-of-use window wins",
    _key(WindowPrecedence.MOST_SPECIFIC): "the narrowest matching time-of-use window wins",
    _key(CreditValuation.RETAIL): "exports are credited at the full retail rate",
    _key(CreditValuation.AVOIDED_COST): "exports are credited at the avoided-cost rate",
    _key(CreditValuation.PERCENT_OF_RETAIL): "exports are credited at a share of retail",
    _key(BankExpiry.NEVER): "banked credits never expire",
    _key(BankExpiry.ANNUAL_TRUE_UP): "banked credits are settled once a year",
    _key(BankExpiry.ROLLING_MONTHS): "banked credits expire a fixed number of months on",
}


def explain_convention(value: object) -> str:
    """Return a one-line explanation of a convention value."""

    return _EXPLANATIONS.get(_key(value), "")


def profile_table(profile: UtilityProfile) -> Table:
    """Render a profile as a three-column table with explanations."""

    table = Table(
        (
            Column("setting", "setting"),
            Column("value", "value"),
            Column("meaning", "meaning", max_width=52),
        ),
        title=f"conventions: {profile.name}",
    )
    rendered = profile.as_dict()
    for key in sorted(rendered):
        if key in ("name", "description"):
            continue
        raw = getattr(profile, key)
        value = rendered[key]
        if isinstance(value, dict):
            value = ", ".join(f"{k}={v}" for k, v in sorted(value.items()))
        table.add(setting=key, value=str(value), meaning=explain_convention(raw))
    return table


def profile_highlights(profile: UtilityProfile) -> list[str]:
    """Return the handful of settings that move a bill the most."""

    interesting = (
        profile.proration,
        profile.tier_basis,
        profile.rounding_stage,
        profile.minimum_basis,
        profile.gaps,
        profile.credit_valuation,
        profile.bank_expiry,
    )
    lines: list[str] = []
    for value in interesting:
        explanation = explain_convention(value)
        if explanation:
            lines.append(explanation)
    return lines
