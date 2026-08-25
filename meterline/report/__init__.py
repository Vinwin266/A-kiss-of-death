"""Rendering: turning engine output into something a person reads.

Nothing in this package computes a number.  If a report needs a figure the
engine did not produce, the engine is missing a determinant — adding the
arithmetic here would put two implementations of the same rule in the
repository, and they would disagree within a month.
"""

from __future__ import annotations

from .csvout import lines_to_csv, meterdata_to_csv
from .diagnostics_text import render_diagnostics
from .explain import explain_invoice, explain_line
from .invoice_text import render_invoice
from .meterdata_text import render_consumption, render_series
from .summary import render_summary, summarise

__all__ = [
    "explain_invoice",
    "explain_line",
    "lines_to_csv",
    "meterdata_to_csv",
    "render_consumption",
    "render_diagnostics",
    "render_invoice",
    "render_series",
    "render_summary",
    "summarise",
]
