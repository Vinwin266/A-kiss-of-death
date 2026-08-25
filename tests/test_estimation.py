"""Estimating usage for a period with no data."""

from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal

from meterline.core.quantity import Quantity
from meterline.core.units import Unit
from meterline.meterdata.consumption import Consumption
from meterline.meterdata.estimate import EstimationInput, estimate_span
from meterline.meterdata.shapes import (
    COMMERCIAL_SHAPE,
    FLAT_SHAPE,
    RESIDENTIAL_SHAPE,
    shape,
)
from meterline.model.quality import QualityCode
from meterline.policy.conventions import EstimationStrategy
from meterline.policy.profile import UtilityProfile
from meterline.timeline.daytypes import DayType
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span
from meterline.timeline.zones import common_zone
from meterline.errors import MeterDataError


def history(daily: str, periods: int = 3, days: int = 30) -> list[Consumption]:
    """Return a run of prior periods at a constant daily rate."""

    records: list[Consumption] = []
    start = utc(2025, 1, 1)
    for index in range(periods):
        opening = start + timedelta(days=days * index)
        closing = opening + timedelta(days=days)
        records.append(
            Consumption(
                Span(opening, closing),
                Quantity(Decimal(daily) * days, Unit.KWH),
            )
        )
    return records


class EstimationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.span = Span(utc(2025, 6, 1), utc(2025, 6, 11))

    def test_the_trailing_average_scales_by_days(self) -> None:
        profile = UtilityProfile(estimation=EstimationStrategy.TRAILING_AVERAGE)
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput(tuple(history("10")))
        )
        self.assertEqual(outcome.value.quantity.value, Decimal("100"))
        self.assertIs(outcome.value.quality, QualityCode.ESTIMATED)

    def test_the_zero_strategy_makes_the_absence_visible(self) -> None:
        profile = UtilityProfile(estimation=EstimationStrategy.ZERO)
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput(tuple(history("10")))
        )
        self.assertTrue(outcome.value.quantity.is_zero)
        self.assertIn("meterdata.estimate.zero", outcome.diagnostics.codes())

    def test_no_history_produces_an_error(self) -> None:
        profile = UtilityProfile()
        outcome = estimate_span(self.span, Unit.KWH, profile, EstimationInput())
        self.assertTrue(outcome.diagnostics.has_errors)
        self.assertTrue(outcome.value.quantity.is_zero)

    def test_prior_period_falls_back_when_a_year_ago_is_missing(self) -> None:
        profile = UtilityProfile(estimation=EstimationStrategy.PRIOR_PERIOD)
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput(tuple(history("10")))
        )
        self.assertIn(
            "meterdata.estimate.no_prior_period", outcome.diagnostics.codes()
        )
        self.assertEqual(outcome.value.quantity.value, Decimal("100"))

    def test_prior_period_uses_last_year_when_it_exists(self) -> None:
        last_year = Consumption(
            Span(self.span.start - timedelta(days=365), self.span.end - timedelta(days=365)),
            Quantity(Decimal("450"), Unit.KWH),
        )
        profile = UtilityProfile(estimation=EstimationStrategy.PRIOR_PERIOD)
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput((last_year,))
        )
        self.assertEqual(outcome.value.quantity.value, Decimal("450"))
        self.assertIn("meterdata.estimate.prior_period", outcome.diagnostics.codes())

    def test_suspect_history_is_not_used(self) -> None:
        records = [
            record.with_quality(QualityCode.SUSPECT) for record in history("10")
        ]
        profile = UtilityProfile()
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput(tuple(records))
        )
        self.assertTrue(outcome.diagnostics.has_errors)

    def test_the_lookback_limits_how_far_back_it_reaches(self) -> None:
        records = history("10", periods=2) + history("40", periods=1)
        profile = UtilityProfile(estimation_lookback_cycles=1)
        outcome = estimate_span(
            self.span, Unit.KWH, profile, EstimationInput(tuple(records))
        )
        self.assertEqual(outcome.value.quantity.value, Decimal("400"))

    def test_an_absurdly_long_period_is_refused(self) -> None:
        span = Span(utc(2020, 1, 1), utc(2025, 1, 1))
        outcome = estimate_span(
            span, Unit.KWH, UtilityProfile(), EstimationInput(tuple(history("10")))
        )
        self.assertIn("meterdata.estimate.too_long", outcome.diagnostics.codes())

    def test_the_profile_strategy_preserves_the_total(self) -> None:
        profile = UtilityProfile(estimation=EstimationStrategy.PROFILE)
        inputs = EstimationInput(
            tuple(history("10")), common_zone("America/New_York"), None, RESIDENTIAL_SHAPE
        )
        outcome = estimate_span(self.span, Unit.KWH, profile, inputs)
        self.assertAlmostEqual(
            float(outcome.value.quantity.value), 100.0, places=6
        )


class LoadShapeTests(unittest.TestCase):
    def test_a_flat_shape_gives_every_hour_the_same_share(self) -> None:
        self.assertEqual(
            FLAT_SHAPE.hour_share(DayType.WEEKDAY, 3),
            FLAT_SHAPE.hour_share(DayType.WEEKDAY, 18),
        )

    def test_a_residential_shape_peaks_in_the_evening(self) -> None:
        self.assertGreater(
            RESIDENTIAL_SHAPE.hour_share(DayType.WEEKDAY, 18),
            RESIDENTIAL_SHAPE.hour_share(DayType.WEEKDAY, 3),
        )

    def test_a_commercial_shape_peaks_in_the_afternoon(self) -> None:
        self.assertGreater(
            COMMERCIAL_SHAPE.hour_share(DayType.WEEKDAY, 13),
            COMMERCIAL_SHAPE.hour_share(DayType.WEEKDAY, 20),
        )

    def test_holidays_fall_back_to_the_weekend_profile(self) -> None:
        self.assertEqual(
            COMMERCIAL_SHAPE.hours_for(DayType.HOLIDAY),
            COMMERCIAL_SHAPE.hours_for(DayType.WEEKEND),
        )

    def test_allocation_preserves_the_total(self) -> None:
        days = [(None, DayType.WEEKDAY), (None, DayType.WEEKEND)]
        allocated = COMMERCIAL_SHAPE.allocate(Decimal("100"), days)
        self.assertAlmostEqual(float(sum(allocated)), 100.0, places=6)
        self.assertGreater(allocated[0], allocated[1])

    def test_allocation_of_nothing_is_empty(self) -> None:
        self.assertEqual(FLAT_SHAPE.allocate(Decimal("10"), []), [])

    def test_a_shape_needs_twenty_four_weights(self) -> None:
        with self.assertRaises(MeterDataError):
            type(FLAT_SHAPE)("bad", tuple(Decimal("1") for _ in range(12)))

    def test_unknown_shapes_are_reported(self) -> None:
        with self.assertRaises(MeterDataError):
            shape("nonesuch")


if __name__ == "__main__":
    unittest.main()
