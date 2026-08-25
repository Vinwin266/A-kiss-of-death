"""Rendering diagnostics."""

from __future__ import annotations

from typing import Sequence

from ..core.diagnostics import Diagnostic, DiagnosticBag, Severity
from ..core.tables import Column, Table

__all__ = ["render_diagnostics", "diagnostics_table", "counts_by_severity"]


def counts_by_severity(bag: DiagnosticBag) -> dict[Severity, int]:
    """Return how many diagnostics of each severity were recorded."""

    counts: dict[Severity, int] = {}
    for item in bag:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def diagnostics_table(items: Sequence[Diagnostic]) -> Table:
    """Return a table of diagnostics."""

    table = Table(
        (
            Column("severity", "severity"),
            Column("code", "code", max_width=36),
            Column("subject", "subject", max_width=20),
            Column("message", "message", max_width=48),
        )
    )
    for item in items:
        table.add(
            severity=item.severity.value,
            code=item.code,
            subject=item.subject,
            message=item.message,
        )
    return table


def render_diagnostics(
    bag: DiagnosticBag, *, minimum: Severity = Severity.INFO, detail: bool = False
) -> str:
    """Render the diagnostics at or above ``minimum``."""

    items = [item for item in bag.sorted_items() if item.severity.rank >= minimum.rank]
    if not items:
        return "no diagnostics"
    if not detail:
        return diagnostics_table(items).to_text()
    lines: list[str] = []
    for item in items:
        lines.append(item.render())
        for key, value in item.context:
            lines.append(f"    {key}: {value}")
    return "\n".join(lines)


def summary_line(bag: DiagnosticBag) -> str:
    """Return a one-line count of diagnostics by severity."""

    counts = counts_by_severity(bag)
    if not counts:
        return "no diagnostics"
    parts = [
        f"{count} {severity.value}"
        for severity, count in sorted(counts.items(), key=lambda item: -item[0].rank)
    ]
    return ", ".join(parts)
