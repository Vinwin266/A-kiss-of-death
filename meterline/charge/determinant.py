"""Billing determinants: the measured inputs a tariff prices.

The engine computes determinants once, from meter data, and tariffs consume
them by name.  The separation matters because a determinant carries its own
quality: a peak demand derived from a day of estimated intervals is still a
number, but a bill that presents it without saying so is misleading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Mapping

from ..core.quantity import Quantity
from ..core.units import Unit
from ..errors import RatingError
from ..model.quality import QualityCode, worst_of

__all__ = ["Determinant", "DeterminantSet"]


@dataclass(frozen=True, slots=True)
class Determinant:
    """One named, measured input to a tariff."""

    name: str
    quantity: Quantity
    quality: QualityCode = QualityCode.VALID
    source: str = ""
    detail: tuple[tuple[str, str], ...] = ()

    @classmethod
    def make(
        cls,
        name: str,
        quantity: Quantity,
        quality: QualityCode = QualityCode.VALID,
        source: str = "",
        **detail: object,
    ) -> "Determinant":
        """Build a determinant with keyword detail."""

        rendered = tuple(sorted((key, str(value)) for key, value in detail.items()))
        return cls(name, quantity, quality, source, rendered)

    @property
    def unit(self) -> Unit:
        """Return the unit of the underlying quantity."""

        return self.quantity.unit

    @property
    def is_estimated(self) -> bool:
        """Return ``True`` when any part of the value was estimated."""

        return self.quality.needs_true_up

    def scaled(self, factor) -> "Determinant":  # noqa: ANN001
        """Return a copy with the quantity multiplied by ``factor``."""

        return Determinant(
            self.name, self.quantity * factor, self.quality, self.source, self.detail
        )

    def describe(self) -> str:
        """Return a one-line description for reports."""

        suffix = "" if self.quality is QualityCode.VALID else f" [{self.quality.value}]"
        return f"{self.name} = {self.quantity}{suffix}"


@dataclass(slots=True)
class DeterminantSet:
    """A keyed collection of determinants with convenient lookups."""

    items: dict[str, Determinant] = field(default_factory=dict)

    @classmethod
    def of(cls, determinants) -> "DeterminantSet":  # noqa: ANN001
        """Build a set from an iterable of determinants."""

        result = cls()
        for determinant in determinants:
            result.add(determinant)
        return result

    def add(self, determinant: Determinant) -> None:
        """Add or replace a determinant."""

        self.items[determinant.name] = determinant

    def put(
        self,
        name: str,
        quantity: Quantity,
        quality: QualityCode = QualityCode.VALID,
        source: str = "",
        **detail: object,
    ) -> None:
        """Build and add a determinant in one call."""

        self.add(Determinant.make(name, quantity, quality, source, **detail))

    def get(self, name: str) -> Determinant | None:
        """Return a determinant, or ``None`` when absent."""

        return self.items.get(name)

    def require(self, name: str, *, why: str = "") -> Determinant:
        """Return a determinant or raise a readable :class:`RatingError`."""

        found = self.items.get(name)
        if found is None:
            raise RatingError(
                "a tariff asked for a determinant that was not computed",
                determinant=name,
                available=", ".join(sorted(self.items)),
                why=why or "unspecified",
            )
        return found

    def quantity(self, name: str, unit: Unit) -> Quantity:
        """Return a determinant's quantity, converted to ``unit``."""

        return self.require(name).quantity.to(unit)

    def quantity_or_zero(self, name: str, unit: Unit) -> Quantity:
        """Return a determinant's quantity, or zero when it is absent.

        Absence and zero are not the same thing, and callers that use this
        must be able to justify the collapse — a missing export channel is
        genuinely zero export, a missing energy channel is not zero usage.
        """

        found = self.items.get(name)
        return found.quantity.to(unit) if found is not None else Quantity.zero(unit)

    def names(self) -> list[str]:
        """Return the determinant names, sorted."""

        return sorted(self.items)

    def matching(self, prefix: str) -> list[Determinant]:
        """Return every determinant whose name starts with ``prefix``."""

        return [self.items[name] for name in sorted(self.items) if name.startswith(prefix)]

    def overall_quality(self) -> QualityCode:
        """Return the worst quality across every determinant."""

        return worst_of(item.quality for item in self.items.values())

    def as_mapping(self) -> Mapping[str, Determinant]:
        """Return a read-only view."""

        return dict(self.items)

    def __iter__(self) -> Iterator[Determinant]:
        for name in sorted(self.items):
            yield self.items[name]

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, name: object) -> bool:
        return name in self.items
