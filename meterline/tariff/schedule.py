"""Dated versions of a tariff, and how a cycle spanning two is rated."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..errors import TariffError
from ..timeline.instants import ensure_utc, format_instant
from ..timeline.spans import Span
from .model import Tariff

__all__ = ["TariffVersion", "TariffSchedule"]


@dataclass(frozen=True, slots=True)
class TariffVersion:
    """One dated version of a tariff."""

    version: str
    effective_from: datetime
    tariff: Tariff
    effective_to: datetime | None = None
    order_reference: str = ""
    """The regulatory order that approved the version, for the audit trail."""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "effective_from", ensure_utc(self.effective_from, what="version start")
        )
        if self.effective_to is not None:
            end = ensure_utc(self.effective_to, what="version end")
            if end <= self.effective_from:
                raise TariffError(
                    "a tariff version ends before it starts",
                    tariff=self.tariff.code,
                    version=self.version,
                )
            object.__setattr__(self, "effective_to", end)

    def covers(self, moment: datetime) -> bool:
        """Return ``True`` when the version is in force at ``moment``."""

        normalised = ensure_utc(moment)
        if normalised < self.effective_from:
            return False
        return self.effective_to is None or normalised < self.effective_to

    def overlap(self, span: Span) -> Span | None:
        """Return the part of ``span`` this version covers."""

        end = self.effective_to or span.end
        if end <= self.effective_from:
            return None
        return span.intersection(Span(self.effective_from, end))

    def describe(self) -> str:
        """Return a one-line description for reports."""

        end = format_instant(self.effective_to) if self.effective_to else "open"
        return (
            f"{self.tariff.code} v{self.version}: "
            f"{format_instant(self.effective_from)} to {end}"
        )


@dataclass(frozen=True, slots=True)
class TariffSchedule:
    """Every version of one tariff, ordered by effective date."""

    code: str
    versions: tuple[TariffVersion, ...] = ()

    @classmethod
    def of(cls, code: str, versions) -> "TariffSchedule":  # noqa: ANN001
        """Build a schedule with versions sorted and implicitly closed.

        A version that does not declare an end date is closed at the start
        of the next one.  Leaving it open would make two versions cover the
        same instant, and a cycle spanning a rate change would then be rated
        twice — once under each — which is exactly the bug this closure
        exists to prevent.
        """

        ordered = sorted(versions, key=lambda version: version.effective_from)
        closed: list[TariffVersion] = []
        for index, version in enumerate(ordered):
            successor = ordered[index + 1] if index + 1 < len(ordered) else None
            if (
                successor is not None
                and version.effective_to is None
                and successor.effective_from > version.effective_from
            ):
                version = TariffVersion(
                    version.version,
                    version.effective_from,
                    version.tariff,
                    successor.effective_from,
                    version.order_reference,
                )
            closed.append(version)
        return cls(code, tuple(closed))

    def at(self, moment: datetime) -> Tariff:
        """Return the tariff in force at ``moment``."""

        found = None
        for version in self.versions:
            if version.covers(moment):
                found = version
        if found is None:
            raise TariffError(
                "no version of this tariff was in force",
                tariff=self.code,
                at=format_instant(ensure_utc(moment)),
            )
        return found.tariff

    def version_at(self, moment: datetime) -> TariffVersion:
        """Return the version record in force at ``moment``."""

        found = None
        for version in self.versions:
            if version.covers(moment):
                found = version
        if found is None:
            raise TariffError(
                "no version of this tariff was in force",
                tariff=self.code,
                at=format_instant(ensure_utc(moment)),
            )
        return found

    def segments(self, span: Span) -> list[tuple[Span, TariffVersion]]:
        """Return the sub-spans of ``span`` and the version covering each.

        A cycle that straddles a rate change produces two segments.  What
        the engine does with them — rate each separately, or apply one
        version to the whole cycle — is the enrolment-resolution convention,
        applied one level up in the rating engine.
        """

        pieces: list[tuple[Span, TariffVersion]] = []
        for version in self.versions:
            overlap = version.overlap(span)
            if overlap is not None and not overlap.is_empty:
                pieces.append((overlap, version))
        pieces.sort(key=lambda item: item[0].start)
        if not pieces:
            raise TariffError(
                "no version of this tariff covers the period",
                tariff=self.code,
                span=span.describe(),
            )
        return pieces

    @property
    def is_versioned(self) -> bool:
        """Return ``True`` when more than one version exists."""

        return len(self.versions) > 1

    def describe(self) -> str:
        """Return one line per version."""

        return "\n".join(version.describe() for version in self.versions)
