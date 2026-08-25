"""Export credits, the bank, and what happens to a credit nobody spends."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.charge.classes import ChargeClass
from meterline.core.money import Money
from meterline.policy.conventions import (
    BankExpiry,
    CashOutPolicy,
    CreditValuation,
    NegativeBillPolicy,
)
from meterline.policy.presets import preset
from meterline.rating.bank import CreditBank, MovementKind
from meterline.rating.netting import apply_netting
from meterline.session import Session
from meterline.timeline.calendars import MonthKey

from tests.support import build_dataset, solar_tariff


class BankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = CreditBank("sp-1")

    def test_a_new_bank_is_empty(self) -> None:
        self.assertTrue(self.bank.is_empty)
        self.assertEqual(self.bank.balance, Decimal("0"))

    def test_earning_and_drawing(self) -> None:
        self.bank.earn("40", MonthKey(2025, 1))
        drawn = self.bank.apply("15", MonthKey(2025, 2))
        self.assertEqual(drawn, Decimal("15"))
        self.assertEqual(self.bank.balance, Decimal("25"))

    def test_drawing_more_than_is_there_takes_what_there_is(self) -> None:
        self.bank.earn("10", MonthKey(2025, 1))
        self.assertEqual(self.bank.apply("40", MonthKey(2025, 2)), Decimal("10"))
        self.assertTrue(self.bank.is_empty)

    def test_the_oldest_lot_is_drawn_first(self) -> None:
        self.bank.earn("10", MonthKey(2025, 1))
        self.bank.earn("10", MonthKey(2025, 6))
        self.bank.apply("10", MonthKey(2025, 7))
        self.assertEqual(self.bank.lots, ((MonthKey(2025, 6), Decimal("10")),))

    def test_expiry_removes_the_old_lots_only(self) -> None:
        self.bank.earn("10", MonthKey(2025, 1))
        self.bank.earn("10", MonthKey(2025, 6))
        expired = self.bank.expire_before(MonthKey(2025, 3), MonthKey(2025, 7))
        self.assertEqual(expired, Decimal("10"))
        self.assertEqual(self.bank.balance, Decimal("10"))

    def test_settling_empties_the_bank(self) -> None:
        self.bank.earn("25", MonthKey(2025, 1))
        settled = self.bank.settle(MonthKey(2025, 4), cash_out=True)
        self.assertEqual(settled, Decimal("25"))
        self.assertTrue(self.bank.is_empty)

    def test_every_change_is_recorded(self) -> None:
        self.bank.earn("25", MonthKey(2025, 1))
        self.bank.apply("5", MonthKey(2025, 2))
        self.assertEqual(len(self.bank.movements_of(MovementKind.EARNED)), 1)
        self.assertEqual(len(self.bank.movements_of(MovementKind.APPLIED)), 1)

    def test_earning_nothing_records_nothing(self) -> None:
        self.bank.earn("0", MonthKey(2025, 1))
        self.assertEqual(len(self.bank.movements), 0)


class NettingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = preset("model-rules")
        self.month = MonthKey(2025, 6)

    def _line(self, amount: str):
        from meterline.charge.lineitem import LineItemBuilder

        builder = LineItemBuilder("energy", "Energy", ChargeClass.ENERGY, "energy")
        return builder.seal(Money(Decimal(amount)))

    def test_a_positive_bill_draws_on_the_bank(self) -> None:
        bank = CreditBank("sp-1")
        bank.earn("20", MonthKey(2025, 5))
        result = apply_netting([self._line("50")], bank, self.profile, self.month, "USD")
        codes = [line.code for line in result.lines]
        self.assertIn("bank.applied", codes)
        self.assertTrue(bank.is_empty)

    def test_a_negative_bill_is_banked_by_default(self) -> None:
        bank = CreditBank("sp-1")
        result = apply_netting([self._line("-30")], bank, self.profile, self.month, "USD")
        self.assertEqual(bank.balance, Decimal("30"))
        self.assertIn("bank.carried", [line.code for line in result.lines])

    def test_a_refund_policy_leaves_the_credit_on_the_bill(self) -> None:
        profile = self.profile.with_changes(negative_bill=NegativeBillPolicy.REFUND)
        bank = CreditBank("sp-1")
        result = apply_netting([self._line("-30")], bank, profile, self.month, "USD")
        self.assertTrue(bank.is_empty)
        self.assertIn("rating.bill.refund", result.diagnostics.codes())

    def test_rolling_expiry_removes_stale_credit(self) -> None:
        profile = self.profile.with_changes(
            bank_expiry=BankExpiry.ROLLING_MONTHS, bank_rolling_months=3
        )
        bank = CreditBank("sp-1")
        bank.earn("20", MonthKey(2024, 1))
        result = apply_netting([self._line("50")], bank, profile, self.month, "USD")
        self.assertIn("rating.bank.expired", result.diagnostics.codes())
        self.assertTrue(bank.is_empty)

    def test_the_annual_true_up_cashes_out(self) -> None:
        profile = self.profile.with_changes(
            bank_expiry=BankExpiry.ANNUAL_TRUE_UP,
            cash_out=CashOutPolicy.ANNUAL_AVOIDED_COST,
            true_up_month=6,
        )
        bank = CreditBank("sp-1")
        bank.earn("40", MonthKey(2025, 1))
        result = apply_netting([self._line("10")], bank, profile, self.month, "USD")
        self.assertIn("bank.cash_out", [line.code for line in result.lines])

    def test_the_annual_true_up_can_forfeit_instead(self) -> None:
        profile = self.profile.with_changes(
            bank_expiry=BankExpiry.ANNUAL_TRUE_UP,
            cash_out=CashOutPolicy.FORFEIT,
            true_up_month=6,
        )
        bank = CreditBank("sp-1")
        bank.earn("400", MonthKey(2025, 1))
        result = apply_netting([self._line("10")], bank, profile, self.month, "USD")
        self.assertIn("rating.bank.forfeited", result.diagnostics.codes())
        self.assertTrue(bank.is_empty)

    def test_the_bank_is_drawn_before_the_true_up_settles_it(self) -> None:
        profile = self.profile.with_changes(
            bank_expiry=BankExpiry.ANNUAL_TRUE_UP,
            cash_out=CashOutPolicy.FORFEIT,
            true_up_month=6,
        )
        bank = CreditBank("sp-1")
        bank.earn("40", MonthKey(2025, 1))
        apply_netting([self._line("25")], bank, profile, self.month, "USD")
        forfeited = bank.movements_of(MovementKind.FORFEITED)
        self.assertEqual(forfeited[0].amount, Decimal("15"))


class SolarBillTests(unittest.TestCase):
    def _bills(self, **changes):
        profile = preset("model-rules").with_changes(**changes)
        dataset = build_dataset(
            tariff=solar_tariff(),
            profile=profile,
            steps=(300, 200, 400),
            export_steps=(250, 500, 100),
        )
        return Session.of(dataset).rate_all().value

    def test_exports_appear_as_a_credit(self) -> None:
        invoice = self._bills()[0]
        credit = invoice.line("export")
        self.assertIsNotNone(credit)
        self.assertTrue(credit.is_credit)

    def test_a_month_of_heavy_export_produces_a_credit_bill(self) -> None:
        bills = self._bills()
        self.assertTrue(any("bank.carried" in bill.codes() for bill in bills))

    def test_the_credit_is_carried_into_the_next_bill(self) -> None:
        bills = self._bills()
        self.assertIn("bank.applied", bills[2].codes())

    def test_avoided_cost_credits_less_than_retail(self) -> None:
        retail = self._bills(credit_valuation=CreditValuation.RETAIL)
        avoided = self._bills(credit_valuation=CreditValuation.AVOIDED_COST)
        self.assertLess(retail[0].total.amount, avoided[0].total.amount)

    def test_the_carried_balance_is_reported_on_the_bill(self) -> None:
        bills = self._bills()
        self.assertIsNotNone(bills[0].credit_carried_out)


if __name__ == "__main__":
    unittest.main()
