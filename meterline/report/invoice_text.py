"""The plain-text bill."""

from __future__ import annotations

from ..charge.basis import Basis
from ..charge.classes import ChargeClass
from ..core.tables import Column, Table
from ..core.text import heading, rule
from ..rating.invoice import Invoice
from ..timeline.zones import Zone

__all__ = ["render_invoice", "invoice_table"]


def invoice_table(invoice: Invoice) -> Table:
    """Return the line-item table of a bill."""

    table = Table(
        (
            Column("code", "code"),
            Column("label", "description", max_width=38),
            Column("quantity", "quantity", align="right"),
            Column("rate", "rate", align="right"),
            Column("amount", "amount", align="right"),
        )
    )
    for line in invoice.ordered_lines():
        table.add(
            code=line.code,
            label=line.label,
            quantity=line.quantity.format(1) if line.quantity else "",
            rate=str(line.rate) if line.rate is not None else "",
            amount=line.amount.format(),
        )
    return table


def render_invoice(invoice: Invoice, zone: Zone, *, width: int = 76) -> str:
    """Render a whole bill as text."""

    start, end = invoice.period_dates(zone)
    lines: list[str] = []
    lines.append(heading(f"Bill {invoice.bill_id}", width))
    lines.append(f"account         {invoice.account_id}")
    lines.append(f"service point   {invoice.service_point_id}")
    lines.append(f"period          {start.isoformat()} to {end.isoformat()}")
    lines.append(f"tariff          {', '.join(invoice.tariff_codes) or 'none'}")
    lines.append(f"conventions     {invoice.profile_name}")
    lines.append(f"data quality    {invoice.quality.value}")
    lines.append("")
    lines.extend(invoice_table(invoice).render())
    lines.append(rule(width))

    subtotals = [
        ("energy", invoice.subtotal(Basis.ENERGY)),
        ("fixed", invoice.subtotal(Basis.FIXED)),
        ("demand", invoice.subtotal(Basis.DEMAND)),
    ]
    for label, amount in subtotals:
        if not amount.is_zero:
            lines.append(f"{label:<28}{amount.format():>12}")
    lines.append(f"{'before tax':<28}{invoice.subtotal(Basis.SUBTOTAL).format():>12}")
    if not invoice.taxes.is_zero:
        lines.append(f"{'tax':<28}{invoice.taxes.format():>12}")
    lines.append(rule(width))
    lines.append(f"{'total due':<28}{invoice.total.format():>12} {invoice.currency}")

    if invoice.credit_carried_out is not None and not invoice.credit_carried_out.is_zero:
        lines.append("")
        lines.append(
            f"credit banked for future bills: {invoice.credit_carried_out.format()}"
        )
    if invoice.is_estimated:
        lines.append("")
        lines.append(
            "This bill includes estimated usage and will be corrected when an "
            "actual read is taken."
        )
    return "\n".join(lines)


def render_invoice_compact(invoice: Invoice) -> str:
    """Render a one-line summary of a bill, for list output."""

    return (
        f"{invoice.service_point_id}  {invoice.span.start.date().isoformat()}  "
        f"{invoice.total.format():>10} {invoice.currency}  {invoice.quality.value}"
    )


def class_breakdown(invoice: Invoice) -> Table:
    """Return a table of subtotals by charge class."""

    table = Table(
        (Column("class", "charge class"), Column("amount", "amount", align="right")),
        title="breakdown",
    )
    totals = invoice.by_class()
    for charge_class in sorted(totals, key=lambda item: item.sort_order):
        table.add(**{"class": charge_class.value, "amount": totals[charge_class].format()})
    return table


def taxes_table(invoice: Invoice) -> Table:
    """Return a table of the tax lines on a bill."""

    table = Table(
        (
            Column("code", "tax"),
            Column("label", "description", max_width=40),
            Column("amount", "amount", align="right"),
        ),
        title="taxes",
    )
    for line in invoice.lines_of(ChargeClass.TAX):
        table.add(code=line.code, label=line.label, amount=line.amount.format())
    return table
