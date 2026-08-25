"""The component interface and the stages components run in."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem

__all__ = ["Stage", "Component"]


class Stage:
    """Evaluation stages, low to high.

    The order is a convention in its own right: a rider assessed on the
    energy subtotal sees a different number depending on whether the
    minimum-charge make-up has already been added.  Making the stages
    explicit and numeric means a tariff can insert a component between two
    of them without renumbering anything.
    """

    FIXED = 10
    ENERGY = 20
    DEMAND = 30
    REACTIVE = 35
    RIDER = 50
    CREDIT = 60
    MINIMUM = 70
    DISCOUNT = 80

    @staticmethod
    def name_of(stage: int) -> str:
        """Return a readable name for a stage number."""

        names = {
            Stage.FIXED: "fixed",
            Stage.ENERGY: "energy",
            Stage.DEMAND: "demand",
            Stage.REACTIVE: "reactive",
            Stage.RIDER: "rider",
            Stage.CREDIT: "credit",
            Stage.MINIMUM: "minimum",
            Stage.DISCOUNT: "discount",
        }
        return names.get(stage, f"stage-{stage}")


class Component(ABC):
    """One priced rule inside a tariff.

    Components are immutable and are shared between bills, so they must not
    keep state between calls to :meth:`compute`.  Everything they need is on
    the context; everything they produce is in the returned lines.
    """

    kind: str = "component"
    """The name this component is written as in a tariff document."""

    def __init__(
        self,
        code: str,
        label: str,
        charge_class: ChargeClass,
        stage: int,
        side: ChargeSide = ChargeSide.OTHER,
    ) -> None:
        self.code = code
        self.label = label
        self.charge_class = charge_class
        self.stage = stage
        self.side = side

    @abstractmethod
    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return the line items this component contributes."""

    def determinants(self) -> tuple[str, ...]:
        """Return the determinant names this component reads."""

        return ()

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.code} ({self.kind}): {self.label}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component's configuration."""

        return {
            "kind": self.kind,
            "code": self.code,
            "label": self.label,
            "class": self.charge_class.value,
            "side": self.side.value,
            "stage": self.stage,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.code}>"
