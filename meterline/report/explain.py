"""The ``explain`` view: every number with its working shown."""

from __future__ import annotations

from ..charge.lineitem import LineItem
from ..core.text import heading, indent, rule
from ..rating.invoice import Invoice
from ..timeline.zones import Zone

__all__ = ["explain_line", "explain_invoice"]


def explain_line(line: LineItem, *, width: int = 76) -> str:
    """Render one line item and the steps that produced it."""

    header = f"{line.code} — {line.label}"
    body = [header, rule(min(width, len(header)))]
    body.append(f"class      {line.charge_class.value}")
    body.append(f"side       {line.side.value}")
    if line.component:
        body.append(f"component  {line.component}")
    if line.quality.value != "valid":
        body.append(f"quality    {line.quality.value}")
    if line.detail:
        rendered = ", ".join(f"{key}={value}" for key, value in line.detail)
        body.append(f"detail     {rendered}")
    body.append("working:")
    if line.trace:
        body.extend(indent(step.render(), 2) for step in line.trace)
    else:
        body.append("  (no working recorded)")
    body.append(f"amount     {line.amount.format()} {line.amount.currency}")
    return "\n".join(body)


def explain_invoice(invoice: Invoice, zone: Zone, *, width: int = 76) -> str:
    """Render every line of a bill with its working."""

    start, end = invoice.period_dates(zone)
    out: list[str] = [heading(f"Explanation of bill {invoice.bill_id}", width)]
    out.append(f"period        {start.isoformat()} to {end.isoformat()}")
    out.append(f"conventions   {invoice.profile_name}")
    out.append(f"engine        {invoice.engine_version}")
    out.append("")

    if invoice.determinants:
        out.append("determinants")
        for name, value in invoice.determinants:
            out.append(f"  {name:<28}{value}")
        out.append("")

    for line in invoice.ordered_lines():
        out.append(explain_line(line, width=width))
        out.append("")

    if invoice.diagnostics:
        out.append("notes")
        for diagnostic in invoice.diagnostics.sorted_items():
            out.append(f"  {diagnostic.render()}")
        out.append("")

    out.append(f"{'total due':<28}{invoice.total.format():>12} {invoice.currency}")
    return "\n".join(out).rstrip() + "\n"


def explain_determinants(invoice: Invoice) -> str:
    """Render just the determinant block of a bill."""

    if not invoice.determinants:
        return "no determinants were recorded"
    width = max(len(name) for name, _ in invoice.determinants)
    return "\n".join(
        f"{name.ljust(width)}  {value}" for name, value in invoice.determinants
    )
