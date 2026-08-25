"""The ``explain`` command."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...report.explain import explain_invoice, explain_line
from ..render import EXIT_DIAGNOSTICS, EXIT_OK, emit, fail, parse_as_of
from .loading import open_session, selected_points

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Render every line of the selected bills with its working."""

    try:
        session = open_session(args)
        as_of = parse_as_of(args.as_of)
        outcome = session.rate_all(
            as_of=as_of, service_point_ids=selected_points(session, args)
        )
    except MeterlineError as error:
        return fail(error)

    invoices = outcome.value
    if args.cycle:
        invoices = [invoice for invoice in invoices if invoice.cycle_id == args.cycle]
        if not invoices:
            emit(f"no bill was produced for cycle {args.cycle}")
            return EXIT_DIAGNOSTICS

    blocks: list[str] = []
    for invoice in invoices:
        if args.line:
            line = invoice.line(args.line)
            if line is None:
                blocks.append(
                    f"bill {invoice.bill_id} has no line with code {args.line}"
                )
                continue
            blocks.append(explain_line(line))
            continue
        zone = session.dataset.zone_of(invoice.service_point_id)
        blocks.append(explain_invoice(invoice, zone))

    emit("\n\n".join(blocks) if blocks else "no bills to explain", args.out)
    return EXIT_DIAGNOSTICS if outcome.diagnostics.has_errors else EXIT_OK
