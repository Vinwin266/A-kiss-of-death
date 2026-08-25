"""The ``validate`` command."""

from __future__ import annotations

import argparse

from ...core.diagnostics import DiagnosticBag, Severity
from ...errors import MeterlineError
from ...report.diagnostics_text import render_diagnostics, summary_line
from ...tariff.validate import validate_tariff
from ..render import EXIT_DIAGNOSTICS, EXIT_OK, emit, fail
from .loading import open_session

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Check a dataset's references and its tariffs, and report."""

    try:
        session = open_session(args)
    except MeterlineError as error:
        return fail(error)

    dataset = session.dataset
    bag = DiagnosticBag()
    bag.merge(dataset.check_references())
    for code in dataset.catalog.codes():
        for version in dataset.catalog.schedule(code).versions:
            bag.merge(validate_tariff(version.tariff))

    counts = dataset.counts()
    width = max(len(key) for key in counts)
    lines = [f"dataset {dataset.name}"]
    for key in sorted(counts):
        lines.append(f"  {key.ljust(width)}  {counts[key]}")
    lines.append("")
    lines.append(f"conventions: {session.active_profile.name}")
    lines.append("")
    lines.append(render_diagnostics(bag, minimum=Severity.INFO))
    lines.append("")
    lines.append(summary_line(bag))
    emit("\n".join(lines))

    if bag.has_errors:
        return EXIT_DIAGNOSTICS
    if args.strict and bag.warnings:
        return EXIT_DIAGNOSTICS
    return EXIT_OK
