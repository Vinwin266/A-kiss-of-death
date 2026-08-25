"""Portfolio-level summaries across many bills."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from ..charge.basis import Basis
from ..core.decimals import ZERO, D, safe_divide
from ..core.money import Money
from ..core.tables import Column, Table
from ..model.quality import QualityCode
from ..rating.invoice import Invoice

__all__ = ["Summary", "summarise", "render_summary"]


@dataclass(slots=True)
class Summary:
    """Aggregate figures over a run of bills."""

    currency: str
    count: int = 0
    total: Money | None = None
    before_tax: Money | None = None
    tax: Money | None = None
    estimated_count: int = 0
    error_count: int = 0
    quality_counts: dict[QualityCode, int] = field(default_factory=dict)
    largest: Invoice | None = None

    @property
    def average(self) -> Money:
        """Return the mean bill, or zero when there are none."""

        if not self.count or self.total is None:
            return Money.zero(self.currency)
        return Money(safe_divide(self.total.amount, D(self.count)), self.currency)

    @property
    def estimated_share(self) -> Decimal:
        """Return the fraction of bills resting on estimated data."""

        return safe_divide(D(self.estimated_count), D(self.count), default=ZERO)


def summarise(invoices: Sequence[Invoice], currency: str = "USD") -> Summary:
    """Aggregate a run of bills."""

    summary = Summary(currency)
    total = Money.zero(currency)
    before = Money.zero(currency)
    tax = Money.zero(currency)
    for invoice in invoices:
        summary.count += 1
        total = total + invoice.total
        before = before + invoice.subtotal(Basis.SUBTOTAL)
        tax = tax + invoice.taxes
        if invoice.is_estimated:
            summary.estimated_count += 1
        if invoice.has_errors:
            summary.error_count += 1
        summary.quality_counts[invoice.quality] = (
            summary.quality_counts.get(invoice.quality, 0) + 1
        )
        if summary.largest is None or invoice.total > summary.largest.total:
            summary.largest = invoice
    summary.total = total
    summary.before_tax = before
    summary.tax = tax
    return summary


def render_summary(summary: Summary) -> str:
    """Render a summary as aligned lines."""

    rows = [
        ("bills", str(summary.count)),
        ("total", (summary.total or Money.zero(summary.currency)).format()),
        ("before tax", (summary.before_tax or Money.zero(summary.currency)).format()),
        ("tax", (summary.tax or Money.zero(summary.currency)).format()),
        ("average bill", summary.average.format()),
        ("estimated bills", str(summary.estimated_count)),
        ("bills with errors", str(summary.error_count)),
    ]
    if summary.largest is not None:
        rows.append(
            ("largest bill", f"{summary.largest.service_point_id} {summary.largest.total.format()}")
        )
    width = max(len(label) for label, _ in rows)
    lines = [f"{label.ljust(width)}  {value}" for label, value in rows]
    if summary.quality_counts:
        lines.append("")
        lines.append("data quality")
        for quality in sorted(summary.quality_counts, key=lambda code: code.rank):
            lines.append(f"  {quality.value:<12}{summary.quality_counts[quality]}")
    return "\n".join(lines)


def summary_table(invoices: Sequence[Invoice]) -> Table:
    """Return a one-row-per-bill table."""

    table = Table(
        (
            Column("service_point", "service point"),
            Column("period", "period"),
            Column("quality", "quality"),
            Column("total", "total", align="right"),
        )
    )
    for invoice in invoices:
        table.add(
            service_point=invoice.service_point_id,
            period=invoice.span.start.date().isoformat(),
            quality=invoice.quality.value,
            total=invoice.total.format(),
        )
    return table
