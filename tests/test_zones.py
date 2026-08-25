"""Timezones with explicit daylight-saving rules."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from meterline.errors import TimelineError
from meterline.timeline.rules import FixedDate, LastWeekday, NthWeekday, Weekday
from meterline.timeline.zones import (
    UTC,
    DstRule,
    NonexistentTime,
    Zone,
    ZoneRegistry,
    common_zone,
)


class DateRuleTests(unittest.TestCase):
    def test_second_sunday_in_march_2025(self) -> None:
        self.assertEqual(NthWeekday(3, Weekday.SUNDAY, 2).resolve(2025), date(2025, 3, 9))

    def test_last_monday_in_may_2025(self) -> None:
        self.assertEqual(LastWeekday(5, Weekday.MONDAY).resolve(2025), date(2025, 5, 26))

    def test_a_fifth_occurrence_clamps_to_the_last(self) -> None:
        rule = NthWeekday(2, Weekday.MONDAY, 5)
        self.assertEqual(rule.resolve(2025), date(2025, 2, 24))

    def test_february_29_clamps_in_a_common_year(self) -> None:
        self.assertEqual(FixedDate(2, 29).resolve(2025), date(2025, 2, 28))

    def test_out_of_range_months_are_rejected(self) -> None:
        with self.assertRaises(TimelineError):
            FixedDate(13, 1)

    def test_rules_describe_themselves(self) -> None:
        self.assertIn("Sunday", NthWeekday(3, Weekday.SUNDAY, 2).describe())


class ZoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.eastern = common_zone("America/New_York")
        self.phoenix = common_zone("America/Phoenix")

    def test_transitions_land_on_the_expected_instants(self) -> None:
        forward, back = self.eastern.transitions(2025)
        self.assertEqual(forward, datetime(2025, 3, 9, 7, tzinfo=timezone.utc))
        self.assertEqual(back, datetime(2025, 11, 2, 6, tzinfo=timezone.utc))

    def test_a_spring_day_is_twenty_three_hours(self) -> None:
        self.assertEqual(self.eastern.day_length_hours(date(2025, 3, 9)), 23)

    def test_an_autumn_day_is_twenty_five_hours(self) -> None:
        self.assertEqual(self.eastern.day_length_hours(date(2025, 11, 2)), 25)

    def test_an_ordinary_day_is_twenty_four_hours(self) -> None:
        self.assertEqual(self.eastern.day_length_hours(date(2025, 6, 1)), 24)

    def test_a_zone_without_rules_never_shifts(self) -> None:
        self.assertEqual(self.phoenix.day_length_hours(date(2025, 3, 9)), 24)
        self.assertFalse(self.phoenix.is_dst(datetime(2025, 7, 1, tzinfo=timezone.utc)))

    def test_local_conversion_applies_the_offset_in_force(self) -> None:
        summer = self.eastern.to_local(datetime(2025, 7, 4, 16, tzinfo=timezone.utc))
        winter = self.eastern.to_local(datetime(2025, 1, 4, 16, tzinfo=timezone.utc))
        self.assertEqual(summer.hour, 12)
        self.assertEqual(winter.hour, 11)

    def test_the_repeated_hour_is_resolved_by_fold(self) -> None:
        wall = datetime(2025, 11, 2, 1, 30)
        first = self.eastern.from_local(wall, fold=0)
        second = self.eastern.from_local(wall, fold=1)
        self.assertLess(first, second)
        self.assertEqual((second - first).total_seconds(), 3600)

    def test_the_skipped_hour_shifts_forward_by_default(self) -> None:
        wall = datetime(2025, 3, 9, 2, 30)
        shifted = self.eastern.to_local(self.eastern.from_local(wall))
        self.assertEqual(shifted.hour, 3)

    def test_the_skipped_hour_can_be_refused(self) -> None:
        with self.assertRaises(NonexistentTime):
            self.eastern.from_local(datetime(2025, 3, 9, 2, 30), on_gap="raise")

    def test_aware_wall_clock_times_are_refused(self) -> None:
        with self.assertRaises(TimelineError):
            self.eastern.from_local(datetime(2025, 3, 9, 5, tzinfo=timezone.utc))

    def test_abbreviations_follow_the_season(self) -> None:
        self.assertEqual(
            self.eastern.abbreviation_at(datetime(2025, 7, 4, tzinfo=timezone.utc)), "EDT"
        )
        self.assertEqual(
            self.eastern.abbreviation_at(datetime(2025, 1, 4, tzinfo=timezone.utc)), "EST"
        )

    def test_utc_has_no_rules(self) -> None:
        self.assertIsNone(UTC.dst)
        self.assertIn("no daylight saving", UTC.describe())


class SouthernHemisphereTests(unittest.TestCase):
    def test_daylight_saving_wrapping_the_new_year(self) -> None:
        zone = Zone(
            "Test/South",
            600,
            DstRule(
                start=NthWeekday(10, Weekday.SUNDAY, 1),
                end=NthWeekday(4, Weekday.SUNDAY, 1),
            ),
            "AEST",
            "AEDT",
        )
        self.assertTrue(zone.is_dst(datetime(2025, 1, 15, tzinfo=timezone.utc)))
        self.assertFalse(zone.is_dst(datetime(2025, 7, 15, tzinfo=timezone.utc)))


class RegistryTests(unittest.TestCase):
    def test_unknown_zones_are_reported_with_the_known_ones(self) -> None:
        registry = ZoneRegistry()
        with self.assertRaises(TimelineError) as caught:
            registry.get("Mars/Olympus")
        self.assertIn("known", caught.exception.context)

    def test_registering_replaces_by_name(self) -> None:
        registry = ZoneRegistry()
        registry.register(Zone("UTC", 60, None, "OFF"))
        self.assertEqual(registry.get("UTC").standard_offset_minutes, 60)

    def test_names_are_sorted(self) -> None:
        self.assertEqual(ZoneRegistry().names(), sorted(ZoneRegistry().names()))


if __name__ == "__main__":
    unittest.main()
