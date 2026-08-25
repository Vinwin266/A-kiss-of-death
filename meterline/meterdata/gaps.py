"""Finding the parts of a period that no data covers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..core.diagnostics import DiagnosticBag, Severity
from ..timeline.spans import Span, merge_spans, subtract_spans
from .consumption import Consumption

__all__ = ["Gap", "find_gaps", "report_gaps", "coverage_fraction"]


@dataclass(frozen=True, slots=True)
class Gap:
    """A stretch of a billing period with no usable consumption."""

    span: Span
    reason: str = "no data"

    @property
    def hours(self):  # noqa: ANN201 - Decimal, kept implicit for brevity
        """Return the length of the gap in hours."""

        return self.span.hours

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.span.describe()} ({self.reason})"


def find_gaps(
    span: Span,
    records: Sequence[Consumption],
    *,
    include_suspect: bool = False,
) -> list[Gap]:
    """Return the uncovered parts of ``span``.

    Records whose quality is unusable are treated as absent, so a period
    covered entirely by a rejected rollover is a gap rather than a silent
    zero — the distinction the whole estimation machinery rests on.
    """

    covered = [
        record.span
        for record in records
        if record.quality.is_billable
        and (include_suspect or record.quality.value != "suspect")
    ]
    holes = subtract_spans(span, merge_spans(covered))
    return [Gap(hole) for hole in holes if not hole.is_empty]


def coverage_fraction(span: Span, records: Sequence[Consumption]):  # noqa: ANN201
    """Return the share of ``span`` covered by usable records."""

    from ..core.decimals import D, safe_divide

    covered = merge_spans([record.span for record in records if record.quality.is_billable])
    total = sum((piece.seconds for piece in covered), 0)
    return safe_divide(D(total), D(span.seconds), default=D(0))


def report_gaps(gaps: Sequence[Gap], subject: str) -> DiagnosticBag:
    """Return a diagnostic per gap."""

    bag = DiagnosticBag()
    for gap in gaps:
        bag.emit(
            "meterdata.gap",
            "no usable meter data covers part of the billing period",
            Severity.WARNING,
            subject,
            span=gap.span.describe(),
            hours=str(gap.hours),
            reason=gap.reason,
        )
    return bag
