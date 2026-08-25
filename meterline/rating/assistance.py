"""Assistance programmes and the accounts enrolled in them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from ..core.diagnostics import DiagnosticBag, Severity
from ..timeline.instants import ensure_utc
from ..timeline.spans import Span

__all__ = ["Programme", "ProgrammeRegistry", "Enrolment"]


@dataclass(frozen=True, slots=True)
class Programme:
    """A named discount programme."""

    code: str
    label: str = ""
    description: str = ""
    requires_recertification_months: int = 12
    """How long an enrolment stays valid before it must be renewed."""

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the code."""

        return self.label or self.code


@dataclass(frozen=True, slots=True)
class Enrolment:
    """An account's membership of a programme over a span of time."""

    account_id: str
    programme_code: str
    effective_from: datetime
    effective_to: datetime | None = None
    certified_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "effective_from", ensure_utc(self.effective_from, what="enrolment start")
        )

    def covers(self, moment: datetime) -> bool:
        """Return ``True`` when the enrolment is in force at ``moment``."""

        normalised = ensure_utc(moment)
        if normalised < self.effective_from:
            return False
        return self.effective_to is None or normalised < self.effective_to

    def overlap(self, span: Span) -> Span | None:
        """Return the part of ``span`` this enrolment covers."""

        end = self.effective_to or span.end
        if end <= self.effective_from:
            return None
        return span.intersection(Span(self.effective_from, end))


@dataclass(slots=True)
class ProgrammeRegistry:
    """The programmes a utility runs, and who is enrolled."""

    programmes: dict[str, Programme] = field(default_factory=dict)
    enrolments: tuple[Enrolment, ...] = ()

    def add(self, programme: Programme) -> None:
        """Add or replace a programme."""

        self.programmes[programme.code] = programme

    def enrol(self, enrolment: Enrolment) -> None:
        """Record an enrolment."""

        self.enrolments = self.enrolments + (enrolment,)

    def extend(self, enrolments: Iterable[Enrolment]) -> None:
        """Record several enrolments."""

        for enrolment in enrolments:
            self.enrol(enrolment)

    def programme_for(self, account_id: str, moment: datetime) -> str:
        """Return the programme an account is in at an instant, if any."""

        for enrolment in sorted(
            self.enrolments, key=lambda item: item.effective_from
        ):
            if enrolment.account_id == account_id and enrolment.covers(moment):
                return enrolment.programme_code
        return ""

    def check_certification(
        self, account_id: str, moment: datetime
    ) -> DiagnosticBag:
        """Report an enrolment whose certification has lapsed."""

        bag = DiagnosticBag()
        for enrolment in self.enrolments:
            if enrolment.account_id != account_id or not enrolment.covers(moment):
                continue
            programme = self.programmes.get(enrolment.programme_code)
            if programme is None or enrolment.certified_at is None:
                continue
            months = programme.requires_recertification_months
            elapsed_days = (ensure_utc(moment) - enrolment.certified_at).days
            if elapsed_days > months * 31:
                bag.emit(
                    "rating.assistance.lapsed",
                    "the discount is still applying but certification has lapsed",
                    Severity.WARNING,
                    account_id,
                    programme=enrolment.programme_code,
                    days=elapsed_days,
                )
        return bag

    def codes(self) -> list[str]:
        """Return the programme codes, sorted."""

        return sorted(self.programmes)
