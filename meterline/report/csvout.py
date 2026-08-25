"""CSV output.

Written by hand rather than with :mod:`csv` so that the quoting rules are
visible and identical on every platform — :class:`csv.writer` defaults to
``\\r\\n`` line endings, which would make two runs on different systems
produce different bytes for the same data.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ..charge.lineitem import LineItem
from ..meterdata.consumption import Consumption
from ..model.series import IntervalSeries
from ..rating.invoice import Invoice
from ..timeline.zones import Zone

__all__ = ["to_csv", "lines_to_csv", "meterdata_to_csv", "series_to_csv"]


def _escape(value: str) -> str:
    """Quote a field when it contains a separator, quote or newline."""

    if any(character in value for character in (',', '"', "\n", "\r")):
        return '"' + value.replace('"', '""') + '"'
    return value


def to_csv(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """Render rows as CSV with Unix line endings and a trailing newline."""

    out = [",".join(_escape(str(header)) for header in headers)]
    for row in rows:
        out.append(",".join(_escape(str(cell)) for cell in row))
    return "\n".join(out) + "\n"


def lines_to_csv(invoice: Invoice) -> str:
    """Render a bill's line items as CSV."""

    headers = (
        "bill_id",
        "service_point_id",
        "code",
        "label",
        "class",
        "side",
        "quantity",
        "unit",
        "rate",
        "amount",
        "currency",
        "quality",
    )
    rows = []
    for line in invoice.ordered_lines():
        rows.append(
            (
                invoice.bill_id,
                invoice.service_point_id,
                line.code,
                line.label,
                line.charge_class.value,
                line.side.value,
                line.quantity.value if line.quantity else "",
                str(line.quantity.unit) if line.quantity else "",
                line.rate if line.rate is not None else "",
                line.amount.format(),
                line.amount.currency,
                line.quality.value,
            )
        )
    return to_csv(headers, rows)


def meterdata_to_csv(records: Sequence[Consumption], zone: Zone) -> str:
    """Render derived consumption as CSV."""

    headers = ("start", "end", "register", "usage", "unit", "quality", "source")
    rows = [
        (
            zone.to_local(record.span.start).isoformat(),
            zone.to_local(record.span.end).isoformat(),
            record.register_id,
            record.quantity.value,
            str(record.unit),
            record.quality.value,
            record.source,
        )
        for record in records
    ]
    return to_csv(headers, rows)


def series_to_csv(series: IntervalSeries, zone: Zone) -> str:
    """Render an interval series as CSV."""

    headers = ("channel", "start", "value", "unit", "quality")
    rows = [
        (
            series.channel_id,
            zone.to_local(point.span.start).isoformat(),
            "" if point.is_missing else point.value,
            str(series.unit),
            point.quality.value,
        )
        for point in series
    ]
    return to_csv(headers, rows)


def summary_to_csv(invoices: Sequence[Invoice]) -> str:
    """Render one row per bill."""

    headers = (
        "bill_id",
        "account_id",
        "service_point_id",
        "start",
        "end",
        "quality",
        "before_tax",
        "tax",
        "total",
        "currency",
    )
    from ..charge.basis import Basis

    rows = [
        (
            invoice.bill_id,
            invoice.account_id,
            invoice.service_point_id,
            invoice.span.start.isoformat(),
            invoice.span.end.isoformat(),
            invoice.quality.value,
            invoice.subtotal(Basis.SUBTOTAL).format(),
            invoice.taxes.format(),
            invoice.total.format(),
            invoice.currency,
        )
        for invoice in invoices
    ]
    return to_csv(headers, rows)
