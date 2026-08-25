"""Tariff components, one at a time."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

from meterline.charge.basis import Basis
from meterline.charge.classes import ChargeClass
from meterline.charge.context import RatingContext
from meterline.charge.determinant import DeterminantSet
from meterline.core.quantity import Quantity
from meterline.core.units import Unit
from meterline.errors import TariffError
from meterline.model.quality import QualityCode
from meterline.policy.conventions import (
    CreditValuation,
    MinimumBasis,
    ProrationBasis,
    RatchetBasis,
    TierBasis,
)
from meterline.policy.profile import UtilityProfile
from meterline.tariff.components.blocks import Block, allocate_blocks, validate_blocks
from meterline.tariff.components.credit import ExportCredit
from meterline.tariff.components.demand import DemandCharge
from meterline.tariff.components.discount import AssistanceDiscount
from meterline.tariff.components.fixed import FixedCharge
from meterline.tariff.components.minimum import MinimumCharge
from meterline.tariff.components.reactive import PowerFactorCharge
from meterline.tariff.components.rider import Rider, RiderKind
from meterline.tariff.components.step import SteppedCharge
from meterline.tariff.components.tiered import TieredCharge
from meterline.tariff.components.tou import TouCharge
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span
from meterline.timeline.zones import common_zone

ZONE = common_zone("America/New_York")


def context(
    profile: UtilityProfile | None = None,
    *,
    days: int = 30,
    determinants: dict[str, Quantity] | None = None,
    qualities: dict[str, QualityCode] | None = None,
) -> RatingContext:
    """Build a rating context over a run of whole days in June 2025."""

    start = ZONE.day_start(date(2025, 6, 1))
    span = Span(start, start + timedelta(days=days))
    determinant_set = DeterminantSet()
    for name, quantity in (determinants or {"energy.total": Quantity(Decimal("700"), Unit.KWH)}).items():
        determinant_set.put(name, quantity, (qualities or {}).get(name, QualityCode.VALID))
    return RatingContext(
        span,
        span,
        ZONE,
        profile or UtilityProfile(),
        determinant_set,
        service_point_id="sp-1",
        currency="USD",
    )


class BlockTests(unittest.TestCase):
    def test_allocation_splits_marginally(self) -> None:
        blocks = [Block.of(500, "0.10"), Block.of(None, "0.15")]
        self.assertEqual(
            allocate_blocks(Decimal("700"), blocks), [Decimal("500"), Decimal("200")]
        )

    def test_allocation_sums_to_the_input(self) -> None:
        blocks = [Block.of(100, "1"), Block.of(300, "2"), Block.of(None, "3")]
        parts = allocate_blocks(Decimal("250"), blocks)
        self.assertEqual(sum(parts), Decimal("250"))

    def test_a_negative_quantity_lands_in_the_first_block(self) -> None:
        blocks = [Block.of(500, "0.10"), Block.of(None, "0.15")]
        self.assertEqual(
            allocate_blocks(Decimal("-40"), blocks), [Decimal("-40"), Decimal("0")]
        )

    def test_a_scale_moves_the_thresholds(self) -> None:
        blocks = [Block.of(500, "0.10"), Block.of(None, "0.15")]
        parts = allocate_blocks(Decimal("700"), blocks, Decimal("2"))
        self.assertEqual(parts, [Decimal("700"), Decimal("0")])

    def test_limits_must_ascend(self) -> None:
        with self.assertRaises(TariffError):
            validate_blocks([Block.of(500, "0.1"), Block.of(200, "0.2"), Block.of(None, "1")])

    def test_only_the_last_block_may_be_open(self) -> None:
        with self.assertRaises(TariffError):
            validate_blocks([Block.of(None, "0.1"), Block.of(500, "0.2")])

    def test_the_last_block_must_be_open(self) -> None:
        with self.assertRaises(TariffError):
            validate_blocks([Block.of(500, "0.1")])


class FixedChargeTests(unittest.TestCase):
    def test_a_full_month_is_the_full_amount(self) -> None:
        component = FixedCharge("basic", "Basic", "12.00")
        line = component.compute(context(days=30), ())[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("12.00"))

    def test_no_proration_bills_a_short_period_in_full(self) -> None:
        profile = UtilityProfile(proration=ProrationBasis.NONE)
        line = FixedCharge("basic", "Basic", "12.00").compute(
            context(profile, days=10), ()
        )[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("12.00"))

    def test_daily_proration_scales_a_short_period(self) -> None:
        profile = UtilityProfile(proration=ProrationBasis.DAILY_ACTUAL)
        line = FixedCharge("basic", "Basic", "12.00").compute(
            context(profile, days=10), ()
        )[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("4.00"))

    def test_nominal_thirty_ignores_the_month_length(self) -> None:
        profile = UtilityProfile(proration=ProrationBasis.DAILY_NOMINAL_30)
        line = FixedCharge("basic", "Basic", "30.00").compute(
            context(profile, days=10), ()
        )[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("10.00"))

    def test_a_per_day_charge_multiplies_by_days(self) -> None:
        line = FixedCharge("basic", "Basic", "0.50", per="day").compute(
            context(days=10), ()
        )[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("5.00"))

    def test_an_unknown_period_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            FixedCharge("basic", "Basic", "1", per="fortnight")

    def test_the_line_records_its_working(self) -> None:
        line = FixedCharge("basic", "Basic", "12.00").compute(context(), ())[0]
        labels = [step.label for step in line.trace]
        self.assertIn("proration", labels)


class TieredChargeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.component = TieredCharge(
            "energy",
            "Energy",
            [Block.of(500, "0.10", "first"), Block.of(None, "0.15", "rest")],
        )

    def test_one_line_per_occupied_block(self) -> None:
        lines = self.component.compute(context(), ())
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].amount.amount, Decimal("50.00"))
        self.assertEqual(lines[1].amount.amount, Decimal("30.00"))

    def test_empty_blocks_are_omitted(self) -> None:
        small = context(determinants={"energy.total": Quantity(Decimal("100"), Unit.KWH)})
        self.assertEqual(len(self.component.compute(small, ())), 1)

    def test_a_daily_tier_basis_grows_the_threshold(self) -> None:
        component = TieredCharge(
            "energy", "Energy", [Block.of(30, "0.10"), Block.of(None, "0.15")]
        )
        # Per bill, a 30 kWh first block is exhausted immediately.
        per_cycle = component.compute(context(UtilityProfile(tier_basis=TierBasis.CYCLE)), ())
        self.assertEqual(len(per_cycle), 2)
        # Per day over a 30-day cycle it becomes 900 kWh and swallows the lot.
        daily = component.compute(
            context(UtilityProfile(tier_basis=TierBasis.DAILY), days=30), ()
        )
        self.assertEqual(len(daily), 1)

    def test_the_quality_of_the_determinant_reaches_the_line(self) -> None:
        estimated = context(
            determinants={"energy.total": Quantity(Decimal("700"), Unit.KWH)},
            qualities={"energy.total": QualityCode.ESTIMATED},
        )
        lines = self.component.compute(estimated, ())
        self.assertIs(lines[0].quality, QualityCode.ESTIMATED)


class SteppedChargeTests(unittest.TestCase):
    def test_the_whole_quantity_takes_the_band_rate(self) -> None:
        component = SteppedCharge(
            "energy", "Energy", [Block.of(500, "0.10"), Block.of(None, "0.15")]
        )
        lines = component.compute(context(), ())
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].amount.amount, Decimal("105.00"))

    def test_stepping_costs_more_than_tiering_above_a_threshold(self) -> None:
        blocks = [Block.of(500, "0.10"), Block.of(None, "0.15")]
        tiered = TieredCharge("t", "T", blocks).compute(context(), ())
        stepped = SteppedCharge("s", "S", blocks).compute(context(), ())
        self.assertGreater(
            stepped[0].amount.amount, sum(line.amount.amount for line in tiered)
        )


class TouChargeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.component = TouCharge(
            "energy", "Energy", {"peak": "0.20", "offpeak": "0.07"}
        )
        self.context = context(
            determinants={
                "energy.bucket.peak": Quantity(Decimal("100"), Unit.KWH),
                "energy.bucket.offpeak": Quantity(Decimal("600"), Unit.KWH),
            }
        )

    def test_one_line_per_bucket(self) -> None:
        lines = self.component.compute(self.context, ())
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            {line.code for line in lines}, {"energy.peak", "energy.offpeak"}
        )

    def test_a_missing_bucket_is_a_notice_not_a_failure(self) -> None:
        partial = context(
            determinants={"energy.bucket.peak": Quantity(Decimal("100"), Unit.KWH)}
        )
        lines = self.component.compute(partial, ())
        self.assertEqual(len(lines), 1)
        self.assertIn("tariff.tou.missing_bucket", partial.diagnostics.codes())

    def test_a_strict_component_demands_every_bucket(self) -> None:
        strict = TouCharge(
            "energy", "Energy", {"peak": "0.20", "offpeak": "0.07"}, require_all=True
        )
        partial = context(
            determinants={"energy.bucket.peak": Quantity(Decimal("100"), Unit.KWH)}
        )
        with self.assertRaises(Exception):
            strict.compute(partial, ())

    def test_a_component_needs_at_least_one_rate(self) -> None:
        with self.assertRaises(TariffError):
            TouCharge("energy", "Energy", {})


class DemandChargeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.component = DemandCharge("demand", "Demand", "10.00")

    def test_the_measured_peak_is_billed(self) -> None:
        ctx = context(determinants={"demand.peak": Quantity(Decimal("40"), Unit.KW)})
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("400.00"))

    def test_no_demand_produces_no_line(self) -> None:
        ctx = context(determinants={"demand.peak": Quantity(Decimal("0"), Unit.KW)})
        self.assertEqual(self.component.compute(ctx, ()), [])

    def test_the_ratchet_lifts_a_low_peak(self) -> None:
        profile = UtilityProfile(ratchet=RatchetBasis.ANNUAL_PEAK, ratchet_percent="60")
        ctx = context(
            profile,
            determinants={
                "demand.peak": Quantity(Decimal("40"), Unit.KW),
                "demand.ratchet_floor": Quantity(Decimal("100"), Unit.KW),
            },
        )
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("600.00"))

    def test_the_ratchet_does_not_lower_a_high_peak(self) -> None:
        profile = UtilityProfile(ratchet=RatchetBasis.ANNUAL_PEAK, ratchet_percent="60")
        ctx = context(
            profile,
            determinants={
                "demand.peak": Quantity(Decimal("200"), Unit.KW),
                "demand.ratchet_floor": Quantity(Decimal("100"), Unit.KW),
            },
        )
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("2000.00"))

    def test_a_declared_ratchet_without_history_is_noted(self) -> None:
        profile = UtilityProfile(ratchet=RatchetBasis.ANNUAL_PEAK)
        ctx = context(profile, determinants={"demand.peak": Quantity(Decimal("40"), Unit.KW)})
        self.component.compute(ctx, ())
        self.assertIn("tariff.demand.no_ratchet_history", ctx.diagnostics.codes())

    def test_a_contract_minimum_applies_without_a_ratchet(self) -> None:
        component = DemandCharge("demand", "Demand", "10.00", minimum_billed="50")
        ctx = context(determinants={"demand.peak": Quantity(Decimal("40"), Unit.KW)})
        line = component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("500.00"))

    def test_billed_demand_can_snap_to_whole_kilowatts(self) -> None:
        profile = UtilityProfile(demand_increment="1")
        ctx = context(
            profile, determinants={"demand.peak": Quantity(Decimal("40.4"), Unit.KW)}
        )
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("400.00"))


class RiderTests(unittest.TestCase):
    def test_a_per_unit_rider_multiplies_the_determinant(self) -> None:
        line = Rider("r", "Rider", "0.01").compute(context(), ())[0]
        self.assertEqual(line.amount.amount, Decimal("7.00"))

    def test_a_percentage_rider_reads_the_lines_before_it(self) -> None:
        ctx = context()
        energy = TieredCharge(
            "energy", "Energy", [Block.of(None, "0.10")]
        ).compute(ctx, ())
        rider = Rider("r", "Rider", "10", rider_kind=RiderKind.PERCENT)
        line = rider.compute(ctx, tuple(energy))[0]
        self.assertEqual(line.amount.amount, Decimal("7.000"))

    def test_a_percentage_of_the_total_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            Rider("r", "Rider", "10", rider_kind=RiderKind.PERCENT, basis=Basis.TOTAL)

    def test_a_flat_rider_prorates(self) -> None:
        profile = UtilityProfile(proration=ProrationBasis.DAILY_ACTUAL)
        rider = Rider("r", "Rider", "30.00", rider_kind=RiderKind.FLAT)
        line = rider.compute(context(profile, days=10), ())[0]
        self.assertEqual(line.amount.quantized().amount, Decimal("10.00"))

    def test_a_rider_worth_nothing_produces_no_line(self) -> None:
        ctx = context(determinants={"energy.total": Quantity(Decimal("0"), Unit.KWH)})
        self.assertEqual(Rider("r", "Rider", "0.01").compute(ctx, ()), [])


class MinimumChargeTests(unittest.TestCase):
    def test_a_shortfall_is_made_up(self) -> None:
        ctx = context()
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.01")]).compute(ctx, ())
        line = MinimumCharge("min", "Minimum", "20.00").compute(ctx, tuple(energy))[0]
        self.assertEqual(line.amount.amount, Decimal("13.00"))
        self.assertIs(line.charge_class, ChargeClass.MINIMUM)

    def test_a_bill_above_the_floor_gets_no_line(self) -> None:
        ctx = context()
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.10")]).compute(ctx, ())
        self.assertEqual(
            MinimumCharge("min", "Minimum", "20.00").compute(ctx, tuple(energy)), []
        )

    def test_the_basis_changes_what_counts(self) -> None:
        profile = UtilityProfile(minimum_basis=MinimumBasis.ENERGY_ONLY)
        ctx = context(profile)
        fixed = FixedCharge("basic", "Basic", "18.00").compute(ctx, ())
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.01")]).compute(ctx, ())
        lines = MinimumCharge("min", "Minimum", "20.00").compute(
            ctx, tuple(fixed) + tuple(energy)
        )
        self.assertEqual(lines[0].amount.amount, Decimal("13.00"))

    def test_a_wider_basis_absorbs_the_fixed_charge(self) -> None:
        profile = UtilityProfile(minimum_basis=MinimumBasis.ENERGY_AND_FIXED)
        ctx = context(profile)
        fixed = FixedCharge("basic", "Basic", "18.00").compute(ctx, ())
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.01")]).compute(ctx, ())
        self.assertEqual(
            MinimumCharge("min", "Minimum", "20.00").compute(
                ctx, tuple(fixed) + tuple(energy)
            ),
            [],
        )


class CreditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.component = ExportCredit(
            "export", "Export", retail_rate="0.12", avoided_cost_rate="0.04"
        )
        self.determinants = {"energy.exported": Quantity(Decimal("200"), Unit.KWH)}

    def test_retail_valuation_credits_the_full_rate(self) -> None:
        ctx = context(determinants=self.determinants)
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("-24.00"))

    def test_avoided_cost_credits_less(self) -> None:
        profile = UtilityProfile(credit_valuation=CreditValuation.AVOIDED_COST)
        ctx = context(profile, determinants=self.determinants)
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("-8.00"))

    def test_a_percentage_of_retail_sits_between(self) -> None:
        profile = UtilityProfile(
            credit_valuation=CreditValuation.PERCENT_OF_RETAIL,
            credit_percent_of_retail="50",
        )
        ctx = context(profile, determinants=self.determinants)
        line = self.component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("-12.00"))

    def test_no_export_produces_no_line(self) -> None:
        ctx = context(determinants={"energy.exported": Quantity(Decimal("0"), Unit.KWH)})
        self.assertEqual(self.component.compute(ctx, ()), [])


class DiscountTests(unittest.TestCase):
    def test_a_percentage_discount_reduces_the_bill(self) -> None:
        ctx = context()
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.10")]).compute(ctx, ())
        discount = AssistanceDiscount("d", "Discount", percent="10", programme="LIHEAP")
        line = discount.compute(ctx, tuple(energy))[0]
        self.assertEqual(line.amount.amount, Decimal("-7.000"))

    def test_a_cap_limits_the_discount(self) -> None:
        ctx = context()
        energy = TieredCharge("energy", "Energy", [Block.of(None, "0.10")]).compute(ctx, ())
        discount = AssistanceDiscount(
            "d", "Discount", percent="50", cap="5.00", programme="LIHEAP"
        )
        line = discount.compute(ctx, tuple(energy))[0]
        self.assertEqual(line.amount.amount, Decimal("-5.00"))

    def test_a_discount_only_applies_to_its_own_programme(self) -> None:
        discount = AssistanceDiscount("d", "Discount", percent="10", programme="LIHEAP")
        self.assertTrue(discount.applies_to("LIHEAP"))
        self.assertFalse(discount.applies_to("OTHER"))

    def test_a_worthless_discount_produces_no_line(self) -> None:
        discount = AssistanceDiscount("d", "Discount", programme="LIHEAP")
        self.assertEqual(discount.compute(context(), ()), [])


class ReactiveTests(unittest.TestCase):
    def test_reactive_energy_below_the_allowance_is_free(self) -> None:
        component = PowerFactorCharge("pf", "Reactive", "0.01")
        ctx = context(
            determinants={
                "energy.total": Quantity(Decimal("1000"), Unit.KWH),
                "reactive.total": Quantity(Decimal("200"), Unit.KVARH),
            }
        )
        self.assertEqual(component.compute(ctx, ()), [])

    def test_reactive_energy_above_the_allowance_is_charged(self) -> None:
        component = PowerFactorCharge("pf", "Reactive", "0.01")
        ctx = context(
            determinants={
                "energy.total": Quantity(Decimal("1000"), Unit.KWH),
                "reactive.total": Quantity(Decimal("500"), Unit.KVARH),
            }
        )
        line = component.compute(ctx, ())[0]
        self.assertEqual(line.amount.amount, Decimal("2.00"))

    def test_the_power_factor_mode_penalises_a_poor_factor(self) -> None:
        component = PowerFactorCharge(
            "pf", "Reactive", "1.00", mode="power_factor", target_power_factor="0.95"
        )
        ctx = context(
            determinants={
                "energy.total": Quantity(Decimal("1000"), Unit.KWH),
                "reactive.total": Quantity(Decimal("800"), Unit.KVARH),
            }
        )
        lines = component.compute(ctx, ())
        self.assertEqual(len(lines), 1)
        self.assertGreater(lines[0].amount.amount, Decimal("0"))

    def test_a_good_power_factor_is_not_penalised(self) -> None:
        component = PowerFactorCharge(
            "pf", "Reactive", "1.00", mode="power_factor", target_power_factor="0.90"
        )
        ctx = context(
            determinants={
                "energy.total": Quantity(Decimal("1000"), Unit.KWH),
                "reactive.total": Quantity(Decimal("100"), Unit.KVARH),
            }
        )
        self.assertEqual(component.compute(ctx, ()), [])


if __name__ == "__main__":
    unittest.main()
