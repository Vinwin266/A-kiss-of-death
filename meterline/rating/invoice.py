"""The bill: line items, subtotals and the record behind them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

from ..charge.basis import Basis, basis_amount, subtotal_by_class
from ..charge.classes import ChargeClass
from ..charge.lineitem import LineItem
from ..core.diagnostics import DiagnosticBag
from ..core.ids import stable_id
from ..core.money import Money
from ..model.quality import QualityCode
from ..timeline.spans import Span

__all__ = ["Invoice"]


@dataclass(slots=True)
class Invoice:
    """One bill for one service point over one period."""

    bill_id: str
    account_id: str
    service_point_id: str
    span: Span
    currency: str
    lines: tuple[LineItem, ...] = ()
    cycle_id: str = ""
    tariff_codes: tuple[str, ...] = ()
    profile_name: str = ""
    quality: QualityCode = QualityCode.VALID
    determinants: tuple[tuple[str, str], ...] = ()
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)
    credit_carried_in: Money | None = None
    credit_carried_out: Money | None = None
    engine_version: str = ""

    @classmethod
    def build(
        cls,
        account_id: str,
        service_point_id: str,
        span: Span,
        currency: str,
        **kwargs: Any,
    ) -> "Invoice":
        """Build an invoice with a deterministic identifier."""

        bill_id = stable_id(
            "bill",
            account_id,
            service_point_id,
            span.start.isoformat(),
            span.end.isoformat(),
        )
        return cls(bill_id, account_id, service_point_id, span, currency, **kwargs)

    # -- totals ---------------------------------------------------------

    def subtotal(self, basis: Basis = Basis.SUBTOTAL) -> Money:
        """Return a named subtotal of the bill."""

        return basis_amount(self.lines, basis, self.currency)

    @property
    def taxes(self) -> Money:
        """Return the total tax on the bill."""

        return basis_amount(
            [line for line in self.lines if line.charge_class is ChargeClass.TAX],
            Basis.TOTAL,
            self.currency,
        )

    @property
    def total(self) -> Money:
        """Return the amount due."""

        return basis_amount(self.lines, Basis.TOTAL, self.currency)

    @property
    def is_credit(self) -> bool:
        """Return ``True`` when the bill owes the customer money."""

        return self.total.is_credit

    def by_class(self) -> dict[ChargeClass, Money]:
        """Return the subtotal of each charge class present."""

        return subtotal_by_class(self.lines, self.currency)

    # -- inspection -----------------------------------------------------

    def line(self, code: str) -> LineItem | None:
        """Return the first line with a given code."""

        for line in self.lines:
            if line.code == code:
                return line
        return None

    def lines_of(self, charge_class: ChargeClass) -> list[LineItem]:
        """Return every line of a charge class, in render order."""

        return [line for line in self.ordered_lines() if line.charge_class is charge_class]

    def ordered_lines(self) -> list[LineItem]:
        """Return the lines in a stable rendering order."""

        return sorted(self.lines, key=lambda line: line.sort_key)

    def codes(self) -> list[str]:
        """Return the line codes present, in render order."""

        return [line.code for line in self.ordered_lines()]

    @property
    def is_estimated(self) -> bool:
        """Return ``True`` when the bill rests on estimated data."""

        return self.quality.needs_true_up

    @property
    def has_errors(self) -> bool:
        """Return ``True`` when an error-level diagnostic was recorded."""

        return self.diagnostics.has_errors

    def determinant(self, name: str) -> str:
        """Return a determinant's rendered value, or an empty string."""

        for key, value in self.determinants:
            if key == name:
                return value
        return ""

    def period_dates(self, zone) -> tuple[date, date]:  # noqa: ANN001
        """Return the first and last local dates the bill covers."""

        from datetime import timedelta

        return (
            zone.local_date(self.span.start),
            zone.local_date(self.span.end - timedelta(microseconds=1)),
        )

    # -- serialisation --------------------------------------------------

    def as_dict(self, places: int = 2) -> dict[str, Any]:
        """Return a JSON friendly view of the whole bill."""

        return {
            "bill_id": self.bill_id,
            "account_id": self.account_id,
            "service_point_id": self.service_point_id,
            "cycle_id": self.cycle_id,
            "span": {
                "start": self.span.start.isoformat(),
                "end": self.span.end.isoformat(),
            },
            "currency": self.currency,
            "profile": self.profile_name,
            "tariffs": list(self.tariff_codes),
            "quality": self.quality.value,
            "engine": self.engine_version,
            "determinants": dict(self.determinants),
            "lines": [line.as_dict(places) for line in self.ordered_lines()],
            "totals": {
                "energy": self.subtotal(Basis.ENERGY).format(places),
                "fixed": self.subtotal(Basis.FIXED).format(places),
                "demand": self.subtotal(Basis.DEMAND).format(places),
                "before_tax": self.subtotal(Basis.SUBTOTAL).format(places),
                "tax": self.taxes.format(places),
                "total": self.total.format(places),
            },
            "credit_carried_in": (
                self.credit_carried_in.format(places) if self.credit_carried_in else None
            ),
            "credit_carried_out": (
                self.credit_carried_out.format(places) if self.credit_carried_out else None
            ),
            "diagnostics": self.diagnostics.as_list(),
        }

    def with_lines(self, lines: Sequence[LineItem]) -> "Invoice":
        """Return a copy carrying a different set of lines."""

        return Invoice(
            self.bill_id,
            self.account_id,
            self.service_point_id,
            self.span,
            self.currency,
            tuple(lines),
            self.cycle_id,
            self.tariff_codes,
            self.profile_name,
            self.quality,
            self.determinants,
            self.diagnostics,
            self.credit_carried_in,
            self.credit_carried_out,
            self.engine_version,
        )
