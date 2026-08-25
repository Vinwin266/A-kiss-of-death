"""Decimal helpers.

Every number that ends up on a bill is a :class:`~decimal.Decimal`.  Floats
are not used anywhere in the rating path — not for rates, not for meter
values, not for day fractions.  A float that reaches a bill is a defect, and
:func:`D` exists to make the conversion boundary explicit and searchable.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable

from ..constants import DEGENERATE_TOLERANCE, WORKING_SCALE
from ..errors import QuantityError

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
HUNDRED = Decimal("100")

__all__ = [
    "D",
    "HUNDRED",
    "ONE",
    "TWO",
    "ZERO",
    "clamp",
    "dsum",
    "is_zero",
    "mean",
    "percent_of",
    "safe_divide",
    "scale_to",
    "sign",
]


def D(value: Any) -> Decimal:
    """Coerce ``value`` into a :class:`Decimal` without going through float.

    Strings, integers and existing decimals pass through the obvious way.  A
    float is accepted but routed via :func:`repr`, which keeps the shortest
    round-tripping decimal rather than the full binary expansion; datasets
    should still quote numbers as strings.
    """

    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise QuantityError("cannot read an empty string as a number")
        try:
            return Decimal(text)
        except InvalidOperation:
            raise QuantityError("not a number", value=value) from None
    raise QuantityError("unsupported numeric type", value=repr(value))


def is_zero(value: Decimal, tolerance: Decimal = DEGENERATE_TOLERANCE) -> bool:
    """Return ``True`` when ``value`` is zero within ``tolerance``.

    Determinants routinely land a few units in the last place away from zero
    after a division and a multiplication; treating those as genuine usage
    produces line items for a hundredth of a cent.
    """

    return abs(value) <= tolerance


def sign(value: Decimal) -> int:
    """Return ``-1``, ``0`` or ``1`` for ``value``, using the zero tolerance."""

    if is_zero(value):
        return 0
    return -1 if value < ZERO else 1


def safe_divide(
    numerator: Decimal, denominator: Decimal, *, default: Decimal = ZERO
) -> Decimal:
    """Divide, returning ``default`` when the denominator is zero.

    Division by zero happens legitimately: a cycle with no days, a channel
    with no intervals, a ratchet with no history.  Every one of those wants a
    documented fallback rather than an exception halfway through a bill.
    """

    if is_zero(denominator):
        return default
    with localcontext() as ctx:
        ctx.prec = 34
        return (numerator / denominator).quantize(
            Decimal(1).scaleb(-WORKING_SCALE)
        )


def percent_of(value: Decimal, percent: Decimal) -> Decimal:
    """Return ``percent`` percent of ``value`` at working precision."""

    return scale_to(value * percent / HUNDRED)


def scale_to(value: Decimal, places: int = WORKING_SCALE) -> Decimal:
    """Round ``value`` to ``places`` decimal places, half-even.

    This is the *internal* precision guard, not a presentation rounding: it
    stops intermediate products from growing an unbounded tail.  Presentation
    rounding is :func:`meterline.core.rounding.quantize` and happens once.
    """

    return value.quantize(Decimal(1).scaleb(-places))


def dsum(values: Iterable[Decimal]) -> Decimal:
    """Sum decimals left to right, returning :data:`ZERO` when empty."""

    total = ZERO
    for value in values:
        total += value
    return total


def mean(values: Iterable[Decimal]) -> Decimal:
    """Return the arithmetic mean, or :data:`ZERO` for an empty sequence."""

    materialised = list(values)
    if not materialised:
        return ZERO
    return safe_divide(dsum(materialised), Decimal(len(materialised)))


def clamp(value: Decimal, low: Decimal | None, high: Decimal | None) -> Decimal:
    """Constrain ``value`` to the inclusive range ``[low, high]``."""

    if low is not None and value < low:
        return low
    if high is not None and value > high:
        return high
    return value
