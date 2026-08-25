"""The credit bank: what happens to an export credit nobody used.

A customer who generates more than they consume ends a cycle with a credit.
Whether that credit is money, a promise, or nothing at all a year later is a
policy question with four defensible answers, and this is the state that
makes those answers different from each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Sequence

from ..core.decimals import ZERO, D
from ..core.money import Money
from ..timeline.calendars import MonthKey

__all__ = ["MovementKind", "BankMovement", "CreditBank"]


class MovementKind(str, Enum):
    """What happened to a bank balance."""

    EARNED = "earned"
    """A credit exceeding the bill was banked."""

    APPLIED = "applied"
    """Banked credit was used to reduce a bill."""

    EXPIRED = "expired"
    """Banked credit passed its expiry and was removed."""

    CASHED_OUT = "cashed_out"
    """Banked credit was paid to the customer at the true-up."""

    FORFEITED = "forfeited"
    """Banked credit was removed at the true-up with no payment."""


@dataclass(frozen=True, slots=True)
class BankMovement:
    """One change to a bank balance, with the month it belongs to."""

    kind: MovementKind
    amount: Decimal
    month: MonthKey
    note: str = ""

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.month} {self.kind.value}: {self.amount} ({self.note})"


@dataclass(slots=True)
class CreditBank:
    """A per-service-point balance of unused export credits.

    Credits are held as dated lots rather than one number so that a rolling
    expiry can remove the oldest first.  Under an annual true-up the lots
    are settled together and the distinction never shows, which is exactly
    why a system that only keeps a running total cannot switch conventions
    later.
    """

    service_point_id: str = ""
    lots: tuple[tuple[MonthKey, Decimal], ...] = ()
    movements: tuple[BankMovement, ...] = ()

    @property
    def balance(self) -> Decimal:
        """Return the total credit held."""

        return sum((amount for _, amount in self.lots), ZERO)

    def money(self, currency: str) -> Money:
        """Return the balance as an amount of money."""

        return Money(self.balance, currency)

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when nothing is banked."""

        return self.balance <= ZERO

    def _record(self, movement: BankMovement) -> None:
        """Append a movement to the audit list."""

        self.movements = self.movements + (movement,)

    def earn(self, amount: Decimal | str, month: MonthKey, note: str = "") -> None:
        """Add a credit lot dated to ``month``."""

        value = D(amount)
        if value <= ZERO:
            return
        self.lots = self.lots + ((month, value),)
        self._record(BankMovement(MovementKind.EARNED, value, month, note))

    def apply(self, wanted: Decimal | str, month: MonthKey) -> Decimal:
        """Draw up to ``wanted`` from the bank, oldest lots first.

        Returns how much was actually drawn, which is less than ``wanted``
        when the bank runs out.  Oldest-first matters under a rolling
        expiry: drawing the newest lot first would leave the about-to-expire
        credit in place, which is worse for the customer and is what a naive
        single-balance implementation does by accident.
        """

        remaining = D(wanted)
        if remaining <= ZERO or self.is_empty:
            return ZERO
        drawn = ZERO
        lots = sorted(self.lots, key=lambda lot: (lot[0], lot[1]))
        kept: list[tuple[MonthKey, Decimal]] = []
        for lot_month, lot_amount in lots:
            if remaining <= ZERO:
                kept.append((lot_month, lot_amount))
                continue
            take = min(lot_amount, remaining)
            remaining -= take
            drawn += take
            leftover = lot_amount - take
            if leftover > ZERO:
                kept.append((lot_month, leftover))
        self.lots = tuple(kept)
        if drawn > ZERO:
            self._record(BankMovement(MovementKind.APPLIED, drawn, month, "bill offset"))
        return drawn

    def expire_before(self, cutoff: MonthKey, month: MonthKey) -> Decimal:
        """Remove every lot dated before ``cutoff``, returning the amount."""

        expired = ZERO
        kept: list[tuple[MonthKey, Decimal]] = []
        for lot_month, amount in self.lots:
            if lot_month < cutoff:
                expired += amount
            else:
                kept.append((lot_month, amount))
        self.lots = tuple(kept)
        if expired > ZERO:
            self._record(
                BankMovement(MovementKind.EXPIRED, expired, month, f"older than {cutoff}")
            )
        return expired

    def settle(self, month: MonthKey, *, cash_out: bool) -> Decimal:
        """Empty the bank at a true-up, returning the settled amount."""

        amount = self.balance
        if amount <= ZERO:
            return ZERO
        self.lots = ()
        kind = MovementKind.CASHED_OUT if cash_out else MovementKind.FORFEITED
        self._record(BankMovement(kind, amount, month, "annual true-up"))
        return amount

    def movements_of(self, kind: MovementKind) -> list[BankMovement]:
        """Return every movement of one kind."""

        return [movement for movement in self.movements if movement.kind is kind]

    def describe(self) -> str:
        """Return a multi-line description for reports."""

        lines = [f"bank {self.service_point_id}: {self.balance}"]
        lines.extend(f"  {movement.describe()}" for movement in self.movements)
        return "\n".join(lines)


def combined_balance(banks: Sequence[CreditBank]) -> Decimal:
    """Return the total balance across several banks."""

    return sum((bank.balance for bank in banks), ZERO)
