"""Rating a cycle end to end, and the conventions that move the total."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.charge.basis import Basis
from meterline.charge.classes import ChargeClass
from meterline.errors import RatingError
from meterline.model.quality import QualityCode, ReadType
from meterline.policy.conventions import (
    GapPolicy,
    ProrationBasis,
    RoundingStage,
    SuspectDataPolicy,
    TierBasis,
)
from meterline.policy.presets import preset
from meterline.policy.profile import UtilityProfile
from meterline.rating.engine import rate_cycle
from meterline.rating.sequence import apply_rounding, round_total
from meterline.session import Session
from meterline.timeline.cycles import BillingCycle, CycleKind
from meterline.timeline.spans import Span

from tests.support import build_dataset, residential_tariff, zone


class BasicRatingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = build_dataset(steps=(450, 620, 380))
        self.session = Session.of(self.dataset)
        self.invoices = self.session.rate_all().value

    def test_one_bill_per_cycle(self) -> None:
        self.assertEqual(len(self.invoices), 3)

    def test_bills_are_in_period_order(self) -> None:
        starts = [invoice.span.start for invoice in self.invoices]
        self.assertEqual(starts, sorted(starts))

    def test_the_energy_charge_matches_the_usage(self) -> None:
        first = self.invoices[0]
        self.assertEqual(first.determinant("energy.total"), "450.000 kWh")

    def test_line_codes_are_stable(self) -> None:
        self.assertEqual(self.invoices[0].codes(), ["basic", "energy.1"])

    def test_the_total_is_the_sum_of_the_lines(self) -> None:
        first = self.invoices[0]
        summed = sum(
            (line.amount.amount for line in first.lines), Decimal("0")
        )
        self.assertEqual(first.total.amount, summed)

    def test_a_bill_carries_its_conventions_and_engine(self) -> None:
        first = self.invoices[0]
        self.assertEqual(first.profile_name, "model-rules")
        self.assertTrue(first.engine_version.startswith("meterline/"))

    def test_identifiers_are_stable_across_runs(self) -> None:
        again = Session.of(build_dataset(steps=(450, 620, 380))).rate_all().value
        self.assertEqual(
            [invoice.bill_id for invoice in self.invoices],
            [invoice.bill_id for invoice in again],
        )

    def test_a_missing_cycle_is_refused(self) -> None:
        with self.assertRaises(RatingError):
            self.session.bill("sp-1", "cyc-nope")

    def test_billing_one_cycle_matches_the_run(self) -> None:
        wanted = self.invoices[1]
        single = self.session.bill("sp-1", wanted.cycle_id).value
        self.assertEqual(single.total, wanted.total)


class ProrationConventionTests(unittest.TestCase):
    def _final_bill_total(self, proration: ProrationBasis) -> Decimal:
        dataset = build_dataset(
            steps=(450,),
            profile=preset("model-rules").with_changes(proration=proration),
        )
        cycle = dataset.cycles_of("sp-1")[0]
        short = BillingCycle.build(
            "sp-1",
            Span(cycle.span.start, cycle.span.start + (cycle.span.duration / 6)),
            cycle.scheduled_read,
            CycleKind.FINAL,
        )
        outcome = rate_cycle(dataset, "sp-1", short)
        line = outcome.value.line("basic")
        return line.amount.quantized().amount if line else Decimal("0")

    def test_no_proration_charges_the_whole_month(self) -> None:
        self.assertEqual(self._final_bill_total(ProrationBasis.NONE), Decimal("12.00"))

    def test_any_day_also_charges_the_whole_month(self) -> None:
        self.assertEqual(
            self._final_bill_total(ProrationBasis.FULL_IF_ANY_DAY), Decimal("12.00")
        )

    def test_daily_proration_charges_a_fraction(self) -> None:
        charged = self._final_bill_total(ProrationBasis.DAILY_ACTUAL)
        self.assertLess(charged, Decimal("12.00"))
        self.assertGreater(charged, Decimal("0"))

    def test_the_cycle_fraction_never_exceeds_a_month(self) -> None:
        charged = self._final_bill_total(ProrationBasis.CYCLE_FRACTION)
        self.assertLessEqual(charged, Decimal("12.00"))


class TierConventionTests(unittest.TestCase):
    def _energy(self, tier_basis: TierBasis) -> Decimal:
        dataset = build_dataset(
            steps=(700, 700, 700),
            profile=preset("model-rules").with_changes(tier_basis=tier_basis),
        )
        invoices = Session.of(dataset).rate_all().value
        return invoices[0].subtotal(Basis.ENERGY).quantized().amount

    def test_per_cycle_thresholds_do_not_move(self) -> None:
        # 500 at 0.10 plus 200 at 0.15.
        self.assertEqual(self._energy(TierBasis.CYCLE), Decimal("80.00"))

    def test_a_daily_basis_makes_the_block_enormous(self) -> None:
        self.assertEqual(self._energy(TierBasis.DAILY), Decimal("70.00"))

    def test_prorating_the_threshold_lands_between(self) -> None:
        prorated = self._energy(TierBasis.MONTH_PRORATED)
        self.assertGreaterEqual(prorated, Decimal("70.00"))
        self.assertLessEqual(prorated, Decimal("80.00"))


class RoundingStageTests(unittest.TestCase):
    def _totals(self, stage: RoundingStage) -> Decimal:
        dataset = build_dataset(
            steps=(457,),
            tariff=residential_tariff(first_block_rate="0.10333"),
            profile=preset("model-rules").with_changes(rounding_stage=stage),
        )
        invoices = Session.of(dataset).rate_all().value
        return invoices[0].total.quantized().amount

    def test_rounding_per_line_and_on_the_total_can_differ(self) -> None:
        per_line = self._totals(RoundingStage.PER_LINE)
        on_total = self._totals(RoundingStage.ON_TOTAL)
        self.assertLess(abs(per_line - on_total), Decimal("0.05"))

    def test_per_line_rounding_leaves_two_decimal_places(self) -> None:
        dataset = build_dataset(
            steps=(457,),
            tariff=residential_tariff(first_block_rate="0.10333"),
            profile=preset("model-rules").with_changes(
                rounding_stage=RoundingStage.PER_LINE
            ),
        )
        invoice = Session.of(dataset).rate_all().value[0]
        for line in invoice.lines:
            self.assertEqual(line.amount.amount, line.amount.quantized().amount)

    def test_component_rounding_rounds_the_subtotal_not_the_lines(self) -> None:
        dataset = build_dataset(
            steps=(700,), tariff=residential_tariff(first_block_rate="0.10333")
        )
        invoice = Session.of(dataset).rate_all().value[0]
        rounded = apply_rounding(
            invoice.lines,
            UtilityProfile(rounding_stage=RoundingStage.PER_COMPONENT),
        )
        by_component: dict[str, Decimal] = {}
        for line in rounded:
            by_component[line.component] = (
                by_component.get(line.component, Decimal("0")) + line.amount.amount
            )
        for component, total in by_component.items():
            self.assertEqual(
                total.quantize(Decimal("0.01")), total, msg=f"{component} is unrounded"
            )

    def test_a_total_can_snap_to_an_increment(self) -> None:
        profile = UtilityProfile(total_increment="0.05")
        from meterline.core.money import Money

        self.assertEqual(
            round_total(Money(Decimal("10.13")), profile).amount, Decimal("10.15")
        )


class MeterDataConventionTests(unittest.TestCase):
    def _dataset_with_a_gap(self, profile: UtilityProfile):
        """Return a dataset whose last two cycles have no closing read.

        Dropping a single interior read is not enough: the engine will
        interpolate across it from the surrounding pair, which is the whole
        point of apportioning a late read.  A genuine hole needs the reads
        after it to be missing too.
        """

        dataset = build_dataset(steps=(450, 620, 380), profile=profile)
        cutoff = dataset.cycles_of("sp-1")[0].span.end
        dataset.reads = tuple(read for read in dataset.reads if read.at <= cutoff)
        return dataset

    def test_a_gap_is_estimated_by_default(self) -> None:
        dataset = self._dataset_with_a_gap(preset("model-rules"))
        invoices = Session.of(dataset).rate_all().value
        self.assertTrue(any(invoice.is_estimated for invoice in invoices))

    def test_zero_filling_bills_nothing_for_the_gap(self) -> None:
        profile = preset("model-rules").with_changes(gaps=GapPolicy.ZERO_FILL)
        dataset = self._dataset_with_a_gap(profile)
        invoices = Session.of(dataset).rate_all().value
        second = invoices[1]
        self.assertTrue(second.quality.needs_true_up)
        self.assertTrue(second.subtotal(Basis.ENERGY).is_zero)

    def test_failing_on_a_gap_produces_no_charges(self) -> None:
        profile = preset("model-rules").with_changes(gaps=GapPolicy.FAIL)
        dataset = self._dataset_with_a_gap(profile)
        outcome = Session.of(dataset).rate_all()
        held = [invoice for invoice in outcome.value if invoice.has_errors]
        self.assertTrue(held)
        self.assertEqual(held[0].lines, ())
        self.assertIs(held[0].quality, QualityCode.MISSING)

    def test_holding_suspect_data_stops_the_bill(self) -> None:
        profile = preset("model-rules").with_changes(
            suspect_data=SuspectDataPolicy.HOLD
        )
        dataset = build_dataset(steps=(450, 4000, 380), profile=profile)
        outcome = Session.of(dataset).rate_all()
        self.assertTrue(any(invoice.has_errors for invoice in outcome.value))

    def test_an_estimated_read_taints_the_bill(self) -> None:
        dataset = build_dataset(steps=(450, 620, 380))
        reads = []
        target = dataset.cycles_of("sp-1")[0].span.end
        for read in dataset.reads:
            if read.at == target:
                read = read.with_quality(QualityCode.ESTIMATED)
            reads.append(read)
        dataset.reads = tuple(reads)
        invoices = Session.of(dataset).rate_all().value
        self.assertTrue(invoices[0].is_estimated)
        self.assertIs(invoices[0].quality, QualityCode.ESTIMATED)


class ServicePeriodTests(unittest.TestCase):
    def test_a_move_in_part_way_through_shortens_the_charge(self) -> None:
        dataset = build_dataset(steps=(450,))
        cycle = dataset.cycles_of("sp-1")[0]
        moved = build_dataset(
            steps=(450,),
            connected_at=cycle.span.start + (cycle.span.duration / 2),
        )
        full = Session.of(dataset).rate_all().value[0].line("basic")
        partial = Session.of(moved).rate_all().value[0].line("basic")
        self.assertLess(partial.amount.amount, full.amount.amount)

    def test_service_that_never_started_produces_no_charges(self) -> None:
        dataset = build_dataset(steps=(450,))
        cycle = dataset.cycles_of("sp-1")[0]
        later = build_dataset(steps=(450,), connected_at=cycle.span.end)
        outcome = Session.of(later).rate_all()
        self.assertEqual(outcome.value[0].lines_of(ChargeClass.FIXED), [])
        self.assertIn("rating.not_served", outcome.diagnostics.codes())


if __name__ == "__main__":
    unittest.main()
