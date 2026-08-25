"""Small, dependency-free primitives the rest of the engine is built from.

Nothing in :mod:`meterline.core` knows about meters, tariffs or bills.  The
rule is deliberately strict: if a helper needs to import from a domain
package to do its job, it belongs in that domain package instead.
"""

from __future__ import annotations

from .decimals import D, ONE, ZERO, is_zero, safe_divide
from .diagnostics import Diagnostic, DiagnosticBag, Severity
from .money import Money, money
from .outcome import Outcome
from .quantity import Quantity
from .rounding import RoundingMode, quantize, round_to_increment
from .units import Unit, UnitKind

__all__ = [
    "D",
    "Diagnostic",
    "DiagnosticBag",
    "Money",
    "ONE",
    "Outcome",
    "Quantity",
    "RoundingMode",
    "Severity",
    "Unit",
    "UnitKind",
    "ZERO",
    "is_zero",
    "money",
    "quantize",
    "round_to_increment",
    "safe_divide",
]
