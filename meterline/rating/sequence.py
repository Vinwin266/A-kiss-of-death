"""Running a tariff's components in order, and rounding the result.

Two conventions live here.  The first is the order components run in, which
is the tariff's stage numbering.  The second is how many times money is
rounded on the way to a total — once per line, once per component, or once
at the very end — which can move a bill by a few cents and is the single
most common cause of a one-cent difference between two systems.
"""

from __future__ import annotations

from typing import Sequence

from ..charge.context import RatingContext
from ..charge.lineitem import LineItem
from ..core.money import Money
from ..policy.conventions import RoundingStage
from ..policy.profile import UtilityProfile
from ..tariff.model import Tariff

__all__ = ["run_components", "apply_rounding"]


def run_components(context: RatingContext, tariff: Tariff) -> list[LineItem]:
    """Evaluate every component of ``tariff`` in stage order.

    Each component sees the lines produced before it, which is what lets a
    minimum charge or a percentage rider work at all.  A component that
    returns nothing contributes nothing — there is no placeholder line —
    so downstream bases never see a zero that was not charged.
    """

    produced: list[LineItem] = []
    for component in tariff.ordered_components():
        lines = component.compute(context, tuple(produced))
        produced.extend(lines)
    return produced


def apply_rounding(
    lines: Sequence[LineItem], profile: UtilityProfile
) -> list[LineItem]:
    """Round the lines according to the profile's rounding stage."""

    stage = profile.rounding_stage
    places = profile.money_places
    mode = profile.rounding_mode
    if stage is RoundingStage.ON_TOTAL:
        return list(lines)
    if stage is RoundingStage.PER_LINE:
        return [line.rounded(places, mode) for line in lines]

    grouped: dict[str, list[LineItem]] = {}
    order: list[str] = []
    for line in lines:
        key = line.component or line.code
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(line)
    result: list[LineItem] = []
    for key in order:
        members = grouped[key]
        exact = Money.zero(members[0].amount.currency)
        for line in members:
            exact = exact + line.amount
        rounded_total = exact.quantized(places, mode)
        difference = rounded_total - exact
        for index, line in enumerate(members):
            if index == len(members) - 1:
                result.append(line.with_amount(line.amount + difference))
            else:
                result.append(line)
    return result


def round_total(amount: Money, profile: UtilityProfile) -> Money:
    """Round a final total, snapping to the profile's increment."""

    from ..core.decimals import D, is_zero
    from ..core.rounding import round_to_increment

    rounded = amount.quantized(profile.money_places, profile.rounding_mode)
    increment = D(profile.total_increment)
    if is_zero(increment):
        return rounded
    return Money(
        round_to_increment(rounded.amount, increment, profile.rounding_mode),
        amount.currency,
    )
