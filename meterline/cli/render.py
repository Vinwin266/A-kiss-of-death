"""Output helpers shared by the commands."""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

from ..core.diagnostics import DiagnosticBag, Severity
from ..errors import MeterlineError
from ..io.files import write_text
from ..io.jsonio import canonical_dumps
from ..report.diagnostics_text import render_diagnostics
from ..timeline.instants import parse_date

__all__ = ["emit", "emit_json", "report_diagnostics", "parse_as_of", "fail"]

EXIT_OK = 0
EXIT_DIAGNOSTICS = 1
EXIT_USAGE = 2


def emit(text: str, out: str | None = None) -> None:
    """Write text to a file or to standard output."""

    if out:
        write_text(out, text if text.endswith("\n") else text + "\n")
        return
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def emit_json(document: Any, out: str | None = None) -> None:
    """Write a document as canonical JSON."""

    emit(canonical_dumps(document).rstrip("\n"), out)


def report_diagnostics(
    bag: DiagnosticBag, *, minimum: Severity = Severity.WARNING
) -> None:
    """Print diagnostics to standard error, if there are any."""

    items = [item for item in bag.sorted_items() if item.severity.rank >= minimum.rank]
    if not items:
        return
    sys.stderr.write(render_diagnostics(bag, minimum=minimum) + "\n")


def parse_as_of(value: str | None) -> date | None:
    """Parse the ``--as-of`` option."""

    if not value:
        return None
    return parse_date(value, what="--as-of")


def fail(error: MeterlineError) -> int:
    """Print an engine error and return the usage exit code."""

    sys.stderr.write(f"error: {error}\n")
    return EXIT_USAGE
