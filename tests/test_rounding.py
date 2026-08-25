"""Rounding conventions, and the increments they snap to."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.decimals import D, clamp, is_zero, mean, safe_divide, sign
from meterline.core.rounding import (
    RoundingMode,
    exponent_for,
    quantize,
    round_to_increment,
)
from meterline.errors import ConfigurationError, QuantityError


class DecimalHelperTests(unittest.TestCase):
    def test_floats_go_through_repr_not_binary(self) -> None:
        self.assertEqual(D(0.1), Decimal("0.1"))

    def test_empty_strings_are_rejected(self) -> None:
        with self.assertRaises(QuantityError):
            D("   ")

    def test_nonsense_strings_are_rejected(self) -> None:
        with self.assertRaises(QuantityError):
            D("twelve")

    def test_division_by_zero_returns_the_default(self) -> None:
        self.assertEqual(safe_divide(D(1), D(0), default=D(-1)), D(-1))

    def test_sign_uses_the_zero_tolerance(self) -> None:
        self.assertEqual(sign(D("0.0000001")), 0)
        self.assertEqual(sign(D("-1")), -1)

    def test_mean_of_nothing_is_zero(self) -> None:
        self.assertTrue(is_zero(mean([])))

    def test_clamp_bounds_on_both_sides(self) -> None:
        self.assertEqual(clamp(D(5), D(1), D(3)), D(3))
        self.assertEqual(clamp(D(0), D(1), D(3)), D(1))
        self.assertEqual(clamp(D(2), None, None), D(2))


class RoundingModeTests(unittest.TestCase):
    def test_every_mode_has_a_decimal_equivalent(self) -> None:
        for mode in RoundingMode:
            self.assertTrue(mode.decimal_rounding.startswith("ROUND_"))

    def test_ties_go_different_ways(self) -> None:
        value = Decimal("2.5")
        self.assertEqual(quantize(value, 0, RoundingMode.HALF_UP), Decimal("3"))
        self.assertEqual(quantize(value, 0, RoundingMode.HALF_EVEN), Decimal("2"))
        self.assertEqual(quantize(value, 0, RoundingMode.HALF_DOWN), Decimal("2"))

    def test_customer_friendly_modes_are_labelled(self) -> None:
        self.assertTrue(RoundingMode.FLOOR.favours_customer)
        self.assertFalse(RoundingMode.CEILING.favours_customer)

    def test_negative_places_are_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            exponent_for(-1)


class IncrementTests(unittest.TestCase):
    def test_snapping_to_a_nickel(self) -> None:
        self.assertEqual(
            round_to_increment(Decimal("10.13"), Decimal("0.05")), Decimal("10.15")
        )

    def test_a_zero_increment_does_nothing(self) -> None:
        self.assertEqual(
            round_to_increment(Decimal("10.13"), Decimal("0")), Decimal("10.13")
        )

    def test_a_negative_increment_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            round_to_increment(Decimal("1"), Decimal("-1"))

    def test_snapping_direction_follows_the_mode(self) -> None:
        self.assertEqual(
            round_to_increment(Decimal("10.11"), Decimal("0.25"), RoundingMode.FLOOR),
            Decimal("10.00"),
        )
        self.assertEqual(
            round_to_increment(Decimal("10.11"), Decimal("0.25"), RoundingMode.CEILING),
            Decimal("10.25"),
        )


if __name__ == "__main__":
    unittest.main()
