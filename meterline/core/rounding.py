"""Rounding conventions.

Rounding is the single most reliable source of a penny of disagreement
between two implementations of the same tariff, so it is a first-class,
named, configurable thing here rather than a call to :func:`round`.

Three questions have to be answered separately and utilities answer them
differently:

* which direction ties go (half up, half even, half away from zero);
* what increment the result snaps to (a cent, a nickel, a whole dollar);
* how many times rounding happens (per line item, or once on the total).

This module owns the first two.  The third is a policy convention and lives
in :mod:`meterline.policy.conventions`.
"""

from __future__ import annotations

from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
)
from enum import Enum

from ..errors import ConfigurationError
from .decimals import ZERO, D, is_zero

__all__ = ["RoundingMode", "quantize", "round_to_increment", "exponent_for"]


class RoundingMode(str, Enum):
    """A named tie-breaking rule.

    The values match the ``decimal`` module's own vocabulary where one
    exists, which keeps dataset files readable by anyone who has met
    :mod:`decimal` before.
    """

    HALF_UP = "half_up"
    """Ties move away from zero: 0.125 -> 0.13, -0.125 -> -0.13."""

    HALF_EVEN = "half_even"
    """Ties move to the nearest even digit; the statistician's default."""

    HALF_DOWN = "half_down"
    """Ties move toward zero: 0.125 -> 0.12."""

    UP = "up"
    """Always away from zero, however small the remainder."""

    DOWN = "down"
    """Always toward zero; identical to truncation."""

    CEILING = "ceiling"
    """Always toward positive infinity, which favours the utility."""

    FLOOR = "floor"
    """Always toward negative infinity, which favours the customer."""

    @property
    def decimal_rounding(self) -> str:
        """Return the :mod:`decimal` constant this mode corresponds to."""

        return _DECIMAL_ROUNDING[self]

    @property
    def favours_customer(self) -> bool:
        """Return ``True`` when the mode can only ever reduce a charge.

        Regulators occasionally require that any rounding of a charge be in
        the customer's favour; the tariff validator uses this to check that
        claim rather than trusting a comment in the rate sheet.
        """

        return self in (RoundingMode.FLOOR, RoundingMode.DOWN, RoundingMode.HALF_DOWN)


_DECIMAL_ROUNDING: dict[RoundingMode, str] = {
    RoundingMode.HALF_UP: ROUND_HALF_UP,
    RoundingMode.HALF_EVEN: ROUND_HALF_EVEN,
    RoundingMode.HALF_DOWN: ROUND_HALF_DOWN,
    RoundingMode.UP: ROUND_UP,
    RoundingMode.DOWN: ROUND_DOWN,
    RoundingMode.CEILING: ROUND_CEILING,
    RoundingMode.FLOOR: ROUND_FLOOR,
}


def exponent_for(places: int) -> Decimal:
    """Return the quantisation exponent for ``places`` decimal places."""

    if places < 0:
        raise ConfigurationError("decimal places cannot be negative", places=places)
    return Decimal(1).scaleb(-places)


def quantize(
    value: Decimal,
    places: int,
    mode: RoundingMode = RoundingMode.HALF_UP,
) -> Decimal:
    """Round ``value`` to ``places`` decimal places under ``mode``."""

    return value.quantize(exponent_for(places), rounding=mode.decimal_rounding)


def round_to_increment(
    value: Decimal,
    increment: Decimal,
    mode: RoundingMode = RoundingMode.HALF_UP,
) -> Decimal:
    """Snap ``value`` to the nearest multiple of ``increment``.

    Used for tariffs that bill demand in whole kilowatts, or that round a
    total to the nearest nickel because the utility no longer handles
    pennies.  An increment of zero means "do not snap".
    """

    increment = D(increment)
    if is_zero(increment):
        return value
    if increment < ZERO:
        raise ConfigurationError("increment must be positive", increment=str(increment))
    multiples = (value / increment).quantize(
        Decimal(1), rounding=mode.decimal_rounding
    )
    return multiples * increment
