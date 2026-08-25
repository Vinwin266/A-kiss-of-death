"""The ``meters`` command."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...meterdata.derive import derive_consumption
from ...meterdata.gaps import find_gaps
from ...report.csvout import meterdata_to_csv
from ...report.meterdata_text import (
    render_consumption,
    render_gaps,
    render_reads,
    render_series,
)
from ...timeline.spans import Span
from ..render import EXIT_OK, emit, fail
from .loading import open_session, selected_points

__all__ = ["run"]


def _period(session, service_point_id: str) -> Span:  # noqa: ANN001
    """Return the span covered by the service point's cycles."""

    cycles = session.cycles_for(service_point_id)
    if not cycles:
        reads = [read for read in session.dataset.reads]
        if not reads:
            raise MeterlineError("this dataset has no reads and no cycles")
        return Span(reads[0].at, reads[-1].at)
    return Span(cycles[0].span.start, cycles[-1].span.end)


def run(args: argparse.Namespace) -> int:
    """Show reads, derived consumption and any gaps."""

    try:
        session = open_session(args)
        dataset = session.dataset
        blocks: list[str] = []
        csv_records = []
        for service_point_id in selected_points(session, args):
            zone = dataset.zone_of(service_point_id)
            span = _period(session, service_point_id)
            blocks.append(f"service point {service_point_id}")
            for meter in dataset.meters_of(service_point_id):
                for register in meter.registers:
                    reads = dataset.reads_around(
                        meter.meter_id, register.register_id, span
                    )
                    outcome = derive_consumption(
                        register,
                        reads,
                        span,
                        session.active_profile,
                        changes=dataset.changes_of(
                            meter.meter_id, register.register_id
                        ),
                    )
                    records = outcome.value
                    csv_records.extend(records)
                    if args.format == "csv":
                        continue
                    blocks.append(register.describe())
                    blocks.append(render_reads(reads, zone))
                    blocks.append(render_consumption(records, zone))
                    blocks.append(render_gaps(find_gaps(span, records), zone))
                if args.intervals and args.format != "csv":
                    for series in dataset.series_of(meter.meter_id):
                        blocks.append(render_series(series, zone))
    except MeterlineError as error:
        return fail(error)

    if args.format == "csv":
        first = selected_points(session, args)[0]
        emit(meterdata_to_csv(csv_records, dataset.zone_of(first)).rstrip("\n"))
    else:
        emit("\n\n".join(blocks))
    return EXIT_OK
