"""Tax rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..charge.basis import Basis
from ..charge.classes import ChargeClass
from ..core.decimals import D
from ..core.units import Unit
from ..errors import ConfigurationError

__all__ = ["TaxKind", "TaxRule"]


class TaxKind(str, Enum):
    """How a tax's amount is arrived at."""

    PERCENT = "percent"
    """A percentage of a named basis."""

    PER_UNIT = "per_unit"
    """A rate per metered unit, such as a per-kWh utility fee."""

    FLAT = "flat"
    """A fixed amount per bill."""


@dataclass(frozen=True, slots=True)
class TaxRule:
    """One tax or regulatory fee."""

    code: str
    label: str
    kind: TaxKind
    rate: Decimal
    jurisdiction: str = ""
    basis: Basis = Basis.SUBTOTAL
    determinant: str = "energy.total"
    unit: Unit = Unit.KWH
    order: int = 0
    """Application order; only meaningful under sequential compounding."""

    exempt_classes: tuple[ChargeClass, ...] = ()
    """Charge classes excluded from this tax's base."""

    exemption_code: str = ""
    """Exemption an account must hold to avoid the tax."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", D(self.rate))
        if self.kind is TaxKind.PERCENT and self.basis is Basis.TOTAL:
            raise ConfigurationError(
                "a tax cannot be a percentage of a total that includes it",
                tax=self.code,
            )

    @property
    def is_percentage(self) -> bool:
        """Return ``True`` for a percentage tax."""

        return self.kind is TaxKind.PERCENT

    def describe(self) -> str:
        """Return a one-line description for reports."""

        if self.kind is TaxKind.PERCENT:
            return f"{self.code}: {self.label}, {self.rate}% of {self.basis.label}"
        if self.kind is TaxKind.PER_UNIT:
            return f"{self.code}: {self.label}, {self.rate} per {self.unit}"
        return f"{self.code}: {self.label}, {self.rate} per bill"
