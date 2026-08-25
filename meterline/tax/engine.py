"""Applying tax rules to a set of line items."""

from __future__ import annotations

from typing import Sequence

from ..charge.basis import Basis, basis_amount, basis_includes
from ..charge.classes import ChargeClass
from ..charge.context import RatingContext
from ..charge.lineitem import LineItem, LineItemBuilder
from ..core.decimals import D, is_zero
from ..core.money import Money, total_of
from ..policy.conventions import TaxCompounding
from .exemption import ExemptionSet
from .model import TaxKind, TaxRule

__all__ = ["apply_taxes", "taxable_base"]


def taxable_base(
    lines: Sequence[LineItem], rule: TaxRule, currency: str
) -> Money:
    """Return the base a percentage tax is assessed on.

    Two filters apply.  The rule's basis picks a subtotal, and then any
    charge class the rule exempts is removed from it — a per-line ``taxable``
    flag removes a line as well, which is how a tariff marks a pass-through
    that must not be taxed twice.
    """

    eligible = [
        line
        for line in lines
        if line.taxable
        and basis_includes(rule.basis, line)
        and line.charge_class not in rule.exempt_classes
    ]
    return total_of((line.amount for line in eligible), currency)


def apply_taxes(
    context: RatingContext,
    lines: Sequence[LineItem],
    rules: Sequence[TaxRule],
    *,
    exemptions: ExemptionSet | None = None,
    held_exemptions: tuple[str, ...] = (),
) -> list[LineItem]:
    """Return the tax lines for a bill.

    Under parallel compounding every rule sees the same pre-tax base.  Under
    sequential compounding each rule sees the base plus the taxes already
    added, in declared order — which makes the order of two 5% taxes worth
    a quarter of a percent, and is why the order is stored on the rule
    rather than being the order the rules happened to be written in.
    """

    produced: list[LineItem] = []
    for rule in rules:
        builder = LineItemBuilder(
            rule.code, rule.label, ChargeClass.TAX, rule.code
        )
        builder.exempt()
        if rule.kind is TaxKind.FLAT:
            amount = context.money(rule.rate)
            builder.note("flat tax", "", rule.rate)
        elif rule.kind is TaxKind.PER_UNIT:
            measured = context.optional_quantity(rule.determinant, rule.unit)
            builder.measure(measured, "taxed usage")
            builder.priced_at(rule.rate, "rate per unit")
            amount = context.money(measured.value * rule.rate)
        else:
            base = taxable_base(lines, rule, context.currency)
            if context.profile.tax_compounding is TaxCompounding.SEQUENTIAL:
                # A named basis such as "subtotal" excludes tax lines by
                # construction, so compounding cannot be expressed by
                # widening the basis; the taxes already added are folded in
                # explicitly, minus any the rule exempts.
                already = total_of(
                    (
                        item.amount
                        for item in produced
                        if ChargeClass.TAX not in rule.exempt_classes
                    ),
                    context.currency,
                )
                if not already.is_zero:
                    builder.note("compounding", "sequential", already.format(6))
                    base = base + already
            builder.note(f"base: {rule.basis.label}", "", base.format(6))
            builder.priced_at(rule.rate, "percent")
            amount = base * (rule.rate / D(100))
        if exemptions is not None and held_exemptions:
            exemption = exemptions.for_tax(rule.code, held_exemptions)
            if exemption is not None:
                relief = exemption.relief(amount.amount)
                builder.note("exemption", exemption.code, relief)
                amount = amount - context.money(relief)
                context.notice(
                    "tax.exemption.applied",
                    "an exemption reduced this tax",
                    tax=rule.code,
                    exemption=exemption.code,
                )
        if is_zero(amount.amount):
            continue
        builder.detail(jurisdiction=rule.jurisdiction, kind=rule.kind.value)
        produced.append(builder.seal(amount))
    return produced


def tax_total(lines: Sequence[LineItem], currency: str) -> Money:
    """Return the sum of the tax lines in a bill."""

    return basis_amount(
        [line for line in lines if line.charge_class is ChargeClass.TAX],
        Basis.TOTAL,
        currency,
    )
