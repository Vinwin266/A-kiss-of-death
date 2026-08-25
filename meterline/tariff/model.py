"""The tariff itself: a named, ordered bundle of components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..constants import DEFAULT_CURRENCY
from ..charge.classes import ChargeClass
from ..core.units import Unit
from ..errors import TariffError
from ..model.service_point import ServiceKind
from .components.base import Component, Stage
from .seasons import SeasonSet
from .windows import WindowSet

__all__ = ["Tariff"]


@dataclass(frozen=True, slots=True)
class Tariff:
    """A rate schedule: what to charge, and for what."""

    code: str
    name: str
    components: tuple[Component, ...] = ()
    currency: str = DEFAULT_CURRENCY
    service_kinds: tuple[ServiceKind, ...] = ()
    windows: WindowSet | None = None
    seasons: SeasonSet | None = None
    energy_unit: Unit = Unit.KWH
    description: str = ""
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.components:
            raise TariffError("a tariff needs at least one component", tariff=self.code)
        seen: set[str] = set()
        for component in self.components:
            if component.code in seen:
                raise TariffError(
                    "duplicate component code",
                    tariff=self.code,
                    component=component.code,
                )
            seen.add(component.code)

    # -- lookups --------------------------------------------------------

    def ordered_components(self) -> list[Component]:
        """Return the components in evaluation order.

        Ordering is by stage, then by declaration order.  Sorting by stage
        alone would make the result depend on Python's sort stability across
        versions, which is exactly the kind of dependency that turns into a
        different bill on a different machine.
        """

        indexed = list(enumerate(self.components))
        indexed.sort(key=lambda pair: (pair[1].stage, pair[0]))
        return [component for _, component in indexed]

    def component(self, code: str) -> Component:
        """Return a component by code."""

        for component in self.components:
            if component.code == code:
                return component
        raise TariffError("unknown component", tariff=self.code, component=code)

    def components_of_class(self, charge_class: ChargeClass) -> list[Component]:
        """Return every component producing a given charge class."""

        return [
            component
            for component in self.components
            if component.charge_class is charge_class
        ]

    def has_class(self, charge_class: ChargeClass) -> bool:
        """Return ``True`` when the tariff can produce that charge class."""

        return bool(self.components_of_class(charge_class))

    # -- derived facts --------------------------------------------------

    @property
    def is_time_of_use(self) -> bool:
        """Return ``True`` when the tariff prices by time-of-use bucket."""

        return self.windows is not None and bool(self.windows.windows)

    @property
    def is_demand_billed(self) -> bool:
        """Return ``True`` when the tariff includes a demand charge."""

        return self.has_class(ChargeClass.DEMAND)

    @property
    def credits_exports(self) -> bool:
        """Return ``True`` when the tariff pays for exported energy."""

        return self.has_class(ChargeClass.CREDIT)

    @property
    def buckets(self) -> tuple[str, ...]:
        """Return the time-of-use buckets the tariff recognises."""

        return self.windows.buckets if self.windows is not None else ()

    def determinant_names(self) -> list[str]:
        """Return every determinant the tariff reads, sorted."""

        names: set[str] = set()
        for component in self.components:
            names.update(component.determinants())
        return sorted(names)

    def stages(self) -> list[int]:
        """Return the distinct stages present, in evaluation order."""

        return sorted({component.stage for component in self.components})

    def accepts(self, kind: ServiceKind) -> bool:
        """Return ``True`` when a service class may take this tariff."""

        return not self.service_kinds or kind in self.service_kinds

    # -- rendering ------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the tariff."""

        document: dict[str, Any] = {
            "code": self.code,
            "name": self.name,
            "currency": self.currency,
            "energy_unit": str(self.energy_unit),
            "description": self.description,
            "service_kinds": [kind.value for kind in self.service_kinds],
            "components": [component.as_dict() for component in self.ordered_components()],
            "metadata": dict(self.metadata),
        }
        if self.windows is not None:
            document.update(self.windows.as_dict())
        if self.seasons is not None:
            document.update(self.seasons.as_dict())
        return document

    def describe(self) -> str:
        """Return a multi-line description for reports."""

        lines = [f"{self.code} — {self.name}"]
        if self.description:
            lines.append(f"  {self.description}")
        for component in self.ordered_components():
            stage = Stage.name_of(component.stage)
            body = component.describe().split("\n")
            lines.append(f"  [{stage}] {body[0]}")
            lines.extend(f"  {line}" for line in body[1:])
        if self.windows is not None:
            lines.append("  windows:")
            lines.extend(f"    {line}" for line in self.windows.describe().split("\n"))
        if self.seasons is not None and self.seasons.seasons:
            lines.append("  seasons:")
            lines.extend(f"    {line}" for line in self.seasons.describe().split("\n"))
        return "\n".join(lines)


def build_tariff(
    code: str,
    name: str,
    components: Sequence[Component],
    **kwargs: Any,
) -> Tariff:
    """Convenience constructor used by the loader and the tests."""

    return Tariff(code, name, tuple(components), **kwargs)
