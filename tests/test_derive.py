"""Turning reads into consumption records."""

from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal

from meterline.core.quantity import Quantity
from meterline.core.units import Unit
from meterline.meterdata.consumption import Consumption, clip, total_quantity
from meterline.meterdata.derive import billable_reads, derive_consumption
from meterline.meterdata.gaps import coverage_fraction, find_gaps, report_gaps
from meterline.model.quality import QualityCode, ReadType
from meterline.model.reading import MeterRead, RegisterChange
from meterline.model.register import Register
from meterline.policy.profile import UtilityProfile
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span

REGISTER = Register("rg-1", "mt-1", Unit.KWH, digits=5)
PROFILE = UtilityProfile()


def read(day: int, value: str, **kwargs) -> MeterRead:
    """Build a read on the given day of June 2025."""

    return MeterRead.build("mt-1", "rg-1", utc(2025, 6, day), Decimal(value), **kwargs)


class DeriveTests(unittest.TestCase):
    def test_two_reads_make_one_record(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        outcome = derive_consumption(
            REGISTER, [read(1, "1000"), read(11, "1300")], span, PROFILE
        )
        self.assertEqual(len(outcome.value), 1)
        self.assertEqual(outcome.value[0].quantity.value, Decimal("300"))

    def test_one_read_is_not_enough(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        outcome = derive_consumption(REGISTER, [read(1, "1000")], span, PROFILE)
        self.assertEqual(outcome.value, [])
        self.assertIn(
            "meterdata.derive.insufficient_reads", outcome.diagnostics.codes()
        )

    def test_records_outside_the_span_are_apportioned_into_it(self) -> None:
        span = Span(utc(2025, 6, 5), utc(2025, 6, 10))
        outcome = derive_consumption(
            REGISTER, [read(1, "1000"), read(11, "2000")], span, PROFILE
        )
        record = outcome.value[0]
        self.assertEqual(record.span, span)
        self.assertEqual(record.quantity.value, Decimal("500"))
        self.assertIs(record.quality, QualityCode.PARTIAL)

    def test_a_check_read_does_not_close_a_period(self) -> None:
        reads = [
            read(1, "1000"),
            read(5, "1100", read_type=ReadType.CHECK),
            read(11, "1300"),
        ]
        kept = billable_reads(reads)
        self.assertEqual(len(kept), 3)
        self.assertIs(kept[1].read_type, ReadType.CHECK)

    def test_two_reads_at_one_instant_prefer_the_billable_one(self) -> None:
        billable = read(5, "1100")
        check = MeterRead.build(
            "mt-1", "rg-1", utc(2025, 6, 5), Decimal("1105"), ReadType.CHECK
        )
        kept = billable_reads([check, billable])
        self.assertEqual(len(kept), 1)
        self.assertIs(kept[0].read_type, ReadType.ACTUAL)

    def test_an_estimated_endpoint_taints_the_record(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        outcome = derive_consumption(
            REGISTER,
            [
                read(1, "1000"),
                read(
                    11,
                    "1300",
                    read_type=ReadType.ESTIMATED,
                    quality=QualityCode.ESTIMATED,
                ),
            ],
            span,
            PROFILE,
        )
        self.assertIs(outcome.value[0].quality, QualityCode.ESTIMATED)

    def test_no_overlapping_reads_is_reported(self) -> None:
        span = Span(utc(2025, 7, 1), utc(2025, 7, 10))
        outcome = derive_consumption(
            REGISTER, [read(1, "1000"), read(11, "1300")], span, PROFILE
        )
        self.assertEqual(outcome.value, [])
        self.assertIn("meterdata.derive.no_coverage", outcome.diagnostics.codes())


class RegisterChangeTests(unittest.TestCase):
    def test_usage_spans_a_meter_exchange(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 21))
        change = RegisterChange.build(
            "mt-1", "rg-1", utc(2025, 6, 11), Decimal("1300"), Decimal("0")
        )
        outcome = derive_consumption(
            REGISTER,
            [read(1, "1000"), read(21, "150")],
            span,
            PROFILE,
            changes=[change],
        )
        total = total_quantity(outcome.value, Unit.KWH)
        self.assertEqual(total.value, Decimal("450"))
        self.assertEqual(len(outcome.value), 2)

    def test_an_exchange_at_the_closing_read_leaves_one_record(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        change = RegisterChange.build(
            "mt-1", "rg-1", utc(2025, 6, 11), Decimal("1400"), Decimal("0")
        )
        outcome = derive_consumption(
            REGISTER,
            [read(1, "1000"), read(11, "0")],
            span,
            PROFILE,
            changes=[change],
        )
        self.assertEqual(len(outcome.value), 1)
        self.assertEqual(outcome.value[0].quantity.value, Decimal("400"))
        self.assertNotIn(
            "meterdata.derive.duplicate_instant", outcome.diagnostics.codes()
        )


class ConsumptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = Consumption(
            Span(utc(2025, 6, 1), utc(2025, 6, 11)),
            Quantity(Decimal("300"), Unit.KWH),
        )

    def test_daily_rate_divides_by_elapsed_time(self) -> None:
        self.assertEqual(self.record.daily_rate, Decimal("30"))

    def test_clipping_to_a_disjoint_span_drops_the_record(self) -> None:
        bounds = Span(utc(2025, 7, 1), utc(2025, 7, 2))
        self.assertEqual(clip([self.record], bounds), [])

    def test_clipping_to_the_same_span_returns_the_record_itself(self) -> None:
        self.assertIs(self.record.clipped_to(self.record.span), self.record)

    def test_a_zero_length_record_has_no_daily_rate(self) -> None:
        empty = Consumption(
            Span(utc(2025, 6, 1), utc(2025, 6, 1)),
            Quantity(Decimal("0"), Unit.KWH),
        )
        self.assertEqual(empty.daily_rate, Decimal("0"))


class GapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.span = Span(utc(2025, 6, 1), utc(2025, 6, 21))
        self.records = derive_consumption(
            REGISTER, [read(1, "1000"), read(11, "1300")], self.span, PROFILE
        ).value

    def test_the_uncovered_tail_is_a_gap(self) -> None:
        gaps = find_gaps(self.span, self.records)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].span.start, utc(2025, 6, 11))
        self.assertEqual(gaps[0].span.duration, timedelta(days=10))

    def test_full_coverage_leaves_no_gap(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        records = derive_consumption(
            REGISTER, [read(1, "1000"), read(11, "1300")], span, PROFILE
        ).value
        self.assertEqual(find_gaps(span, records), [])

    def test_coverage_fraction_reports_the_half(self) -> None:
        self.assertEqual(coverage_fraction(self.span, self.records), Decimal("0.5"))

    def test_every_gap_produces_a_diagnostic(self) -> None:
        bag = report_gaps(find_gaps(self.span, self.records), "sp-1")
        self.assertEqual(len(bag), 1)
        self.assertEqual(bag.items[0].code, "meterdata.gap")


if __name__ == "__main__":
    unittest.main()
