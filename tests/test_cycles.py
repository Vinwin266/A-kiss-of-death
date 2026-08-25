"""Billing cycles and the read schedules that produce them."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from meterline.errors import TimelineError
from meterline.timeline.calendars import MonthKey
from meterline.timeline.cycles import BillingCycle, CycleKind, CycleSchedule, ReadDayShift
from meterline.timeline.holidays import us_federal_calendar
from meterline.timeline.rules import Weekday
from meterline.timeline.zones import common_zone


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = common_zone("America/New_York")
        self.schedule = CycleSchedule("R1", 15, self.zone)

    def test_cycles_tile_without_gaps(self) -> None:
        cycles = self.schedule.cycles("sp-1", MonthKey(2025, 4), 4)
        for earlier, later in zip(cycles, cycles[1:]):
            self.assertEqual(earlier.span.end, later.span.start)

    def test_cycle_length_tracks_the_month(self) -> None:
        cycles = self.schedule.cycles("sp-1", MonthKey(2025, 4), 3)
        lengths = [cycle.days(self.zone) for cycle in cycles]
        self.assertEqual(lengths, [31, 30, 31])

    def test_a_cycle_is_attributed_to_the_month_it_ends_in(self) -> None:
        cycles = self.schedule.cycles("sp-1", MonthKey(2025, 4), 1)
        self.assertEqual(cycles[0].month(self.zone), MonthKey(2025, 4))

    def test_identifiers_are_stable_across_runs(self) -> None:
        first = self.schedule.cycles("sp-1", MonthKey(2025, 4), 2)
        second = self.schedule.cycles("sp-1", MonthKey(2025, 4), 2)
        self.assertEqual(
            [cycle.cycle_id for cycle in first], [cycle.cycle_id for cycle in second]
        )

    def test_a_cycle_crossing_the_spring_change_is_still_whole_days(self) -> None:
        cycles = self.schedule.cycles("sp-1", MonthKey(2025, 3), 1)
        self.assertEqual(cycles[0].days(self.zone), 28)
        self.assertEqual(cycles[0].span.hours, 671)

    def test_read_day_clamps_to_a_short_month(self) -> None:
        schedule = CycleSchedule("R1", 31, self.zone)
        self.assertEqual(
            schedule.scheduled_read_for(MonthKey(2025, 2)), date(2025, 2, 28)
        )

    def test_no_cycles_when_none_are_asked_for(self) -> None:
        self.assertEqual(self.schedule.cycles("sp-1", MonthKey(2025, 4), 0), [])

    def test_an_out_of_range_read_day_is_refused(self) -> None:
        with self.assertRaises(TimelineError):
            CycleSchedule("R1", 32, self.zone)

    def test_an_impossible_tolerance_is_refused(self) -> None:
        with self.assertRaises(TimelineError):
            CycleSchedule("R1", 15, self.zone, minimum_days=40, maximum_days=30)


class ReadDayShiftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = common_zone("America/New_York")
        self.holidays = us_federal_calendar()

    def _schedule(self, shift: ReadDayShift) -> CycleSchedule:
        return CycleSchedule("R1", 5, self.zone, shift, self.holidays)

    def test_no_shift_reads_on_the_weekend(self) -> None:
        schedule = self._schedule(ReadDayShift.NONE)
        self.assertEqual(schedule.scheduled_read_for(MonthKey(2025, 7)), date(2025, 7, 5))

    def test_forward_moves_to_the_following_monday(self) -> None:
        schedule = self._schedule(ReadDayShift.FORWARD)
        self.assertEqual(schedule.scheduled_read_for(MonthKey(2025, 7)), date(2025, 7, 7))

    def test_backward_skips_a_holiday_as_well_as_the_weekend(self) -> None:
        schedule = self._schedule(ReadDayShift.BACKWARD)
        # 5 July 2025 is a Saturday and 4 July is an observed holiday.
        self.assertEqual(schedule.scheduled_read_for(MonthKey(2025, 7)), date(2025, 7, 3))

    def test_nearest_breaks_ties_backward(self) -> None:
        schedule = self._schedule(ReadDayShift.NEAREST)
        self.assertEqual(schedule.scheduled_read_for(MonthKey(2025, 7)), date(2025, 7, 3))

    def test_working_days_exclude_the_weekend(self) -> None:
        schedule = self._schedule(ReadDayShift.NONE)
        self.assertFalse(schedule.is_working_day(date(2025, 7, 5)))
        self.assertTrue(schedule.is_working_day(date(2025, 7, 8)))

    def test_a_route_reading_seven_days_a_week_never_shifts(self) -> None:
        schedule = CycleSchedule(
            "R1",
            5,
            self.zone,
            ReadDayShift.FORWARD,
            None,
            working_days=tuple(Weekday),
        )
        self.assertEqual(schedule.scheduled_read_for(MonthKey(2025, 7)), date(2025, 7, 5))

    def test_next_read_after_a_date(self) -> None:
        schedule = self._schedule(ReadDayShift.NONE)
        self.assertEqual(schedule.next_read_after(date(2025, 7, 5)), date(2025, 8, 5))


class CycleToleranceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = common_zone("America/New_York")
        self.schedule = CycleSchedule("R1", 15, self.zone)

    def test_a_normal_cycle_is_within_tolerance(self) -> None:
        cycle = self.schedule.cycles("sp-1", MonthKey(2025, 4), 1)[0]
        self.assertTrue(self.schedule.is_within_tolerance(cycle))

    def test_a_stretched_cycle_is_flagged(self) -> None:
        cycle = self.schedule.cycles("sp-1", MonthKey(2025, 4), 1)[0]
        stretched = BillingCycle.build(
            "sp-1",
            type(cycle.span)(cycle.span.start, cycle.span.end + timedelta(days=20)),
            cycle.scheduled_read,
            CycleKind.OFF_CYCLE,
        )
        self.assertFalse(self.schedule.is_within_tolerance(stretched))

    def test_cycle_kinds_describe_themselves(self) -> None:
        cycle = self.schedule.cycles("sp-1", MonthKey(2025, 4), 1)[0]
        self.assertIn("regular", cycle.describe(self.zone))


if __name__ == "__main__":
    unittest.main()
