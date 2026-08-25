"""Budget billing: paying a level amount and settling the difference.

A budget plan replaces the amount due with a levelised figure and tracks the
difference in a deferred balance.  Two conventions decide how it behaves:
how the level amount is recomputed as the deferred balance drifts, and when
the balance is settled.  Getting the first wrong produces a plan that never
converges and a customer who owes four hundred dollars in November.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from ..charge.classes import ChargeClass, ChargeSide
from ..charge.lineitem import LineItem, LineItemBuilder
from ..core.decimals import ZERO, D, dsum, safe_divide
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.money import Money
from ..core.rounding import RoundingMode, quantize
from ..timeline.calendars import MonthKey

__all__ = ["BudgetPlan", "budget_line", "recommended_level"]


def recommended_level(
    history: Sequence[Decimal], months: int = 12, places: int = 2
) -> Decimal:
    """Return the level payment implied by a run of past bills.

    The mean of the trailing year, rounded up to the nearest currency unit.
    Rounding up rather than to nearest is deliberate: a plan that slightly
    over-collects settles to a credit, and a credit is a much easier
    conversation than a catch-up bill.
    """

    recent = list(history)[-months:]
    if not recent:
        return ZERO
    average = safe_divide(dsum(recent), D(len(recent)))
    return quantize(average, places, RoundingMode.CEILING)


@dataclass(slots=True)
class BudgetPlan:
    """A levelised payment plan and its deferred balance."""

    plan_id: str
    account_id: str
    level_amount: Decimal
    deferred_balance: Decimal = ZERO
    started: MonthKey | None = None
    settle_month: int = 6
    """Calendar month in which the deferred balance is settled."""

    review_threshold: Decimal = D("50")
    """Deferred balance beyond which the level amount is recomputed."""

    months_elapsed: int = 0

    @property
    def is_behind(self) -> bool:
        """Return ``True`` when the customer has under-paid so far."""

        return self.deferred_balance > ZERO

    def post(self, actual: Decimal) -> Decimal:
        """Record a cycle's actual charges, returning the amount billed."""

        self.deferred_balance += actual - self.level_amount
        self.months_elapsed += 1
        return self.level_amount

    def needs_review(self) -> bool:
        """Return ``True`` when the deferred balance has drifted too far."""

        return abs(self.deferred_balance) > self.review_threshold

    def relevel(self, history: Sequence[Decimal], remaining_months: int = 12) -> Decimal:
        """Recompute the level amount, spreading the deferred balance."""

        base = recommended_level(history)
        spread = safe_divide(self.deferred_balance, D(max(remaining_months, 1)))
        self.level_amount = quantize(base + spread, 2, RoundingMode.CEILING)
        return self.level_amount

    def settle(self) -> Decimal:
        """Empty the deferred balance, returning the amount settled."""

        amount = self.deferred_balance
        self.deferred_balance = ZERO
        self.months_elapsed = 0
        return amount

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{self.plan_id}: {self.level_amount} per month, "
            f"deferred {self.deferred_balance}"
        )


def budget_line(
    plan: BudgetPlan,
    actual_total: Money,
    month: MonthKey,
) -> tuple[list[LineItem], DiagnosticBag]:
    """Return the lines that turn an actual bill into a budget bill."""

    bag = DiagnosticBag()
    currency = actual_total.currency
    billed = plan.post(actual_total.amount)
    difference = actual_total.amount - billed
    lines: list[LineItem] = []

    builder = LineItemBuilder(
        "budget.deferral",
        "Budget billing deferral",
        ChargeClass.ADJUSTMENT,
        "budget",
        ChargeSide.OTHER,
    )
    builder.exempt()
    builder.note("actual charges", "", actual_total.format())
    builder.note("level amount", "", billed)
    builder.note("deferred balance", "", plan.deferred_balance)
    lines.append(builder.seal(Money(-difference, currency)))
    bag.emit(
        "rating.budget.deferred",
        "the difference between actual and level charges was deferred",
        Severity.NOTICE,
        plan.account_id,
        actual=actual_total.format(),
        level=str(billed),
        balance=str(plan.deferred_balance),
    )

    if month.month == plan.settle_month and plan.deferred_balance != ZERO:
        settled = plan.settle()
        settle_builder = LineItemBuilder(
            "budget.settlement",
            "Budget billing settlement",
            ChargeClass.ADJUSTMENT,
            "budget",
            ChargeSide.OTHER,
        )
        settle_builder.exempt()
        settle_builder.note("settled balance", "", settled)
        lines.append(settle_builder.seal(Money(settled, currency)))
        bag.emit(
            "rating.budget.settled",
            "the deferred balance was settled on this bill",
            Severity.NOTICE,
            plan.account_id,
            amount=str(settled),
        )
    elif plan.needs_review():
        bag.emit(
            "rating.budget.review",
            "the deferred balance has drifted past the review threshold",
            Severity.WARNING,
            plan.account_id,
            balance=str(plan.deferred_balance),
            threshold=str(plan.review_threshold),
        )
    return lines, bag
