"""Tariffs: the priced rules a bill is produced from.

A tariff is data.  It knows what to charge for and how much, but nothing
about where the numbers came from or what order the charges go in — those
belong to :mod:`meterline.meterdata` and :mod:`meterline.rating`.
"""

from __future__ import annotations

from .catalog import TariffCatalog
from .model import Tariff
from .schedule import TariffSchedule, TariffVersion
from .seasons import Season, SeasonSet
from .windows import TimeWindow, WindowSet, bucket_spans

__all__ = [
    "Season",
    "SeasonSet",
    "Tariff",
    "TariffCatalog",
    "TariffSchedule",
    "TariffVersion",
    "TimeWindow",
    "WindowSet",
    "bucket_spans",
]
