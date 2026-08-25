"""Service points: where a tariff meets a meter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..errors import ConfigurationError
from ..timeline.spans import Span

__all__ = ["ServiceKind", "ServicePoint"]


class ServiceKind(str, Enum):
    """The class of service, which drives which tariffs are eligible."""

    RESIDENTIAL = "residential"
    SMALL_COMMERCIAL = "small_commercial"
    LARGE_COMMERCIAL = "large_commercial"
    INDUSTRIAL = "industrial"
    STREET_LIGHTING = "street_lighting"
    AGRICULTURAL = "agricultural"

    @property
    def is_demand_metered_by_default(self) -> bool:
        """Return ``True`` for classes normally billed on demand as well."""

        return self in (
            ServiceKind.LARGE_COMMERCIAL,
            ServiceKind.INDUSTRIAL,
        )


@dataclass(frozen=True, slots=True)
class ServicePoint:
    """The billing anchor: one commodity, one premise, one tariff at a time."""

    service_point_id: str
    account_id: str
    premise_id: str
    zone_name: str
    kind: ServiceKind = ServiceKind.RESIDENTIAL
    route: str = ""
    meter_ids: tuple[str, ...] = ()
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    voltage_level: str = "secondary"
    has_generation: bool = False
    """Whether the point can export; gates the net-metering components."""

    generation_capacity_kw: str = "0"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.zone_name:
            raise ConfigurationError(
                "a service point needs a timezone",
                service_point=self.service_point_id,
            )

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the identifier."""

        return self.label or self.service_point_id

    @property
    def service_span(self) -> Span | None:
        """Return the connected span when both ends are known."""

        if self.connected_at is None or self.disconnected_at is None:
            return None
        return Span(self.connected_at, self.disconnected_at)

    def was_served_during(self, span: Span) -> bool:
        """Return ``True`` when service was active during any of ``span``."""

        if self.connected_at is not None and self.connected_at >= span.end:
            return False
        if self.disconnected_at is not None and self.disconnected_at <= span.start:
            return False
        return True

    def served_portion(self, span: Span) -> Span | None:
        """Return the part of ``span`` for which service was connected.

        A cycle that begins before a move-in must not be billed in full; the
        standing charge applies to this portion, not to the whole cycle.
        """

        start = span.start
        end = span.end
        if self.connected_at is not None:
            start = max(start, self.connected_at)
        if self.disconnected_at is not None:
            end = min(end, self.disconnected_at)
        if end <= start:
            return None
        return Span(start, end)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        parts = [f"{self.display_name} ({self.kind.value})", f"zone {self.zone_name}"]
        if self.route:
            parts.append(f"route {self.route}")
        if self.has_generation:
            parts.append(f"generation {self.generation_capacity_kw} kW")
        return ", ".join(parts)
