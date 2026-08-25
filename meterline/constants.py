"""Constants that several subsystems agree on.

Anything in this module is a fact about the domain rather than a policy
choice.  Policy choices live in :mod:`meterline.policy` where they can be
swapped per utility; putting one here by mistake is how a "convention" turns
into a hard-coded assumption nobody can find later.
"""

from __future__ import annotations

from decimal import Decimal

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
SECONDS_PER_HOUR = SECONDS_PER_MINUTE * MINUTES_PER_HOUR
SECONDS_PER_DAY = SECONDS_PER_HOUR * HOURS_PER_DAY
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY

DEFAULT_CURRENCY = "USD"
"""Currency assumed when a dataset does not say."""

DEFAULT_INTERVAL_MINUTES = 15
"""Interval width assumed for channel data that does not declare one."""

SUPPORTED_INTERVAL_MINUTES: tuple[int, ...] = (1, 5, 10, 15, 30, 60)
"""Interval widths the aggregation code can bucket without remainder."""

DEFAULT_DEMAND_WINDOW_MINUTES = 15
"""Width of the demand integration window when a tariff does not declare one."""

MONEY_SCALE = 2
"""Number of decimal places a rendered money amount carries."""

WORKING_SCALE = 10
"""Decimal places retained on intermediate arithmetic before presentation."""

RATE_SCALE = 6
"""Decimal places a published unit rate is quoted to."""

DEGENERATE_TOLERANCE = Decimal("0.000001")
"""Below this magnitude a computed quantity is treated as exactly zero."""

MAX_ESTIMATION_DAYS = 400
"""Longest gap the estimators will attempt to fill before giving up."""

ANNUAL_MONTHS = 12
"""Months in a billing year; used by ratchets and net-metering true-ups."""

RATCHET_LOOKBACK_MONTHS = 11
"""Prior months a demand ratchet inspects, in addition to the current one."""

BILLING_DAYS_NOMINAL = 30
"""Nominal cycle length used by the "normalise to 30 days" conventions."""

__all__ = [
    "ANNUAL_MONTHS",
    "BILLING_DAYS_NOMINAL",
    "DEFAULT_CURRENCY",
    "DEFAULT_DEMAND_WINDOW_MINUTES",
    "DEFAULT_INTERVAL_MINUTES",
    "DEGENERATE_TOLERANCE",
    "HOURS_PER_DAY",
    "MAX_ESTIMATION_DAYS",
    "MINUTES_PER_DAY",
    "MINUTES_PER_HOUR",
    "MONEY_SCALE",
    "RATCHET_LOOKBACK_MONTHS",
    "RATE_SCALE",
    "SECONDS_PER_DAY",
    "SECONDS_PER_HOUR",
    "SECONDS_PER_MINUTE",
    "SUPPORTED_INTERVAL_MINUTES",
    "WORKING_SCALE",
]
