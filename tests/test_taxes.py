"""Taxes, jurisdictions and exemptions."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.charge.basis import Basis
from meterline.charge.classes import ChargeClass
from meterline.charge.context import RatingContext
from meterline.charge.determinant import DeterminantSet
from meterline.charge.lineitem import LineItemBuilder
from meterline.core.money import Money
from meterline.core.quantity import Quantity
from meterline.core.units import Unit
from meterline.errors import ConfigurationError, UnknownReferenceError
from meterline.policy.conventions import TaxCompounding
from meterline.policy.profile import UtilityProfile
from meterline.tax.engine import apply_taxes, tax_total, taxable_base
from meterline.tax.exemption import Exemption, ExemptionSet
from meterline.tax.jurisdiction import Jurisdiction, JurisdictionSet
from meterline.tax.model import TaxKind, TaxRule
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span
from meterline.timeline.zones import common_zone

ZONE = common_zone("America/New_York")


def context(profile: UtilityProfile | None = None) -> RatingContext:
    """Build a rating context with an energy determinant."""

    span = Span(utc(2025, 6, 1), utc(2025, 7, 1))
    determinants = DeterminantSet()
    determinants.put("energy.total", Quantity(Decimal("1000"), Unit.KWH))
    return RatingContext(
        span, span, ZONE, profile or UtilityProfile(), determinants, "sp-1", currency="USD"
    )


def line(code: str, amount: str, charge_class: ChargeClass = ChargeClass.ENERGY):
    """Build one line item."""

    builder = LineItemBuilder(code, code, charge_class, code)
    return builder.seal(Money(Decimal(amount)))


STATE = TaxRule("tax.state", "State tax", TaxKind.PERCENT, "5", "us-ny", order=10)
LOCAL = TaxRule("tax.local", "Local tax", TaxKind.PERCENT, "2", "us-ny-city", order=20)


class TaxRuleTests(unittest.TestCase):
    def test_a_percentage_of_the_total_is_refused(self) -> None:
        with self.assertRaises(ConfigurationError):
            TaxRule("t", "T", TaxKind.PERCENT, "5", basis=Basis.TOTAL)

    def test_rules_describe_themselves(self) -> None:
        self.assertIn("5% of", STATE.describe())
        self.assertIn("per", TaxRule("f", "F", TaxKind.PER_UNIT, "0.01").describe())


class JurisdictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.set = JurisdictionSet.of(
            [
                Jurisdiction("us-ny", "New York", rules=(STATE,)),
                Jurisdiction("us-ny-city", "City", "us-ny", (LOCAL,)),
            ]
        )

    def test_the_chain_runs_inward_out(self) -> None:
        chain = [item.code for item in self.set.chain("us-ny-city")]
        self.assertEqual(chain, ["us-ny-city", "us-ny"])

    def test_rules_are_ordered_by_their_declared_order(self) -> None:
        rules = [rule.code for rule in self.set.rules_for("us-ny-city")]
        self.assertEqual(rules, ["tax.state", "tax.local"])

    def test_an_unknown_jurisdiction_is_reported(self) -> None:
        with self.assertRaises(UnknownReferenceError):
            self.set.get("mars")

    def test_no_jurisdiction_means_no_rules(self) -> None:
        self.assertEqual(self.set.rules_for(""), [])


class TaxEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = [line("energy", "100.00"), line("basic", "20.00", ChargeClass.FIXED)]

    def test_parallel_taxes_share_one_base(self) -> None:
        ctx = context(UtilityProfile(tax_compounding=TaxCompounding.PARALLEL))
        taxes = apply_taxes(ctx, self.lines, [STATE, LOCAL])
        self.assertEqual(taxes[0].amount.amount, Decimal("6.00"))
        self.assertEqual(taxes[1].amount.amount, Decimal("2.40"))

    def test_sequential_taxes_compound(self) -> None:
        ctx = context(UtilityProfile(tax_compounding=TaxCompounding.SEQUENTIAL))
        taxes = apply_taxes(ctx, self.lines, [STATE, LOCAL])
        self.assertEqual(taxes[0].amount.amount, Decimal("6.00"))
        self.assertEqual(taxes[1].amount.amount, Decimal("2.52"))

    def test_a_per_unit_fee_reads_a_determinant(self) -> None:
        rule = TaxRule("fee", "Fee", TaxKind.PER_UNIT, "0.001")
        taxes = apply_taxes(context(), self.lines, [rule])
        self.assertEqual(taxes[0].amount.amount, Decimal("1.000"))

    def test_a_flat_fee_ignores_everything(self) -> None:
        rule = TaxRule("fee", "Fee", TaxKind.FLAT, "3.50")
        taxes = apply_taxes(context(), self.lines, [rule])
        self.assertEqual(taxes[0].amount.amount, Decimal("3.50"))

    def test_an_exempt_class_leaves_the_base(self) -> None:
        rule = TaxRule(
            "t", "T", TaxKind.PERCENT, "10", exempt_classes=(ChargeClass.FIXED,)
        )
        base = taxable_base(self.lines, rule, "USD")
        self.assertEqual(base.amount, Decimal("100.00"))

    def test_a_line_marked_untaxable_leaves_the_base(self) -> None:
        untaxed = line("energy", "100.00")
        stripped = type(untaxed)(
            untaxed.line_id,
            untaxed.code,
            untaxed.label,
            untaxed.charge_class,
            untaxed.amount,
            untaxed.quantity,
            untaxed.rate,
            untaxed.side,
            untaxed.quality,
            untaxed.component,
            False,
            untaxed.trace,
            untaxed.detail,
        )
        base = taxable_base([stripped], STATE, "USD")
        self.assertTrue(base.is_zero)

    def test_a_full_exemption_removes_the_tax(self) -> None:
        exemptions = ExemptionSet()
        exemptions.add(Exemption("ex-1", "tax.state"))
        taxes = apply_taxes(
            context(),
            self.lines,
            [STATE],
            exemptions=exemptions,
            held_exemptions=("ex-1",),
        )
        self.assertEqual(taxes, [])

    def test_a_partial_exemption_reduces_the_tax(self) -> None:
        exemptions = ExemptionSet()
        exemptions.add(Exemption("ex-1", "tax.state", Decimal("50")))
        ctx = context()
        taxes = apply_taxes(
            ctx, self.lines, [STATE], exemptions=exemptions, held_exemptions=("ex-1",)
        )
        self.assertEqual(taxes[0].amount.amount, Decimal("3.00"))
        self.assertIn("tax.exemption.applied", ctx.diagnostics.codes())

    def test_a_capped_exemption_relieves_no_more_than_the_cap(self) -> None:
        exemption = Exemption("ex-1", "tax.state", Decimal("100"), cap=Decimal("2"))
        self.assertEqual(exemption.relief(Decimal("6")), Decimal("2"))
        self.assertFalse(exemption.is_full)

    def test_an_exemption_for_another_tax_does_not_apply(self) -> None:
        exemptions = ExemptionSet()
        exemptions.add(Exemption("ex-1", "tax.other"))
        taxes = apply_taxes(
            context(),
            self.lines,
            [STATE],
            exemptions=exemptions,
            held_exemptions=("ex-1",),
        )
        self.assertEqual(len(taxes), 1)

    def test_tax_lines_are_not_themselves_taxable(self) -> None:
        taxes = apply_taxes(context(), self.lines, [STATE])
        self.assertFalse(taxes[0].taxable)

    def test_the_tax_total_sums_only_tax_lines(self) -> None:
        taxes = apply_taxes(context(), self.lines, [STATE, LOCAL])
        total = tax_total(self.lines + taxes, "USD")
        self.assertEqual(total.amount, Decimal("8.40"))


if __name__ == "__main__":
    unittest.main()
