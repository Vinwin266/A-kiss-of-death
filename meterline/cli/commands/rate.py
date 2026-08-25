"""The ``rate`` command."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...report.csvout import summary_to_csv
from ...report.invoice_text import render_invoice
from ...report.summary import render_summary
from ..render import (
    EXIT_DIAGNOSTICS,
    EXIT_OK,
    emit,
    emit_json,
    parse_as_of,
    report_diagnostics,
)
from .loading import open_session, selected_points

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Produce bills and render them in the requested format."""

    try:
        session = open_session(args)
        as_of = parse_as_of(args.as_of)
        outcome = session.rate_all(
            as_of=as_of, service_point_ids=selected_points(session, args)
        )
    except MeterlineError as error:
        from ..render import fail

        return fail(error)

    invoices = outcome.value
    if args.format == "json":
        emit_json(
            {
                "dataset": session.dataset.name,
                "profile": session.active_profile.name,
                "fingerprints": session.fingerprints(),
                "bills": [invoice.as_dict() for invoice in invoices],
            },
            args.out,
        )
    elif args.format == "csv":
        emit(summary_to_csv(invoices).rstrip("\n"), args.out)
    else:
        blocks = []
        for invoice in invoices:
            zone = session.dataset.zone_of(invoice.service_point_id)
            blocks.append(render_invoice(invoice, zone))
        summary = session.summarise(invoices)
        blocks.append("")
        blocks.append(render_summary(summary))
        emit("\n\n".join(blocks), args.out)

    report_diagnostics(outcome.diagnostics)
    return EXIT_DIAGNOSTICS if outcome.diagnostics.has_errors else EXIT_OK
