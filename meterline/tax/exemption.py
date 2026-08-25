"""Exemptions: who does not pay a tax, and how much of it."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..core.decimals import D, HUNDRED

__all__ = ["Exemption", "ExemptionSet"]


@dataclass(frozen=True, slots=True)
class Exemption:
    """A full or partial relief from one tax.

    Partial exemptions are the norm rather than the exception: a
    manufacturer might be relieved of the state portion of a utility tax on
    the share of energy used in production, which is a percentage, and a
    non-profit might be exempt outright, which is a hundred percent of the
    same field.
    """

    code: str
    tax_code: str
    percent: Decimal = HUNDRED
    label: str = ""
    cap: Decimal = D(0)
    """Maximum amount relieved per bill; zero means no cap."""

    @property
    def is_full(self) -> bool:
        """Return ``True`` when the exemption relieves the whole tax."""

        return self.percent >= HUNDRED and self.cap == D(0)

    def relief(self, amount: Decimal) -> Decimal:
        """Return how much of ``amount`` this exemption relieves."""

        relieved = amount * self.percent / HUNDRED
        if self.cap > D(0):
            relieved = min(relieved, self.cap)
        return relieved

    def describe(self) -> str:
        """Return a one-line description for reports."""

        cap = f", capped at {self.cap}" if self.cap > D(0) else ""
        return f"{self.code}: {self.percent}% of {self.tax_code}{cap}"


@dataclass(slots=True)
class ExemptionSet:
    """The exemptions available, keyed by code."""

    items: dict[str, Exemption] = field(default_factory=dict)

    def add(self, exemption: Exemption) -> None:
        """Add or replace an exemption."""

        self.items[exemption.code] = exemption

    def get(self, code: str) -> Exemption | None:
        """Return an exemption by code."""

        return self.items.get(code)

    def for_tax(self, tax_code: str, held: tuple[str, ...]) -> Exemption | None:
        """Return the exemption among ``held`` that applies to a tax."""

        for code in sorted(held):
            exemption = self.items.get(code)
            if exemption is not None and exemption.tax_code == tax_code:
                return exemption
        return None

    def codes(self) -> list[str]:
        """Return the exemption codes, sorted."""

        return sorted(self.items)
