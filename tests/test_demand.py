"""Peak demand, demand windows and the ratchet."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.units import Unit
from meterline.errors import MeterDataError
from meterline.meterdata.demand import (
    effective_window,
    peak_demand,
    ratchet_floor,
)
from meterline.model.quality import QualityCode
from meterline.model.series import IntervalSeries
from meterline.policy.conventions import DemandMethod, RatchetBasis
from meterline.timeline.calendars import MonthKey
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span


def series(values: list[str], minutes: int = 15) -> IntervalSeries:
    """Build a series starting at midnight on 1 June 2025."""

    return IntervalSeries(
        "ch-1", utc(2025, 6, 1), minutes, tuple(Decimal(value) for value in values)
    )


class PeakDemandTests(unittest.TestCase):
    def setUp(self) -> None:
        # Four quarter-hours: a burst in the second and third.
        self.series = series(["1", "5", "5", "1"])
        self.span = Span(utc(2025, 6, 1), utc(2025, 6, 1, 1))

    def test_the_highest_interval_scales_to_an_hourly_rate(self) -> None:
        peak = peak_demand(
            self.series, self.span, method=DemandMethod.HIGHEST_INTERVAL
        )
        self.assertEqual(peak.value, Decimal("20"))

    def test_a_block_window_averages_across_the_block(self) -> None:
        peak = peak_demand(
            self.series, self.span, method=DemandMethod.BLOCK, window_minutes=30
        )
        self.assertEqual(peak.value, Decimal("12"))

    def test_a_rolling_window_finds_the_burst_the_blocks_split(self) -> None:
        peak = peak_demand(
            self.series, self.span, method=DemandMethod.ROLLING, window_minutes=30
        )
        self.assertEqual(peak.value, Decimal("20"))

    def test_rolling_is_never_below_block(self) -> None:
        block = peak_demand(
            self.series, self.span, method=DemandMethod.BLOCK, window_minutes=30
        )
        rolling = peak_demand(
            self.series, self.span, method=DemandMethod.ROLLING, window_minutes=30
        )
        self.assertGreaterEqual(rolling.value, block.value)

    def test_a_window_that_is_not_a_whole_number_of_intervals_raises(self) -> None:
        with self.assertRaises(MeterDataError):
            peak_demand(self.series, self.span, window_minutes=20)

    def test_no_overlapping_intervals_gives_a_missing_peak(self) -> None:
        away = Span(utc(2025, 7, 1), utc(2025, 7, 2))
        peak = peak_demand(self.series, away)
        self.assertTrue(peak.is_zero)
        self.assertIs(peak.quality, QualityCode.MISSING)

    def test_the_peak_records_where_it_was_found(self) -> None:
        peak = peak_demand(
            self.series, self.span, method=DemandMethod.HIGHEST_INTERVAL
        )
        self.assertIsNotNone(peak.span)
        self.assertEqual(peak.span.start, utc(2025, 6, 1, 0, 15))

    def test_the_peak_quantity_is_in_kilowatts(self) -> None:
        peak = peak_demand(self.series, self.span)
        self.assertIs(peak.quantity.unit, Unit.KW)


class WindowWideningTests(unittest.TestCase):
    def test_a_window_finer_than_the_data_widens(self) -> None:
        hourly = series(["1"] * 24, minutes=60)
        window, note = effective_window(hourly, 15)
        self.assertEqual(window, 60)
        self.assertIn("60-minute", note)

    def test_a_window_that_is_a_multiple_passes_through(self) -> None:
        quarter = series(["1"] * 96)
        window, note = effective_window(quarter, 30)
        self.assertEqual(window, 30)
        self.assertEqual(note, "")

    def test_a_window_that_is_not_a_multiple_rounds_up(self) -> None:
        quarter = series(["1"] * 96)
        window, note = effective_window(quarter, 20)
        self.assertEqual(window, 30)
        self.assertIn("30 minutes", note)


class RatchetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.month = MonthKey(2025, 6)
        self.history = {
            MonthKey(2025, 5): Decimal("40"),
            MonthKey(2023, 8): Decimal("120"),
            MonthKey(2025, 1): Decimal("90"),
        }

    def test_no_ratchet_remembers_nothing(self) -> None:
        self.assertEqual(
            ratchet_floor(self.history, self.month, basis=RatchetBasis.NONE),
            Decimal("0"),
        )

    def test_the_annual_ratchet_finds_the_highest_recent_peak(self) -> None:
        floor = ratchet_floor(
            self.history, self.month, basis=RatchetBasis.ANNUAL_PEAK
        )
        self.assertEqual(floor, Decimal("90"))

    def test_the_lookback_excludes_the_current_month(self) -> None:
        history = dict(self.history)
        history[self.month] = Decimal("500")
        floor = ratchet_floor(history, self.month, basis=RatchetBasis.ANNUAL_PEAK)
        self.assertEqual(floor, Decimal("90"))

    def test_a_longer_lookback_reaches_further_back(self) -> None:
        floor = ratchet_floor(
            self.history,
            self.month,
            basis=RatchetBasis.ANNUAL_PEAK,
            lookback_months=36,
        )
        self.assertEqual(floor, Decimal("120"))

    def test_a_seasonal_ratchet_ignores_other_seasons(self) -> None:
        floor = ratchet_floor(
            self.history,
            self.month,
            basis=RatchetBasis.SEASON_PEAK,
            lookback_months=36,
            season_months=(6, 7, 8, 9),
        )
        self.assertEqual(floor, Decimal("120"))

    def test_a_contract_ratchet_ignores_history(self) -> None:
        floor = ratchet_floor(
            self.history,
            self.month,
            basis=RatchetBasis.CONTRACT,
            contract_kw=Decimal("75"),
        )
        self.assertEqual(floor, Decimal("75"))

    def test_no_history_means_no_floor(self) -> None:
        self.assertEqual(
            ratchet_floor({}, self.month, basis=RatchetBasis.ANNUAL_PEAK), Decimal("0")
        )


if __name__ == "__main__":
    unittest.main()
