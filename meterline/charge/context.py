"""The context a tariff component is rated against.

A component is handed one of these and nothing else.  That constraint is
what keeps components pure: they cannot reach for meter data, cannot decide
what day it is, and cannot consult a different policy than the one the bill
is being produced under.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..constants import DEFAULT_CURRENCY
from ..core.decimals import D, safe_divide
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.money import Money
from ..core.quantity import Quantity
from ..core.units import Unit
from ..policy.profile import UtilityProfile
from ..timeline.calendars import MonthKey, days_in_month
from ..timeline.daycount import billing_days
from ..timeline.daytypes import DayType, classify_day
from ..timeline.holidays import HolidayCalendar
from ..timeline.spans import Span
from ..timeline.zones import Zone
from .determinant import DeterminantSet

__all__ = ["RatingContext"]


@dataclass(slots=True)
class RatingContext:
    """Everything a component needs, and nothing it does not."""

    span: Span
    """The period being rated; may be a sub-period of the billing cycle."""

    cycle_span: Span
    """The whole billing cycle, for proration denominators."""

    zone: Zone
    profile: UtilityProfile
    determinants: DeterminantSet
    service_point_id: str = ""
    tariff_code: str = ""
    currency: str = DEFAULT_CURRENCY
    holidays: HolidayCalendar | None = None
    served_span: Span | None = None
    """The part of the span for which service was actually connected."""

    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)
    notes: dict[str, str] = field(default_factory=dict)

    # -- calendar facts -------------------------------------------------

    @property
    def start_date(self) -> date:
        """Return the local date the rated span begins on."""

        return self.zone.local_date(self.span.start)

    @property
    def end_date(self) -> date:
        """Return the last local date the rated span touches."""

        return self.zone.local_date(self.span.end - timedelta(microseconds=1))

    @property
    def month(self) -> MonthKey:
        """Return the calendar month the period is attributed to."""

        return MonthKey.of(self.end_date)

    @property
    def days(self) -> int:
        """Return the billable day count of the rated span."""

        return billing_days(self.span, self.zone, self.profile.day_count)

    @property
    def cycle_days(self) -> int:
        """Return the billable day count of the whole cycle."""

        return billing_days(self.cycle_span, self.zone, self.profile.day_count)

    @property
    def served_days(self) -> int:
        """Return the days service was actually connected within the span."""

        if self.served_span is None:
            return self.days
        return billing_days(self.served_span, self.zone, self.profile.day_count)

    @property
    def days_in_calendar_month(self) -> int:
        """Return the length of the calendar month the period ends in."""

        return days_in_month(self.month.year, self.month.month)

    @property
    def is_partial_cycle(self) -> bool:
        """Return ``True`` when the rated span is shorter than the cycle."""

        return self.span.duration < self.cycle_span.duration

    def day_type(self, day: date) -> DayType:
        """Classify a local date under the profile's day-type rules."""

        return classify_day(day, self.holidays, self.profile.day_types)

    def local_days(self) -> list[tuple[date, Span]]:
        """Return the local days the span covers with their true extents."""

        return self.span.local_days(self.zone)

    # -- money ----------------------------------------------------------

    def money(self, amount: Decimal | str | int) -> Money:
        """Build an amount in the bill's currency."""

        return Money(D(amount), self.currency)

    @property
    def zero(self) -> Money:
        """Return a zero amount in the bill's currency."""

        return Money.zero(self.currency)

    # -- determinants ---------------------------------------------------

    def quantity(self, name: str, unit: Unit) -> Quantity:
        """Return a required determinant's quantity in ``unit``."""

        return self.determinants.quantity(name, unit)

    def optional_quantity(self, name: str, unit: Unit) -> Quantity:
        """Return a determinant's quantity, or zero when it is absent."""

        return self.determinants.quantity_or_zero(name, unit)

    def has(self, name: str) -> bool:
        """Return ``True`` when a determinant was computed."""

        return name in self.determinants

    # -- diagnostics ----------------------------------------------------

    def warn(self, code: str, message: str, **context: Any) -> None:
        """Record a warning against the bill."""

        self.diagnostics.emit(
            code, message, Severity.WARNING, self.service_point_id, **context
        )

    def notice(self, code: str, message: str, **context: Any) -> None:
        """Record a notice that a convention was applied."""

        self.diagnostics.emit(
            code, message, Severity.NOTICE, self.service_point_id, **context
        )

    # -- derived ratios -------------------------------------------------

    @property
    def cycle_fraction(self) -> Decimal:
        """Return the rated span's share of the whole cycle, by days."""

        return safe_divide(D(self.days), D(self.cycle_days), default=D(1))

    def for_span(self, span: Span) -> "RatingContext":
        """Return a copy narrowed to ``span``, sharing the diagnostics bag."""

        return RatingContext(
            span,
            self.cycle_span,
            self.zone,
            self.profile,
            self.determinants,
            self.service_point_id,
            self.tariff_code,
            self.currency,
            self.holidays,
            self.served_span,
            self.diagnostics,
            dict(self.notes),
        )

    def with_determinants(self, determinants: DeterminantSet) -> "RatingContext":
        """Return a copy carrying a different determinant set."""

        return RatingContext(
            self.span,
            self.cycle_span,
            self.zone,
            self.profile,
            determinants,
            self.service_point_id,
            self.tariff_code,
            self.currency,
            self.holidays,
            self.served_span,
            self.diagnostics,
            dict(self.notes),
        )
