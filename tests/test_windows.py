"""Time-of-use windows, seasons and bucket assignment."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

from meterline.errors import TariffError
from meterline.policy.conventions import WindowPrecedence
from meterline.tariff.seasons import Season, SeasonSet
from meterline.tariff.windows import (
    TimeWindow,
    WindowSet,
    bucket_at,
    bucket_spans,
    parse_clock,
)
from meterline.timeline.daytypes import DayType
from meterline.timeline.holidays import us_federal_calendar
from meterline.timeline.spans import Span
from meterline.timeline.zones import common_zone

ZONE = common_zone("America/New_York")


class ClockTests(unittest.TestCase):
    def test_clock_strings_become_minutes(self) -> None:
        self.assertEqual(parse_clock("14:30"), 870)

    def test_midnight_at_the_end_of_the_day_is_accepted(self) -> None:
        self.assertEqual(parse_clock("24:00"), 1440)

    def test_nonsense_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            parse_clock("half past two")

    def test_out_of_range_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            parse_clock("25:00")


class WindowTests(unittest.TestCase):
    def test_a_window_covers_its_own_minutes(self) -> None:
        window = TimeWindow.between("peak", "14:00", "19:00")
        self.assertTrue(window.covers_minute(parse_clock("16:00")))
        self.assertFalse(window.covers_minute(parse_clock("19:00")))

    def test_a_window_can_wrap_midnight(self) -> None:
        window = TimeWindow.between("night", "22:00", "06:00")
        self.assertTrue(window.wraps_midnight)
        self.assertTrue(window.covers_minute(parse_clock("23:00")))
        self.assertTrue(window.covers_minute(parse_clock("02:00")))
        self.assertFalse(window.covers_minute(parse_clock("12:00")))

    def test_a_wrapping_window_reports_its_true_length(self) -> None:
        self.assertEqual(TimeWindow.between("night", "22:00", "06:00").length_minutes, 480)

    def test_a_zero_length_window_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            TimeWindow.between("bad", "10:00", "10:00")

    def test_day_type_and_season_narrow_a_window(self) -> None:
        window = TimeWindow.between(
            "peak", "14:00", "19:00", (DayType.WEEKDAY,), "summer"
        )
        self.assertTrue(window.matches(900, DayType.WEEKDAY, "summer"))
        self.assertFalse(window.matches(900, DayType.WEEKEND, "summer"))
        self.assertFalse(window.matches(900, DayType.WEEKDAY, "winter"))


class PrecedenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.windows = WindowSet(
            (
                TimeWindow.between("shoulder", "07:00", "22:00", (DayType.WEEKDAY,)),
                TimeWindow.between("peak", "14:00", "19:00", (DayType.WEEKDAY,)),
            ),
            "offpeak",
        )

    def test_most_specific_prefers_the_narrower_window(self) -> None:
        self.assertEqual(
            self.windows.resolve(900, DayType.WEEKDAY, "", WindowPrecedence.MOST_SPECIFIC),
            "peak",
        )

    def test_first_match_prefers_declaration_order(self) -> None:
        self.assertEqual(
            self.windows.resolve(900, DayType.WEEKDAY, "", WindowPrecedence.FIRST_MATCH),
            "shoulder",
        )

    def test_last_match_lets_later_entries_override(self) -> None:
        self.assertEqual(
            self.windows.resolve(900, DayType.WEEKDAY, "", WindowPrecedence.LAST_MATCH),
            "peak",
        )

    def test_unmatched_minutes_fall_to_the_default(self) -> None:
        self.assertEqual(
            self.windows.resolve(60, DayType.WEEKDAY, "", WindowPrecedence.MOST_SPECIFIC),
            "offpeak",
        )

    def test_a_tariff_can_override_the_profile(self) -> None:
        insistent = WindowSet(
            self.windows.windows, "offpeak", WindowPrecedence.FIRST_MATCH
        )
        self.assertEqual(
            insistent.resolve(900, DayType.WEEKDAY, "", WindowPrecedence.MOST_SPECIFIC),
            "shoulder",
        )

    def test_buckets_include_the_default(self) -> None:
        self.assertEqual(set(self.windows.buckets), {"shoulder", "peak", "offpeak"})


class SeasonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seasons = SeasonSet(
            (Season("summer", 6, 1, 9, 30), Season("winter", 10, 1, 5, 31))
        )

    def test_a_winter_season_wraps_the_year_end(self) -> None:
        self.assertTrue(self.seasons.get("winter").wraps_year_end)
        self.assertEqual(self.seasons.season_for(date(2025, 1, 15)), "winter")
        self.assertEqual(self.seasons.season_for(date(2025, 12, 15)), "winter")

    def test_summer_is_selected_in_between(self) -> None:
        self.assertEqual(self.seasons.season_for(date(2025, 7, 15)), "summer")

    def test_the_pair_covers_the_whole_year(self) -> None:
        self.assertTrue(self.seasons.covers_year())

    def test_a_gap_is_detectable(self) -> None:
        partial = SeasonSet((Season("summer", 6, 1, 9, 30),))
        self.assertFalse(partial.covers_year())

    def test_unknown_seasons_are_reported(self) -> None:
        with self.assertRaises(TariffError):
            self.seasons.get("monsoon")

    def test_an_unmatched_day_returns_the_default(self) -> None:
        partial = SeasonSet((Season("summer", 6, 1, 9, 30),), "winter")
        self.assertEqual(partial.season_for(date(2025, 1, 1)), "winter")


class BucketSpanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.windows = WindowSet(
            (
                TimeWindow.between("shoulder", "07:00", "22:00", (DayType.WEEKDAY,)),
                TimeWindow.between("peak", "14:00", "19:00", (DayType.WEEKDAY,)),
            ),
            "offpeak",
        )

    def _hours(self, start: date, days: int) -> dict[str, Decimal]:
        span = Span(
            ZONE.day_start(start),
            ZONE.day_start(date.fromordinal(start.toordinal() + days)),
        )
        spans = bucket_spans(span, ZONE, self.windows, holidays=us_federal_calendar())
        return {
            bucket: sum((piece.hours for piece in pieces), Decimal(0))
            for bucket, pieces in spans.items()
        }

    def test_a_weekday_splits_into_three_buckets(self) -> None:
        hours = self._hours(date(2025, 6, 4), 1)
        self.assertEqual(hours["peak"], Decimal("5"))
        self.assertEqual(hours["shoulder"], Decimal("10"))
        self.assertEqual(hours["offpeak"], Decimal("9"))

    def test_a_weekend_day_is_entirely_off_peak(self) -> None:
        hours = self._hours(date(2025, 6, 7), 1)
        self.assertEqual(hours["offpeak"], Decimal("24"))
        self.assertNotIn("peak", hours)

    def test_a_holiday_is_off_peak(self) -> None:
        hours = self._hours(date(2025, 7, 4), 1)
        self.assertEqual(hours["offpeak"], Decimal("24"))

    def test_the_autumn_day_contributes_twenty_five_hours(self) -> None:
        hours = self._hours(date(2025, 11, 2), 1)
        self.assertEqual(sum(hours.values(), Decimal(0)), Decimal("25"))

    def test_the_spring_day_contributes_twenty_three(self) -> None:
        hours = self._hours(date(2025, 3, 9), 1)
        self.assertEqual(sum(hours.values(), Decimal(0)), Decimal("23"))

    def test_a_week_adds_up_to_a_week(self) -> None:
        hours = self._hours(date(2025, 6, 2), 7)
        self.assertEqual(sum(hours.values(), Decimal(0)), Decimal("168"))

    def test_bucket_at_agrees_with_bucket_spans(self) -> None:
        moment = ZONE.from_local(datetime(2025, 6, 4, 16, 0))
        self.assertEqual(bucket_at(moment, ZONE, self.windows), "peak")

    def test_an_empty_span_produces_no_buckets(self) -> None:
        empty = Span(ZONE.day_start(date(2025, 6, 1)), ZONE.day_start(date(2025, 6, 1)))
        self.assertEqual(bucket_spans(empty, ZONE, self.windows), {})


if __name__ == "__main__":
    unittest.main()
