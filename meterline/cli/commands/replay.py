"""The ``replay`` command: proving a run is reproducible."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...io.jsonio import canonical_dumps
from ...session import Session
from ..render import EXIT_DIAGNOSTICS, EXIT_OK, emit, fail, parse_as_of
from .loading import open_session, selected_points

__all__ = ["run"]


def _render(session: Session, invoices) -> str:  # noqa: ANN001
    """Render a run in a form suitable for byte comparison."""

    return canonical_dumps(
        {
            "fingerprints": session.fingerprints(),
            "bills": [invoice.as_dict() for invoice in invoices],
        }
    )


def run(args: argparse.Namespace) -> int:
    """Rate the same dataset several times and compare the output bytes."""

    passes = max(int(args.passes), 2)
    renders: list[str] = []
    try:
        as_of = parse_as_of(args.as_of)
        for _ in range(passes):
            session = open_session(args)
            outcome = session.rate_all(
                as_of=as_of, service_point_ids=selected_points(session, args)
            )
            renders.append(_render(session, outcome.value))
    except MeterlineError as error:
        return fail(error)

    first = renders[0]
    differing = [index for index, text in enumerate(renders) if text != first]
    if differing:
        emit(
            f"replay FAILED: pass(es) {', '.join(str(index + 1) for index in differing)} "
            f"differ from pass 1"
        )
        return EXIT_DIAGNOSTICS
    emit(
        f"replay ok: {passes} passes produced identical output "
        f"({len(first)} bytes each)"
    )
    return EXIT_OK
