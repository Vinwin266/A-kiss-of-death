"""The catalog: every tariff the utility offers, by code."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Iterator

from ..errors import TariffError
from ..model.service_point import ServiceKind
from ..timeline.spans import Span
from .model import Tariff
from .schedule import TariffSchedule, TariffVersion

__all__ = ["TariffCatalog"]


@dataclass(slots=True)
class TariffCatalog:
    """A lookup from tariff code to its dated schedule."""

    schedules: dict[str, TariffSchedule] = field(default_factory=dict)

    @classmethod
    def of(cls, schedules: Iterable[TariffSchedule]) -> "TariffCatalog":
        """Build a catalog from an iterable of schedules."""

        catalog = cls()
        for schedule in schedules:
            catalog.add(schedule)
        return catalog

    @classmethod
    def single_version(cls, tariffs: Iterable[Tariff], effective_from: datetime) -> "TariffCatalog":
        """Build a catalog where every tariff has one open-ended version."""

        catalog = cls()
        for tariff in tariffs:
            catalog.add(
                TariffSchedule.of(
                    tariff.code, [TariffVersion("1", effective_from, tariff)]
                )
            )
        return catalog

    def add(self, schedule: TariffSchedule) -> None:
        """Add or replace a schedule."""

        self.schedules[schedule.code] = schedule

    def add_version(self, version: TariffVersion) -> None:
        """Append a version to the schedule of its tariff."""

        code = version.tariff.code
        existing = self.schedules.get(code)
        versions = list(existing.versions) if existing else []
        versions.append(version)
        self.schedules[code] = TariffSchedule.of(code, versions)

    def schedule(self, code: str) -> TariffSchedule:
        """Return the schedule for a tariff code."""

        try:
            return self.schedules[code]
        except KeyError:
            raise TariffError(
                "unknown tariff",
                code=code,
                known=", ".join(sorted(self.schedules)),
            ) from None

    def resolve(self, code: str, at: datetime) -> Tariff:
        """Return the tariff version in force at an instant."""

        return self.schedule(code).at(at)

    def segments(self, code: str, span: Span) -> list[tuple[Span, TariffVersion]]:
        """Return the versions covering each part of ``span``."""

        return self.schedule(code).segments(span)

    def codes(self) -> list[str]:
        """Return the tariff codes, sorted."""

        return sorted(self.schedules)

    def eligible_for(self, kind: ServiceKind, at: datetime) -> list[str]:
        """Return the tariff codes a service class may take at an instant."""

        eligible: list[str] = []
        for code in self.codes():
            try:
                tariff = self.resolve(code, at)
            except TariffError:
                continue
            if tariff.accepts(kind):
                eligible.append(code)
        return eligible

    def __iter__(self) -> Iterator[TariffSchedule]:
        for code in self.codes():
            yield self.schedules[code]

    def __len__(self) -> int:
        return len(self.schedules)

    def __contains__(self, code: object) -> bool:
        return code in self.schedules

    def describe(self) -> str:
        """Return one block per tariff."""

        return "\n".join(self.schedules[code].describe() for code in self.codes())
