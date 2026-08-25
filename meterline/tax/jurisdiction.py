"""Jurisdictions: the tax rules that apply at a premise."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..errors import UnknownReferenceError
from .model import TaxRule

__all__ = ["Jurisdiction", "JurisdictionSet"]


@dataclass(frozen=True, slots=True)
class Jurisdiction:
    """A named place, and the taxes it levies.

    Jurisdictions nest: a city rule and a state rule both apply to the same
    bill.  Rather than model the hierarchy, a jurisdiction lists a parent
    code and the set resolves the chain, which keeps a premise pointing at
    one code and lets the state rate change in one place.
    """

    code: str
    label: str = ""
    parent: str = ""
    rules: tuple[TaxRule, ...] = ()

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the code."""

        return self.label or self.code

    def describe(self) -> str:
        """Return a multi-line description for reports."""

        lines = [f"{self.display_name} ({self.code})"]
        if self.parent:
            lines.append(f"  within {self.parent}")
        lines.extend(f"  {rule.describe()}" for rule in self.rules)
        return "\n".join(lines)


@dataclass(slots=True)
class JurisdictionSet:
    """Every jurisdiction known to the dataset."""

    items: dict[str, Jurisdiction] = field(default_factory=dict)

    @classmethod
    def of(cls, jurisdictions: Iterable[Jurisdiction]) -> "JurisdictionSet":
        """Build a set from an iterable."""

        result = cls()
        for jurisdiction in jurisdictions:
            result.add(jurisdiction)
        return result

    def add(self, jurisdiction: Jurisdiction) -> None:
        """Add or replace a jurisdiction."""

        self.items[jurisdiction.code] = jurisdiction

    def get(self, code: str) -> Jurisdiction:
        """Return a jurisdiction by code."""

        try:
            return self.items[code]
        except KeyError:
            raise UnknownReferenceError(
                "no such jurisdiction", kind="jurisdiction", identifier=code
            ) from None

    def chain(self, code: str) -> list[Jurisdiction]:
        """Return the jurisdiction and its ancestors, innermost first."""

        seen: list[Jurisdiction] = []
        cursor = code
        guard = 0
        while cursor and guard < 8:
            jurisdiction = self.get(cursor)
            seen.append(jurisdiction)
            cursor = jurisdiction.parent
            guard += 1
        return seen

    def rules_for(self, code: str) -> list[TaxRule]:
        """Return every rule that applies at a jurisdiction, in order.

        Rules are ordered by their declared ``order`` and then by code, so
        that sequential compounding is reproducible regardless of the order
        the jurisdictions were loaded in.
        """

        if not code:
            return []
        rules: list[TaxRule] = []
        for jurisdiction in self.chain(code):
            rules.extend(jurisdiction.rules)
        rules.sort(key=lambda rule: (rule.order, rule.code))
        return rules

    def codes(self) -> list[str]:
        """Return the jurisdiction codes, sorted."""

        return sorted(self.items)
