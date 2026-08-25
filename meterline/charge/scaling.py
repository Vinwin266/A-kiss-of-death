"""Proration and threshold scaling.

Two questions, both answered by policy and both worth a few dollars a bill:
how much of a monthly charge a partial period earns, and how far a block
threshold moves when the cycle is not a month long.
"""

from __future__ import annotations

from decimal import Decimal

from ..constants import BILLING_DAYS_NOMINAL
from ..core.decimals import ONE, D, safe_divide
from ..policy.conventions import ProrationBasis, TierBasis
from .context import RatingContext

__all__ = ["proration_factor", "tier_scale", "describe_proration"]


def proration_factor(context: RatingContext) -> Decimal:
    """Return the multiplier applied to a charge quoted per month.

    The result is 1 for a full month under every convention.  It diverges
    for short periods, and the divergence is the point: under
    :data:`ProrationBasis.FULL_IF_ANY_DAY` a two-day final bill still pays a
    whole month's standing charge, which is legal in some jurisdictions and
    forbidden in others.
    """

    basis = context.profile.proration
    served = context.served_days
    if basis is ProrationBasis.NONE:
        return ONE
    if basis is ProrationBasis.FULL_IF_ANY_DAY:
        return ONE if served > 0 else D(0)
    if basis is ProrationBasis.DAILY_NOMINAL_30:
        return safe_divide(D(served), D(BILLING_DAYS_NOMINAL))
    if basis is ProrationBasis.CYCLE_FRACTION:
        return safe_divide(D(served), D(context.cycle_days), default=ONE)
    return safe_divide(D(served), D(context.days_in_calendar_month))


def tier_scale(context: RatingContext) -> Decimal:
    """Return the multiplier applied to a block threshold.

    Under :data:`TierBasis.CYCLE` this is always 1 and a long cycle keeps
    the cheap first block for longer.  Under the other conventions the
    threshold grows and shrinks with the period, which is the behaviour a
    regulator usually intends when the tariff says "per month".
    """

    basis = context.profile.tier_basis
    days = context.days
    if basis is TierBasis.CYCLE:
        return ONE
    if basis is TierBasis.DAILY:
        return D(days)
    if basis is TierBasis.NORMALIZED_30:
        return safe_divide(D(days), D(BILLING_DAYS_NOMINAL))
    return safe_divide(D(days), D(context.days_in_calendar_month))


def describe_proration(context: RatingContext) -> str:
    """Return a one-line explanation of the proration in force."""

    basis = context.profile.proration
    factor = proration_factor(context)
    if basis is ProrationBasis.NONE:
        return "no proration; the full monthly charge applies"
    if basis is ProrationBasis.FULL_IF_ANY_DAY:
        return "any service in the period earns the full monthly charge"
    if basis is ProrationBasis.DAILY_NOMINAL_30:
        return f"{context.served_days}/30 of a month = {factor}"
    if basis is ProrationBasis.CYCLE_FRACTION:
        return f"{context.served_days}/{context.cycle_days} of the cycle = {factor}"
    return f"{context.served_days}/{context.days_in_calendar_month} of the month = {factor}"
