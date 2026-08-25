"""Corrections, true-ups and budget billing."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.charge.classes import ChargeClass
from meterline.core.money import Money
from meterline.policy.conventions import TrueUpPolicy
from meterline.policy.presets import preset
from meterline.rating.adjust import (
    cancel_and_rebill,
    combined_total,
    delta_adjustment,
    true_up,
)
from meterline.rating.budget import BudgetPlan, budget_line, recommended_level
from meterline.session import Session
from meterline.timeline.calendars import MonthKey

from tests.support import build_dataset


class AdjustmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = Session.of(build_dataset(steps=(450,))).rate_all().value[0]
        self.replacement = Session.of(build_dataset(steps=(700,))).rate_all().value[0]

    def test_cancel_and_rebill_reverses_every_line(self) -> None:
        result = cancel_and_rebill(self.original, self.replacement)
        reversals = [
            line for line in result.lines if line.charge_class is ChargeClass.ADJUSTMENT
        ]
        self.assertEqual(len(reversals), len(self.original.lines))

    def test_the_reversal_and_the_original_cancel_out(self) -> None:
        result = cancel_and_rebill(self.original, self.replacement)
        reversals = [
            line for line in result.lines if line.charge_class is ChargeClass.ADJUSTMENT
        ]
        total = combined_total(reversals, "USD")
        self.assertEqual(total.amount, -self.original.total.amount)

    def test_a_delta_adjustment_is_a_single_line(self) -> None:
        result = delta_adjustment(self.original, self.replacement)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(
            result.lines[0].amount.amount,
            self.replacement.total.amount - self.original.total.amount,
        )

    def test_an_unchanged_bill_produces_no_adjustment(self) -> None:
        result = delta_adjustment(self.original, self.original)
        self.assertEqual(result.lines, ())
        self.assertFalse(result.is_material)

    def test_the_true_up_policy_selects_the_shape(self) -> None:
        cancel = true_up(
            self.original,
            self.replacement,
            preset("model-rules").with_changes(true_up=TrueUpPolicy.CANCEL_REBILL),
        )
        delta = true_up(
            self.original,
            self.replacement,
            preset("model-rules").with_changes(true_up=TrueUpPolicy.NEXT_ACTUAL),
        )
        self.assertGreater(len(cancel.lines), len(delta.lines))

    def test_no_true_up_posts_nothing(self) -> None:
        result = true_up(
            self.original,
            self.replacement,
            preset("model-rules").with_changes(true_up=TrueUpPolicy.NONE),
        )
        self.assertEqual(result.lines, ())
        self.assertIn("rating.true_up.skipped", result.diagnostics.codes())

    def test_the_difference_is_reported_either_way(self) -> None:
        expected = self.replacement.total - self.original.total
        for policy in TrueUpPolicy:
            result = true_up(
                self.original,
                self.replacement,
                preset("model-rules").with_changes(true_up=policy),
            )
            self.assertEqual(result.difference, expected)


class BudgetTests(unittest.TestCase):
    def test_the_recommended_level_rounds_up(self) -> None:
        history = [Decimal("100.10"), Decimal("100.20"), Decimal("100.30")]
        self.assertEqual(recommended_level(history), Decimal("100.20"))

    def test_no_history_means_no_level(self) -> None:
        self.assertEqual(recommended_level([]), Decimal("0"))

    def test_posting_moves_the_deferred_balance(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"))
        plan.post(Decimal("130"))
        self.assertEqual(plan.deferred_balance, Decimal("30"))
        self.assertTrue(plan.is_behind)

    def test_a_quiet_month_pays_the_balance_down(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"))
        plan.post(Decimal("130"))
        plan.post(Decimal("70"))
        self.assertEqual(plan.deferred_balance, Decimal("0"))

    def test_drift_past_the_threshold_asks_for_a_review(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"), review_threshold=Decimal("20"))
        plan.post(Decimal("200"))
        self.assertTrue(plan.needs_review())

    def test_relevelling_spreads_the_deferred_balance(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"))
        plan.post(Decimal("220"))
        new_level = plan.relevel([Decimal("100")] * 12, remaining_months=12)
        self.assertGreater(new_level, Decimal("100"))

    def test_the_budget_line_defers_the_difference(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"))
        lines, bag = budget_line(plan, Money(Decimal("130")), MonthKey(2025, 3))
        self.assertEqual(lines[0].amount.amount, Decimal("-30"))
        self.assertIn("rating.budget.deferred", bag.codes())

    def test_the_settlement_month_clears_the_balance(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"), settle_month=6)
        plan.post(Decimal("160"))
        lines, bag = budget_line(plan, Money(Decimal("100")), MonthKey(2025, 6))
        self.assertIn("budget.settlement", [line.code for line in lines])
        self.assertEqual(plan.deferred_balance, Decimal("0"))
        self.assertIn("rating.budget.settled", bag.codes())

    def test_budget_lines_are_never_taxable(self) -> None:
        plan = BudgetPlan("bp-1", "ac-1", Decimal("100"))
        lines, _ = budget_line(plan, Money(Decimal("130")), MonthKey(2025, 3))
        self.assertFalse(lines[0].taxable)


if __name__ == "__main__":
    unittest.main()
