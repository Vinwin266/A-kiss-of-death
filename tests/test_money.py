"""Money keeps full precision until it is asked not to."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.money import Money, money, total_of
from meterline.core.rounding import RoundingMode
from meterline.errors import CurrencyMismatch


class MoneyArithmeticTests(unittest.TestCase):
    def test_addition_keeps_full_precision(self) -> None:
        left = Money(Decimal("0.005"))
        right = Money(Decimal("0.005"))
        self.assertEqual((left + right).amount, Decimal("0.010"))

    def test_multiplication_does_not_round(self) -> None:
        amount = Money(Decimal("0.084213")) * Decimal("1873")
        self.assertEqual(amount.amount, Decimal("157.730949"))
        self.assertEqual(amount.quantized().amount, Decimal("157.73"))

    def test_rounding_once_differs_from_rounding_twice(self) -> None:
        rate = Decimal("0.084213")
        usage = Decimal("1873")
        once = Money(rate * usage).quantized()
        twice = Money(Decimal("0.0842") * usage).quantized()
        self.assertNotEqual(once, twice)

    def test_currencies_do_not_mix(self) -> None:
        with self.assertRaises(CurrencyMismatch):
            Money(Decimal("1"), "USD") + Money(Decimal("1"), "EUR")

    def test_comparison_across_currencies_raises(self) -> None:
        with self.assertRaises(CurrencyMismatch):
            _ = Money(Decimal("1"), "USD") < Money(Decimal("2"), "EUR")

    def test_equality_is_currency_aware(self) -> None:
        self.assertNotEqual(Money(Decimal("1"), "USD"), Money(Decimal("1"), "EUR"))

    def test_total_of_empty_is_zero(self) -> None:
        self.assertTrue(total_of([], "USD").is_zero)


class MoneyPresentationTests(unittest.TestCase):
    def test_half_up_and_half_even_disagree_on_a_tie(self) -> None:
        amount = Money(Decimal("0.125"))
        self.assertEqual(amount.quantized(2, RoundingMode.HALF_UP).amount, Decimal("0.13"))
        self.assertEqual(
            amount.quantized(2, RoundingMode.HALF_EVEN).amount, Decimal("0.12")
        )

    def test_floor_favours_the_customer(self) -> None:
        amount = Money(Decimal("10.999"))
        self.assertEqual(amount.quantized(2, RoundingMode.FLOOR).amount, Decimal("10.99"))
        self.assertEqual(
            amount.quantized(2, RoundingMode.CEILING).amount, Decimal("11.00")
        )

    def test_credits_render_with_a_leading_minus(self) -> None:
        self.assertEqual(Money(Decimal("-4.5")).format(), "-4.50")

    def test_minor_units_round_half_up(self) -> None:
        self.assertEqual(Money(Decimal("1.005")).minor_units(), 101)

    def test_parse_tolerates_symbols_and_separators(self) -> None:
        self.assertEqual(Money.parse("$1,234.50").amount, Decimal("1234.50"))

    def test_money_helper_passes_through_existing_amounts(self) -> None:
        existing = Money(Decimal("3"))
        self.assertIs(money(existing), existing)

    def test_is_credit_only_for_negative_amounts(self) -> None:
        self.assertTrue(Money(Decimal("-0.01")).is_credit)
        self.assertFalse(Money(Decimal("0")).is_credit)


if __name__ == "__main__":
    unittest.main()
