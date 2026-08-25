"""Line items: one row on a bill."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..core.decimals import D
from ..core.ids import stable_id
from ..core.money import Money
from ..core.quantity import Quantity
from ..core.rounding import RoundingMode, quantize
from ..model.quality import QualityCode
from .classes import ChargeClass, ChargeSide
from .trace import Trace, TraceStep

__all__ = ["LineItem", "LineItemBuilder"]


@dataclass(frozen=True, slots=True)
class LineItem:
    """One priced row, with the working that produced it."""

    line_id: str
    code: str
    label: str
    charge_class: ChargeClass
    amount: Money
    quantity: Quantity | None = None
    rate: Decimal | None = None
    side: ChargeSide = ChargeSide.OTHER
    quality: QualityCode = QualityCode.VALID
    component: str = ""
    """Code of the tariff component that produced the line."""

    taxable: bool = True
    trace: tuple[TraceStep, ...] = ()
    detail: tuple[tuple[str, str], ...] = ()

    @property
    def is_credit(self) -> bool:
        """Return ``True`` when the line reduces the bill."""

        return self.amount.is_credit

    @property
    def is_zero(self) -> bool:
        """Return ``True`` when the line has no monetary effect."""

        return self.amount.is_zero

    @property
    def sort_key(self) -> tuple[int, str, str]:
        """Return the deterministic ordering key for rendering."""

        return (self.charge_class.sort_order, self.component, self.code)

    def rounded(
        self, places: int = 2, mode: RoundingMode = RoundingMode.HALF_UP
    ) -> "LineItem":
        """Return a copy with the amount rounded for presentation."""

        rounded_amount = self.amount.quantized(places, mode)
        if rounded_amount == self.amount:
            return self
        trace = list(self.trace)
        trace.append(
            TraceStep(
                "round",
                f"{self.amount.format(6)} at {places}dp {mode.value}",
                rounded_amount.format(places),
            )
        )
        return LineItem(
            self.line_id,
            self.code,
            self.label,
            self.charge_class,
            rounded_amount,
            self.quantity,
            self.rate,
            self.side,
            self.quality,
            self.component,
            self.taxable,
            tuple(trace),
            self.detail,
        )

    def with_amount(self, amount: Money) -> "LineItem":
        """Return a copy carrying a different amount."""

        return LineItem(
            self.line_id,
            self.code,
            self.label,
            self.charge_class,
            amount,
            self.quantity,
            self.rate,
            self.side,
            self.quality,
            self.component,
            self.taxable,
            self.trace,
            self.detail,
        )

    def negated(self, *, code_suffix: str = ".reversal") -> "LineItem":
        """Return the reversing line used by a cancel-and-rebill."""

        return LineItem(
            stable_id("li", self.line_id, code_suffix),
            f"{self.code}{code_suffix}",
            f"Reversal of {self.label}",
            ChargeClass.ADJUSTMENT,
            -self.amount,
            self.quantity,
            self.rate,
            self.side,
            self.quality,
            self.component,
            self.taxable,
            self.trace,
            self.detail,
        )

    def as_dict(self, places: int = 2) -> dict[str, Any]:
        """Return a JSON friendly view."""

        return {
            "line_id": self.line_id,
            "code": self.code,
            "label": self.label,
            "class": self.charge_class.value,
            "side": self.side.value,
            "component": self.component,
            "quantity": self.quantity.format() if self.quantity else None,
            "rate": str(self.rate) if self.rate is not None else None,
            "amount": self.amount.format(places),
            "currency": self.amount.currency,
            "quality": self.quality.value,
            "taxable": self.taxable,
            "detail": dict(self.detail),
            "trace": [step.as_dict() for step in self.trace],
        }


class LineItemBuilder:
    """Accumulates the working for one line item, then seals it.

    Components build lines through this rather than constructing
    :class:`LineItem` directly, so that every line arrives with a trace and
    a deterministic identifier without each component remembering to do it.
    """

    def __init__(
        self,
        code: str,
        label: str,
        charge_class: ChargeClass,
        component: str = "",
        side: ChargeSide = ChargeSide.OTHER,
    ) -> None:
        self.code = code
        self.label = label
        self.charge_class = charge_class
        self.component = component
        self.side = side
        self.trace = Trace()
        self.quantity: Quantity | None = None
        self.rate: Decimal | None = None
        self.quality: QualityCode = QualityCode.VALID
        self.taxable = charge_class.is_taxable_by_default
        self._detail: dict[str, str] = {}

    def measure(self, quantity: Quantity, label: str = "quantity") -> "LineItemBuilder":
        """Record the metered quantity being priced."""

        self.quantity = quantity
        self.trace.add(label, quantity.format())
        return self

    def priced_at(self, rate: Decimal | str, label: str = "rate") -> "LineItemBuilder":
        """Record the unit rate being applied."""

        self.rate = D(rate)
        self.trace.add(label, str(quantize(self.rate, 6, RoundingMode.HALF_UP)))
        return self

    def note(self, label: str, detail: Any = "", value: Any = "") -> "LineItemBuilder":
        """Record an arbitrary step in the working."""

        self.trace.add(label, str(detail), str(value))
        return self

    def detail(self, **values: Any) -> "LineItemBuilder":
        """Attach structured detail to the finished line."""

        for key, value in values.items():
            self._detail[key] = str(value)
        return self

    def flag(self, quality: QualityCode) -> "LineItemBuilder":
        """Record the quality of the data behind the line."""

        self.quality = quality
        return self

    def exempt(self) -> "LineItemBuilder":
        """Mark the line as outside the tax base."""

        self.taxable = False
        return self

    def seal(self, amount: Money) -> LineItem:
        """Produce the finished, immutable line item."""

        self.trace.add("amount", "", amount.format(6))
        line_id = stable_id(
            "li",
            self.component,
            self.code,
            str(amount.amount),
            self.quantity.format() if self.quantity else "",
        )
        return LineItem(
            line_id,
            self.code,
            self.label,
            self.charge_class,
            amount,
            self.quantity,
            self.rate,
            self.side,
            self.quality,
            self.component,
            self.taxable,
            self.trace.freeze(),
            tuple(sorted(self._detail.items())),
        )
