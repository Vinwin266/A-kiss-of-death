"""Validation rules, edits and quality merging."""

from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal

from meterline.core.quantity import Quantity
from meterline.core.units import Unit
from meterline.meterdata.consumption import Consumption, merge_consumption_quality
from meterline.meterdata.edits import EditRecord, apply_edits
from meterline.meterdata.validate import (
    ValidationInput,
    apply_suspect_policy,
    validate_consumption,
)
from meterline.model.quality import (
    QualityCode,
    QualityMergeRule,
    ReadType,
    merge_quality,
    worst_of,
)
from meterline.model.series import IntervalSeries
from meterline.policy.profile import UtilityProfile
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span

PROFILE = UtilityProfile()


def record(days: int, usage: str, start_day: int = 1, **kwargs) -> Consumption:
    """Build one consumption record in June 2025."""

    start = utc(2025, 6, start_day)
    return Consumption(
        Span(start, start + timedelta(days=days)),
        Quantity(Decimal(usage), Unit.KWH),
        **kwargs,
    )


class QualityTests(unittest.TestCase):
    def test_worst_wins_takes_the_most_severe(self) -> None:
        parts = [(QualityCode.VALID, Decimal("900")), (QualityCode.ESTIMATED, Decimal("1"))]
        self.assertIs(merge_quality(parts, QualityMergeRule.WORST_WINS), QualityCode.ESTIMATED)

    def test_measured_wins_hides_the_estimate(self) -> None:
        parts = [(QualityCode.VALID, Decimal("1")), (QualityCode.ESTIMATED, Decimal("900"))]
        self.assertIs(
            merge_quality(parts, QualityMergeRule.MEASURED_WINS), QualityCode.VALID
        )

    def test_dominant_share_follows_the_usage(self) -> None:
        parts = [(QualityCode.VALID, Decimal("1")), (QualityCode.ESTIMATED, Decimal("900"))]
        self.assertIs(
            merge_quality(parts, QualityMergeRule.DOMINANT_SHARE), QualityCode.ESTIMATED
        )

    def test_majority_valid_needs_more_than_half(self) -> None:
        even = [(QualityCode.VALID, Decimal("50")), (QualityCode.ESTIMATED, Decimal("50"))]
        self.assertIs(
            merge_quality(even, QualityMergeRule.MAJORITY_VALID), QualityCode.ESTIMATED
        )

    def test_no_parts_at_all_is_missing(self) -> None:
        self.assertIs(merge_quality([], QualityMergeRule.WORST_WINS), QualityCode.MISSING)

    def test_worst_of_an_empty_sequence_is_valid(self) -> None:
        self.assertIs(worst_of([]), QualityCode.VALID)

    def test_estimates_are_flagged_for_true_up(self) -> None:
        self.assertTrue(QualityCode.ESTIMATED.needs_true_up)
        self.assertFalse(QualityCode.VALID.needs_true_up)

    def test_missing_data_is_not_billable(self) -> None:
        self.assertFalse(QualityCode.MISSING.is_billable)
        self.assertTrue(QualityCode.SUSPECT.is_billable)

    def test_a_check_read_does_not_bill_by_default(self) -> None:
        self.assertFalse(ReadType.CHECK.bills_by_default)
        self.assertTrue(ReadType.ESTIMATED.bills_by_default)

    def test_merging_consumption_uses_the_usage_as_weight(self) -> None:
        records = [
            record(10, "900"),
            record(10, "10", 11, quality=QualityCode.ESTIMATED),
        ]
        self.assertIs(
            merge_consumption_quality(records, QualityMergeRule.DOMINANT_SHARE),
            QualityCode.VALID,
        )


class ValidationRuleTests(unittest.TestCase):
    def test_a_quiet_period_produces_nothing(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 7, 1))
        bag = validate_consumption(
            span, [record(30, "300")], PROFILE, history=[record(30, "300")]
        )
        self.assertEqual(len(bag), 0)

    def test_a_spike_is_flagged(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 7, 1))
        bag = validate_consumption(
            span, [record(30, "3000")], PROFILE, history=[record(30, "300")]
        )
        self.assertIn("meterdata.validate.spike", bag.codes())

    def test_a_collapse_is_a_notice_not_a_warning(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 7, 1))
        bag = validate_consumption(
            span, [record(30, "30")], PROFILE, history=[record(30, "3000")]
        )
        self.assertIn("meterdata.validate.dropout", bag.codes())
        self.assertEqual(bag.warnings, [])

    def test_negative_usage_is_flagged(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        bag = validate_consumption(span, [record(10, "-5")], PROFILE)
        self.assertIn("meterdata.validate.negative", bag.codes())

    def test_a_long_dead_meter_is_flagged(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 8, 1))
        bag = validate_consumption(span, [record(61, "0")], PROFILE)
        self.assertIn("meterdata.validate.stopped", bag.codes())

    def test_mixed_quality_is_noted(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 21))
        records = [record(10, "100"), record(10, "100", 11, quality=QualityCode.ESTIMATED)]
        bag = validate_consumption(span, records, PROFILE)
        self.assertIn("meterdata.validate.mixed_quality", bag.codes())

    def test_interval_data_that_disagrees_is_flagged(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 3))
        series = IntervalSeries(
            "ch-1", utc(2025, 6, 1), 60, tuple(Decimal("1") for _ in range(48))
        )
        bag = validate_consumption(
            span, [record(2, "100")], PROFILE, series=series
        )
        self.assertIn("meterdata.validate.interval_mismatch", bag.codes())

    def test_partial_interval_coverage_is_not_compared(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 30))
        series = IntervalSeries(
            "ch-1", utc(2025, 6, 1), 60, tuple(Decimal("1") for _ in range(48))
        )
        bag = validate_consumption(span, [record(29, "100")], PROFILE, series=series)
        self.assertNotIn("meterdata.validate.interval_mismatch", bag.codes())

    def test_the_input_reports_its_own_daily_rate(self) -> None:
        span = Span(utc(2025, 6, 1), utc(2025, 6, 11))
        inputs = ValidationInput(span, (record(10, "300"),), (), PROFILE)
        self.assertEqual(inputs.daily_rate, Decimal("30"))

    def test_suspect_policy_stamps_the_records(self) -> None:
        stamped = apply_suspect_policy([record(10, "100")], True, PROFILE)
        self.assertIs(stamped[0].quality, QualityCode.SUSPECT)

    def test_suspect_policy_leaves_clean_records_alone(self) -> None:
        original = [record(10, "100")]
        self.assertEqual(apply_suspect_policy(original, False, PROFILE), original)


class EditTests(unittest.TestCase):
    def test_an_edit_replaces_a_covered_record(self) -> None:
        original = record(10, "300")
        edit = EditRecord.build("rg-1", original.span, Decimal("250"), "field visit")
        edited, bag = apply_edits([original], [edit], subject="rg-1")
        self.assertEqual(edited[0].quantity.value, Decimal("250"))
        self.assertIs(edited[0].quality, QualityCode.EDITED)
        self.assertIn("meterdata.edit.applied", bag.codes())

    def test_a_partial_edit_is_refused_and_reported(self) -> None:
        original = record(10, "300")
        narrow = Span(original.span.start, original.span.start + timedelta(days=2))
        edit = EditRecord.build("rg-1", narrow, Decimal("10"), "partial")
        edited, bag = apply_edits([original], [edit], subject="rg-1")
        self.assertEqual(edited[0].quantity.value, Decimal("300"))
        self.assertIn("meterdata.edit.unapplied", bag.codes())

    def test_no_edits_changes_nothing(self) -> None:
        original = [record(10, "300")]
        edited, bag = apply_edits(original, [])
        self.assertEqual(edited, original)
        self.assertEqual(len(bag), 0)

    def test_edits_are_identified_deterministically(self) -> None:
        span = record(10, "300").span
        first = EditRecord.build("rg-1", span, Decimal("250"), "x")
        second = EditRecord.build("rg-1", span, Decimal("250"), "y")
        self.assertEqual(first.edit_id, second.edit_id)


if __name__ == "__main__":
    unittest.main()
