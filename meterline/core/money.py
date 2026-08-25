"""An exact money type.

:class:`Money` keeps an unrounded :class:`~decimal.Decimal` internally and
only rounds when asked.  That ordering matters: a tariff that multiplies
1,873 kWh by $0.084213 produces $157.73 if you round once at the end and
$157.75 if you round the rate to four places first.  Both appear on real
bills; the engine can produce either, but it never picks by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from ..constants import DEFAULT_CURRENCY, MONEY_SCALE
from ..errors import CurrencyMismatch
from .decimals import ZERO, D, is_zero
from .rounding import RoundingMode, quantize

__all__ = ["Money", "money", "total_of"]


@dataclass(frozen=True, slots=True)
class Money:
    """An amount of a single currency, carried at full precision."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", D(self.amount))
        object.__setattr__(self, "currency", self.currency.upper())

    # -- construction ---------------------------------------------------

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> "Money":
        """Return a zero amount in ``currency``."""

        return cls(ZERO, currency)

    @classmethod
    def parse(cls, text: str, currency: str = DEFAULT_CURRENCY) -> "Money":
        """Read ``"12.34"`` or ``"-12.34"`` into a :class:`Money`."""

        cleaned = text.strip().replace(",", "").lstrip("$")
        return cls(D(cleaned), currency)

    # -- arithmetic -----------------------------------------------------

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(
                "cannot combine amounts in different currencies",
                left=self.currency,
                right=other.currency,
            )

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | str) -> "Money":
        return Money(self.amount * D(factor), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, divisor: Decimal | int | str) -> "Money":
        return Money(self.amount / D(divisor), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    # -- comparison -----------------------------------------------------

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.currency == other.currency and self.amount == other.amount

    def __hash__(self) -> int:
        return hash((self.currency, self.amount))

    # -- inspection -----------------------------------------------------

    @property
    def is_zero(self) -> bool:
        """Return ``True`` when the amount rounds to nothing."""

        return is_zero(self.amount)

    @property
    def is_credit(self) -> bool:
        """Return ``True`` for a negative amount, i.e. money owed back."""

        return self.amount < ZERO

    def quantized(
        self, places: int = MONEY_SCALE, mode: RoundingMode = RoundingMode.HALF_UP
    ) -> "Money":
        """Return a copy rounded for presentation."""

        return Money(quantize(self.amount, places, mode), self.currency)

    def minor_units(self, places: int = MONEY_SCALE) -> int:
        """Return the amount as an integer number of minor units (cents)."""

        return int(quantize(self.amount, places, RoundingMode.HALF_UP).scaleb(places))

    def format(self, places: int = MONEY_SCALE, *, symbol: str = "") -> str:
        """Render the amount, with a leading minus for credits."""

        rounded = quantize(self.amount, places, RoundingMode.HALF_UP)
        sign = "-" if rounded < ZERO else ""
        return f"{sign}{symbol}{abs(rounded):.{places}f}"

    def __str__(self) -> str:
        return f"{self.format()} {self.currency}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Money({self.amount!s}, {self.currency!r})"


def money(value: Any, currency: str = DEFAULT_CURRENCY) -> Money:
    """Convenience constructor: ``money("1.50")``."""

    if isinstance(value, Money):
        return value
    return Money(D(value), currency)


def total_of(amounts: Iterable[Money], currency: str = DEFAULT_CURRENCY) -> Money:
    """Sum an iterable of amounts, tolerating an empty one."""

    total = Money.zero(currency)
    for amount in amounts:
        total = total + amount
    return total
