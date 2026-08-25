"""The ``tariff`` command."""

from __future__ import annotations

import argparse

from ...core.diagnostics import Severity
from ...errors import MeterlineError
from ...report.diagnostics_text import render_diagnostics
from ...tariff.validate import validate_tariff
from ..render import EXIT_DIAGNOSTICS, EXIT_OK, emit, fail
from .loading import open_session

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Describe one tariff, or list them all."""

    try:
        session = open_session(args)
    except MeterlineError as error:
        return fail(error)

    catalog = session.dataset.catalog
    codes = [args.code] if args.code else catalog.codes()
    blocks: list[str] = []
    worst = Severity.INFO
    for code in codes:
        try:
            schedule = catalog.schedule(code)
        except MeterlineError as error:
            return fail(error)
        blocks.append(schedule.describe())
        for version in schedule.versions:
            blocks.append(version.tariff.describe())
            bag = validate_tariff(version.tariff)
            if bag:
                blocks.append(render_diagnostics(bag, minimum=Severity.INFO))
                if bag.worst.rank > worst.rank:
                    worst = bag.worst
        blocks.append("")

    emit("\n".join(blocks).rstrip())
    return EXIT_DIAGNOSTICS if worst is Severity.ERROR else EXIT_OK
