"""Turning meter records into billing determinants.

This is the half of the engine that decides *what was used*.  It is kept
strictly separate from the half that decides *what that costs*, because the
two are wrong in different ways: a rating bug produces an obviously wrong
number, while a meter-data bug produces a plausible one.
"""

from __future__ import annotations

from .aggregate import bucket_totals, daily_totals
from .consumption import Consumption, total_quantity
from .demand import DemandPeak, peak_demand, ratchet_floor
from .derive import derive_consumption
from .determinants import build_determinants
from .estimate import estimate_span
from .gaps import find_gaps
from .rollover import register_delta
from .validate import validate_consumption

__all__ = [
    "Consumption",
    "DemandPeak",
    "bucket_totals",
    "build_determinants",
    "daily_totals",
    "derive_consumption",
    "estimate_span",
    "find_gaps",
    "peak_demand",
    "ratchet_floor",
    "register_delta",
    "total_quantity",
    "validate_consumption",
]
