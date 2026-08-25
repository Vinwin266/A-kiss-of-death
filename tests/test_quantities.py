"""Quantities carry their units, and refuse to lose them."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.quantity import Quantity, quantity, sum_quantities
from meterline.core.units import Unit, UnitKind, conversion_factor, convertible
from meterline.errors import UnitMismatch


class UnitTests(unittest.TestCase):
    def test_kwh_and_mwh_convert(self) -> None:
        self.assertEqual(conversion_factor(Unit.MWH, Unit.KWH), Decimal("1000"))

    def test_energy_and_power_do_not_convert(self) -> None:
        self.assertFalse(convertible(Unit.KWH, Unit.KW))
        with self.assertRaises(UnitMismatch):
            conversion_factor(Unit.KWH, Unit.KW)

    def test_apparent_power_is_not_real_power(self) -> None:
        self.assertIs(Unit.KVA.kind, UnitKind.POWER)
        self.assertFalse(convertible(Unit.KVA, Unit.KW))

    def test_units_render_as_their_symbol(self) -> None:
        self.assertEqual(str(Unit.KWH), "kWh")
        self.assertEqual(Unit.THERM.label, "therms")


class QuantityTests(unittest.TestCase):
    def test_addition_converts_the_right_operand(self) -> None:
        total = Quantity(Decimal("1"), Unit.MWH) + Quantity(Decimal("500"), Unit.KWH)
        self.assertEqual(total.to(Unit.KWH).value, Decimal("1500.0000000000"))

    def test_addition_across_kinds_raises(self) -> None:
        with self.assertRaises(UnitMismatch):
            Quantity(Decimal("1"), Unit.KWH) + Quantity(Decimal("1"), Unit.KW)

    def test_positive_and_negative_parts_split_a_net_value(self) -> None:
        net = Quantity(Decimal("-40"), Unit.KWH)
        self.assertTrue(net.positive_part().is_zero)
        self.assertEqual(net.negative_part().value, Decimal("40"))

    def test_zero_tolerance_absorbs_tiny_residues(self) -> None:
        self.assertTrue(Quantity(Decimal("0.0000001"), Unit.KWH).is_zero)

    def test_format_uses_the_unit_symbol(self) -> None:
        self.assertEqual(Quantity(Decimal("12"), Unit.KW).format(1), "12.0 kW")

    def test_sum_of_no_quantities_is_zero_in_the_asked_unit(self) -> None:
        total = sum_quantities([], Unit.THERM)
        self.assertIs(total.unit, Unit.THERM)
        self.assertTrue(total.is_zero)

    def test_quantity_helper_converts_when_given_a_quantity(self) -> None:
        converted = quantity(Quantity(Decimal("2"), Unit.MWH), Unit.KWH)
        self.assertEqual(converted.value, Decimal("2000.0000000000"))

    def test_equality_ignores_the_unit_within_a_kind(self) -> None:
        self.assertEqual(
            Quantity(Decimal("1"), Unit.MWH), Quantity(Decimal("1000"), Unit.KWH)
        )


if __name__ == "__main__":
    unittest.main()
