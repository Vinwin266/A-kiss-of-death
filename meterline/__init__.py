"""meterline — a deterministic utility metering and tariff rating engine.

The engine answers two questions about a billing period and shows its
working for both: what was used, and what that costs.  Both answers depend
on conventions that reasonable utilities implement differently, so every one
of those conventions is named, chosen explicitly in a
:class:`~meterline.policy.profile.UtilityProfile`, and recorded on the bill.

Nothing here reads the clock, the network or a random source.  The same
dataset and the same profile produce the same bytes on any machine, which is
what makes a bill produced today defensible in two years' time.
"""

from __future__ import annotations

from .core.money import Money
from .core.quantity import Quantity
from .core.units import Unit
from .dataset import Dataset
from .errors import (
    ConfigurationError,
    DatasetError,
    MeterDataError,
    MeterlineError,
    PolicyError,
    RatingError,
    TariffError,
    TimelineError,
)
from .policy.presets import PRESETS, preset
from .policy.profile import UtilityProfile
from .rating.invoice import Invoice
from .session import Session
from .version import VERSION, version_string

__all__ = [
    "ConfigurationError",
    "Dataset",
    "DatasetError",
    "Invoice",
    "MeterDataError",
    "MeterlineError",
    "Money",
    "PRESETS",
    "PolicyError",
    "Quantity",
    "RatingError",
    "Session",
    "TariffError",
    "TimelineError",
    "Unit",
    "UtilityProfile",
    "VERSION",
    "preset",
    "version_string",
]
