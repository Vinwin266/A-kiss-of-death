"""Half-open spans, and what they do across a clock change."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from meterline.errors import TimelineError
from meterline.timeline.instants import (
    ceil_to,
    ensure_utc,
    floor_to,
    format_instant,
    parse_instant,
    utc,
)
from meterline.timeline.spans import (
    Span,
    intersect_all,
    merge_spans,
    subtract_spans,
    total_hours,
)
from meterline.timeline.zones import common_zone


class InstantTests(unittest.TestCase):
    def test_naive_datetimes_are_refused(self) -> None:
        with self.assertRaises(TimelineError):
            ensure_utc(datetime(2025, 1, 1))

    def test_trailing_z_is_accepted(self) -> None:
        self.assertEqual(parse_instant("2025-06-01T00:00Z"), utc(2025, 6, 1))

    def test_an_offset_is_normalised_to_utc(self) -> None:
        self.assertEqual(parse_instant("2025-06-01T02:00+02:00"), utc(2025, 6, 1))

    def test_an_offsetless_timestamp_is_refused(self) -> None:
        with self.assertRaises(TimelineError):
            parse_instant("2025-06-01T00:00")

    def test_rendering_round_trips(self) -> None:
        moment = utc(2025, 6, 1, 13, 45)
        self.assertEqual(parse_instant(format_instant(moment)), moment)

    def test_flooring_and_ceiling_to_an_interval(self) -> None:
        moment = utc(2025, 6, 1, 13, 47)
        self.assertEqual(floor_to(moment, 15), utc(2025, 6, 1, 13, 45))
        self.assertEqual(ceil_to(moment, 15), utc(2025, 6, 1, 14, 0))

    def test_ceiling_an_exact_boundary_does_not_move(self) -> None:
        moment = utc(2025, 6, 1, 13, 45)
        self.assertEqual(ceil_to(moment, 15), moment)


class SpanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.span = Span(utc(2025, 6, 1), utc(2025, 6, 8))

    def test_a_span_cannot_end_before_it_starts(self) -> None:
        with self.assertRaises(TimelineError):
            Span(utc(2025, 6, 8), utc(2025, 6, 1))

    def test_containment_is_half_open(self) -> None:
        self.assertTrue(self.span.contains(utc(2025, 6, 1)))
        self.assertFalse(self.span.contains(utc(2025, 6, 8)))

    def test_touching_spans_do_not_overlap(self) -> None:
        neighbour = Span(utc(2025, 6, 8), utc(2025, 6, 9))
        self.assertFalse(self.span.overlaps(neighbour))
        self.assertTrue(self.span.abuts(neighbour))

    def test_intersection_of_disjoint_spans_is_none(self) -> None:
        other = Span(utc(2025, 7, 1), utc(2025, 7, 2))
        self.assertIsNone(self.span.intersection(other))

    def test_hours_are_exact(self) -> None:
        self.assertEqual(self.span.hours, 168)

    def test_splitting_outside_the_span_raises(self) -> None:
        with self.assertRaises(TimelineError):
            self.span.split_at(utc(2025, 7, 1))

    def test_steps_clip_the_final_piece(self) -> None:
        pieces = list(Span(utc(2025, 6, 1), utc(2025, 6, 1, 0, 50)).steps(15))
        self.assertEqual(len(pieces), 4)
        self.assertEqual(pieces[-1].duration, timedelta(minutes=5))

    def test_union_of_disjoint_spans_raises(self) -> None:
        with self.assertRaises(TimelineError):
            self.span.union(Span(utc(2025, 7, 1), utc(2025, 7, 2)))

    def test_total_hours_of_nothing_is_zero(self) -> None:
        self.assertEqual(total_hours([]), 0)


class LocalDayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = common_zone("America/New_York")

    def _days(self, start: date, count: int) -> list[tuple[date, Span]]:
        span = Span(
            self.zone.day_start(start),
            self.zone.day_start(start + timedelta(days=count)),
        )
        return span.local_days(self.zone)

    def test_ordinary_days_are_twenty_four_hours(self) -> None:
        days = self._days(date(2025, 6, 1), 3)
        self.assertEqual([piece.hours for _, piece in days], [24, 24, 24])

    def test_the_autumn_day_gets_its_extra_hour(self) -> None:
        days = self._days(date(2025, 11, 1), 3)
        self.assertEqual([piece.hours for _, piece in days], [24, 25, 24])

    def test_the_spring_day_loses_an_hour(self) -> None:
        days = self._days(date(2025, 3, 8), 3)
        self.assertEqual([piece.hours for _, piece in days], [24, 23, 24])

    def test_days_tile_without_overlap(self) -> None:
        days = self._days(date(2025, 11, 1), 3)
        for (_, left), (_, right) in zip(days, days[1:]):
            self.assertEqual(left.end, right.start)


class SpanAlgebraTests(unittest.TestCase):
    def test_merging_joins_touching_spans(self) -> None:
        merged = merge_spans(
            [
                Span(utc(2025, 6, 1), utc(2025, 6, 2)),
                Span(utc(2025, 6, 2), utc(2025, 6, 3)),
                Span(utc(2025, 6, 5), utc(2025, 6, 6)),
            ]
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].end, utc(2025, 6, 3))

    def test_subtracting_leaves_the_holes(self) -> None:
        base = Span(utc(2025, 6, 1), utc(2025, 6, 10))
        holes = subtract_spans(base, [Span(utc(2025, 6, 3), utc(2025, 6, 5))])
        self.assertEqual(len(holes), 2)
        self.assertEqual(holes[0].end, utc(2025, 6, 3))
        self.assertEqual(holes[1].start, utc(2025, 6, 5))

    def test_subtracting_everything_leaves_nothing(self) -> None:
        base = Span(utc(2025, 6, 1), utc(2025, 6, 10))
        self.assertEqual(subtract_spans(base, [base]), [])

    def test_intersect_all_of_nothing_is_none(self) -> None:
        self.assertIsNone(intersect_all([]))

    def test_intersect_all_narrows_to_the_common_part(self) -> None:
        common = intersect_all(
            [
                Span(utc(2025, 6, 1), utc(2025, 6, 10)),
                Span(utc(2025, 6, 3), utc(2025, 6, 8)),
                Span(utc(2025, 6, 5), utc(2025, 6, 20)),
            ]
        )
        self.assertEqual(common, Span(utc(2025, 6, 5), utc(2025, 6, 8)))


if __name__ == "__main__":
    unittest.main()
