"""Calendar arithmetic, day counts, holidays and day types."""

from __future__ import annotations

import unittest
from datetime import date

from meterline.errors import TimelineError
from meterline.timeline.calendars import (
    MonthKey,
    add_months,
    date_range,
    days_in_month,
    end_of_month,
    iter_months,
    month_of,
)
from meterline.timeline.daycount import (
    DayCount,
    billing_days,
    day_fraction,
    days_between,
    year_fraction,
)
from meterline.timeline.daytypes import DayType, DayTypeRules, classify_day
from meterline.timeline.holidays import (
    Holiday,
    HolidayCalendar,
    ObservedRule,
    us_federal_calendar,
)
from meterline.timeline.rules import FixedDate
from meterline.timeline.spans import Span
from meterline.timeline.zones import common_zone


class MonthKeyTests(unittest.TestCase):
    def test_shifting_across_a_year_boundary(self) -> None:
        self.assertEqual(MonthKey(2025, 11).shift(3), MonthKey(2026, 2))
        self.assertEqual(MonthKey(2025, 2).shift(-3), MonthKey(2024, 11))

    def test_parsing_and_rendering_round_trip(self) -> None:
        self.assertEqual(str(MonthKey.parse("2025-06")), "2025-06")

    def test_bad_month_strings_are_refused(self) -> None:
        with self.assertRaises(TimelineError):
            MonthKey.parse("June 2025")

    def test_months_are_orderable(self) -> None:
        self.assertLess(MonthKey(2025, 1), MonthKey(2025, 2))

    def test_start_and_end_bracket_the_month(self) -> None:
        key = MonthKey(2025, 2)
        self.assertEqual(key.start(), date(2025, 2, 1))
        self.assertEqual(key.end(), date(2025, 2, 28))

    def test_iterating_months(self) -> None:
        months = list(iter_months(MonthKey(2025, 11), 3))
        self.assertEqual([str(month) for month in months], ["2025-11", "2025-12", "2026-01"])


class CalendarArithmeticTests(unittest.TestCase):
    def test_month_end_clamps(self) -> None:
        self.assertEqual(add_months(date(2025, 1, 31), 1), date(2025, 2, 28))

    def test_clamping_can_be_refused(self) -> None:
        with self.assertRaises(TimelineError):
            add_months(date(2025, 1, 31), 1, clamp=False)

    def test_leap_years_are_handled(self) -> None:
        self.assertEqual(days_in_month(2024, 2), 29)
        self.assertEqual(end_of_month(date(2024, 2, 10)), date(2024, 2, 29))

    def test_date_range_is_half_open_by_default(self) -> None:
        days = list(date_range(date(2025, 6, 1), date(2025, 6, 4)))
        self.assertEqual(len(days), 3)
        self.assertEqual(days[-1], date(2025, 6, 3))

    def test_date_range_can_include_the_end(self) -> None:
        days = list(date_range(date(2025, 6, 1), date(2025, 6, 4), inclusive=True))
        self.assertEqual(days[-1], date(2025, 6, 4))

    def test_a_backwards_range_raises(self) -> None:
        with self.assertRaises(TimelineError):
            list(date_range(date(2025, 6, 4), date(2025, 6, 1)))

    def test_month_of_a_date(self) -> None:
        self.assertEqual(month_of(date(2025, 6, 15)), MonthKey(2025, 6))


class DayCountTests(unittest.TestCase):
    def test_half_open_and_inclusive_differ_by_one(self) -> None:
        start, end = date(2025, 6, 1), date(2025, 7, 1)
        self.assertEqual(days_between(start, end, DayCount.ACTUAL), 30)
        self.assertEqual(days_between(start, end, DayCount.ACTUAL_INCLUSIVE), 31)

    def test_thirty_360_flattens_the_months(self) -> None:
        self.assertEqual(
            days_between(date(2025, 1, 31), date(2025, 3, 31), DayCount.THIRTY_360), 60
        )

    def test_nominal_thirty_ignores_the_dates(self) -> None:
        self.assertEqual(
            days_between(date(2025, 1, 1), date(2025, 12, 1), DayCount.NOMINAL_30), 30
        )

    def test_backwards_dates_raise(self) -> None:
        with self.assertRaises(TimelineError):
            days_between(date(2025, 7, 1), date(2025, 6, 1))

    def test_year_fraction_accounts_for_a_leap_day(self) -> None:
        # The leap year contributes one extra day to the numerator, which
        # outweighs its larger 366-day basis.
        common = year_fraction(date(2025, 1, 1), date(2025, 3, 1))
        leap = year_fraction(date(2024, 1, 1), date(2024, 3, 1))
        self.assertGreater(leap, common)

    def test_billing_days_count_local_dates_not_hours(self) -> None:
        zone = common_zone("America/New_York")
        span = Span(zone.day_start(date(2025, 11, 1)), zone.day_start(date(2025, 11, 4)))
        self.assertEqual(billing_days(span, zone, DayCount.ACTUAL), 3)

    def test_day_fraction_is_relative_to_thirty(self) -> None:
        zone = common_zone("America/New_York")
        span = Span(zone.day_start(date(2025, 6, 1)), zone.day_start(date(2025, 7, 1)))
        self.assertEqual(day_fraction(span, zone), 1)


class HolidayTests(unittest.TestCase):
    def test_saturday_moves_back_to_friday(self) -> None:
        holiday = Holiday("Test", FixedDate(7, 4), ObservedRule.NEAREST_WEEKDAY)
        self.assertEqual(holiday.dates_in(2026), (date(2026, 7, 3),))

    def test_sunday_moves_forward_to_monday(self) -> None:
        holiday = Holiday("Test", FixedDate(7, 4), ObservedRule.NEAREST_WEEKDAY)
        self.assertEqual(holiday.dates_in(2027), (date(2027, 7, 5),))

    def test_both_keeps_the_actual_and_the_observed_day(self) -> None:
        holiday = Holiday("Test", FixedDate(7, 4), ObservedRule.BOTH)
        self.assertEqual(holiday.dates_in(2026), (date(2026, 7, 3), date(2026, 7, 4)))

    def test_none_leaves_the_date_alone(self) -> None:
        holiday = Holiday("Test", FixedDate(7, 4), ObservedRule.NONE)
        self.assertEqual(holiday.dates_in(2026), (date(2026, 7, 4),))

    def test_the_tariff_calendar_recognises_six_days(self) -> None:
        calendar = us_federal_calendar()
        self.assertEqual(len(calendar.in_year(2025)), 6)

    def test_thanksgiving_2025(self) -> None:
        calendar = us_federal_calendar()
        self.assertEqual(calendar.name_of(date(2025, 11, 27)), "Thanksgiving")

    def test_counting_holidays_in_a_range(self) -> None:
        calendar = us_federal_calendar()
        # Half-open: New Year's Day and Memorial Day, but not 4 July.
        self.assertEqual(calendar.count_between(date(2025, 1, 1), date(2025, 7, 1)), 2)
        self.assertEqual(calendar.count_between(date(2025, 1, 1), date(2025, 7, 5)), 3)

    def test_an_empty_calendar_has_no_holidays(self) -> None:
        self.assertFalse(HolidayCalendar("none").is_holiday(date(2025, 12, 25)))


class DayTypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calendar = us_federal_calendar()

    def test_a_plain_weekday(self) -> None:
        self.assertIs(classify_day(date(2025, 6, 4), self.calendar), DayType.WEEKDAY)

    def test_a_weekend_day(self) -> None:
        self.assertIs(classify_day(date(2025, 6, 7), self.calendar), DayType.WEEKEND)

    def test_a_holiday_is_distinct_by_default(self) -> None:
        self.assertIs(classify_day(date(2025, 7, 4), self.calendar), DayType.HOLIDAY)

    def test_saturday_can_count_as_a_working_day(self) -> None:
        rules = DayTypeRules(saturday_is_weekend=False)
        self.assertIs(
            classify_day(date(2025, 6, 7), self.calendar, rules), DayType.WEEKDAY
        )

    def test_holidays_can_collapse_into_the_weekend_bucket(self) -> None:
        rules = DayTypeRules(holidays_are_distinct=False)
        self.assertIs(
            classify_day(date(2025, 7, 4), self.calendar, rules), DayType.WEEKEND
        )

    def test_weekend_and_holiday_are_off_peak_by_default(self) -> None:
        self.assertTrue(DayType.WEEKEND.is_offpeak_by_default)
        self.assertFalse(DayType.WEEKDAY.is_offpeak_by_default)


if __name__ == "__main__":
    unittest.main()
