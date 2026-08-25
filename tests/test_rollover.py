"""What a dial that went backwards is taken to mean."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.units import Unit
from meterline.meterdata.rollover import register_delta
from meterline.model.quality import QualityCode, ReadType
from meterline.model.reading import MeterRead
from meterline.model.register import Register
from meterline.policy.conventions import RolloverPolicy
from meterline.policy.profile import UtilityProfile
from meterline.timeline.instants import utc


def read(value: str, day: int = 1, quality: QualityCode = QualityCode.VALID) -> MeterRead:
    """Build a read of the test register."""

    return MeterRead.build(
        "mt-1", "rg-1", utc(2025, 6, day), Decimal(value), ReadType.ACTUAL, quality
    )


class RolloverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.register = Register("rg-1", "mt-1", Unit.KWH, digits=5)

    def _delta(self, policy: RolloverPolicy, earlier: str, later: str, **kwargs):
        profile = UtilityProfile(rollover=policy, **kwargs)
        return register_delta(self.register, read(earlier, 1), read(later, 2), profile)

    def test_an_ordinary_delta_needs_no_policy(self) -> None:
        outcome = self._delta(RolloverPolicy.THRESHOLD, "1000", "1450")
        self.assertEqual(outcome.value.value, Decimal("450"))
        self.assertFalse(outcome.value.rolled_over)
        self.assertEqual(len(outcome.diagnostics), 0)

    def test_assume_rollover_always_adds_a_turn(self) -> None:
        outcome = self._delta(RolloverPolicy.ASSUME_ROLLOVER, "99800", "150")
        self.assertEqual(outcome.value.value, Decimal("350"))
        self.assertTrue(outcome.value.rolled_over)

    def test_threshold_accepts_a_plausible_wrap(self) -> None:
        outcome = self._delta(RolloverPolicy.THRESHOLD, "99800", "150")
        self.assertEqual(outcome.value.value, Decimal("350"))
        self.assertIn("meterdata.rollover.applied", outcome.diagnostics.codes())

    def test_threshold_refuses_an_implausible_wrap(self) -> None:
        # A wrap here would imply 90,100 kWh in a day, well past the half
        # dial the default threshold allows.
        outcome = self._delta(RolloverPolicy.THRESHOLD, "10000", "100")
        self.assertEqual(outcome.value.value, Decimal("0"))
        self.assertIs(outcome.value.quality, QualityCode.SUSPECT)
        self.assertIn("meterdata.rollover.implausible", outcome.diagnostics.codes())

    def test_a_generous_threshold_accepts_the_same_wrap(self) -> None:
        outcome = self._delta(
            RolloverPolicy.THRESHOLD, "10000", "100", rollover_threshold_factor="0.95"
        )
        self.assertEqual(outcome.value.value, Decimal("90100"))

    def test_treat_as_reset_bills_the_later_value(self) -> None:
        outcome = self._delta(RolloverPolicy.TREAT_AS_RESET, "99800", "150")
        self.assertEqual(outcome.value.value, Decimal("150"))
        self.assertIs(outcome.value.quality, QualityCode.SUSPECT)

    def test_reject_produces_an_error_and_no_usage(self) -> None:
        outcome = self._delta(RolloverPolicy.REJECT, "99800", "150")
        self.assertTrue(outcome.diagnostics.has_errors)
        self.assertIs(outcome.value.quality, QualityCode.MISSING)
        self.assertFalse(outcome.value.is_usable)

    def test_the_multiplier_is_applied_after_the_wrap(self) -> None:
        register = Register("rg-1", "mt-1", Unit.KWH, digits=5, multiplier="40")
        profile = UtilityProfile(rollover=RolloverPolicy.ASSUME_ROLLOVER)
        outcome = register_delta(register, read("99800"), read("150", 2), profile)
        self.assertEqual(outcome.value.value, Decimal("14000"))

    def test_the_weaker_endpoint_sets_the_quality(self) -> None:
        profile = UtilityProfile()
        outcome = register_delta(
            self.register,
            read("1000", 1, QualityCode.ESTIMATED),
            read("1450", 2),
            profile,
        )
        self.assertIs(outcome.value.quality, QualityCode.ESTIMATED)


class RegisterTests(unittest.TestCase):
    def test_rollover_point_follows_the_digit_count(self) -> None:
        self.assertEqual(
            Register("r", "m", Unit.KWH, digits=4).rollover_at, Decimal("10000")
        )

    def test_decimal_places_reduce_the_whole_part(self) -> None:
        register = Register("r", "m", Unit.KWH, digits=5, decimals=1)
        self.assertEqual(register.rollover_at, Decimal("10000"))

    def test_a_register_describes_itself(self) -> None:
        register = Register(
            "r", "m", Unit.KWH, digits=5, multiplier="40", tou_bucket="peak"
        )
        described = register.describe()
        self.assertIn("x40", described)
        self.assertIn("peak", described)


if __name__ == "__main__":
    unittest.main()
