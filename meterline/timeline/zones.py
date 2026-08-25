"""Timezones with explicit daylight-saving rules.

The engine deliberately does not use :mod:`zoneinfo`.  A bill has to be
reproducible years later, and the IANA database is a moving target: rerun a
2019 bill on a machine with a 2026 tzdata and a jurisdiction that abolished
daylight saving in between will re-bucket every peak hour.  Rules are
therefore data in the dataset, versioned with everything else.

The cost is that historical rule changes must be modelled explicitly, which
:class:`Zone` supports through dated rule segments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping

from ..errors import TimelineError
from .instants import ensure_utc
from .rules import DateRule, LastWeekday, NthWeekday, Weekday

__all__ = [
    "UTC",
    "DstRule",
    "Zone",
    "ZoneRegistry",
    "common_zone",
    "AmbiguousTime",
    "NonexistentTime",
]


class AmbiguousTime(TimelineError):
    """Raised when a wall-clock time happens twice and no fold was given."""

    code = "meterline.timeline.ambiguous"


class NonexistentTime(TimelineError):
    """Raised when a wall-clock time is skipped by a spring-forward."""

    code = "meterline.timeline.nonexistent"


@dataclass(frozen=True, slots=True)
class DstRule:
    """When daylight saving starts and ends, and by how much."""

    start: DateRule
    end: DateRule
    offset_minutes: int = 60
    start_hour: int = 2
    """Local *standard* hour at which the clocks go forward."""

    end_hour: int = 2
    """Local *daylight* hour at which the clocks go back."""

    @property
    def shift(self) -> timedelta:
        """Return the size of the daylight-saving shift."""

        return timedelta(minutes=self.offset_minutes)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"+{self.offset_minutes}m from {self.start.describe()} "
            f"to {self.end.describe()}"
        )


@dataclass(frozen=True, slots=True)
class Zone:
    """A named zone: a standard offset plus optional daylight rules."""

    name: str
    standard_offset_minutes: int
    dst: DstRule | None = None
    abbreviation: str = ""
    dst_abbreviation: str = ""

    # -- offsets --------------------------------------------------------

    @property
    def standard_offset(self) -> timedelta:
        """Return the year-round base offset from UTC."""

        return timedelta(minutes=self.standard_offset_minutes)

    def transitions(self, year: int) -> tuple[datetime, datetime] | None:
        """Return the two UTC transition instants for ``year``.

        The first is the instant the clocks go forward, the second the
        instant they go back.  ``None`` when the zone has no daylight rules.
        """

        if self.dst is None:
            return None
        forward_local = datetime.combine(
            self.dst.start.resolve(year), datetime.min.time()
        ) + timedelta(hours=self.dst.start_hour)
        back_local = datetime.combine(
            self.dst.end.resolve(year), datetime.min.time()
        ) + timedelta(hours=self.dst.end_hour)
        forward = forward_local.replace(tzinfo=timezone.utc) - self.standard_offset
        back = (
            back_local.replace(tzinfo=timezone.utc)
            - self.standard_offset
            - self.dst.shift
        )
        return forward, back

    def is_dst(self, instant: datetime) -> bool:
        """Return ``True`` when daylight saving is in force at ``instant``."""

        if self.dst is None:
            return False
        moment = ensure_utc(instant)
        bounds = self.transitions(moment.year)
        if bounds is None:  # pragma: no cover - guarded above
            return False
        forward, back = bounds
        if forward <= back:
            return forward <= moment < back
        # Southern hemisphere: daylight saving wraps the new year.
        return moment >= forward or moment < back

    def offset_at(self, instant: datetime) -> timedelta:
        """Return the UTC offset in force at ``instant``."""

        if self.dst is not None and self.is_dst(instant):
            return self.standard_offset + self.dst.shift
        return self.standard_offset

    def abbreviation_at(self, instant: datetime) -> str:
        """Return the zone abbreviation in force at ``instant``."""

        if self.dst is not None and self.is_dst(instant):
            return self.dst_abbreviation or self.abbreviation
        return self.abbreviation

    # -- conversions ----------------------------------------------------

    def to_local(self, instant: datetime) -> datetime:
        """Convert a UTC instant to a naive wall-clock time in this zone."""

        moment = ensure_utc(instant)
        return (moment + self.offset_at(moment)).replace(tzinfo=None)

    def local_date(self, instant: datetime) -> date:
        """Return the local calendar date containing ``instant``."""

        return self.to_local(instant).date()

    def from_local(
        self, wall: datetime, *, fold: int = 0, on_gap: str = "shift"
    ) -> datetime:
        """Convert a naive wall-clock time in this zone to a UTC instant.

        ``fold`` disambiguates the repeated hour in autumn: ``0`` picks the
        first (still daylight-saving) occurrence, ``1`` the second.  A time
        that does not exist at all is either shifted forward past the gap
        (``on_gap="shift"``) or refused (``on_gap="raise"``).
        """

        if wall.tzinfo is not None:
            raise TimelineError(
                "wall-clock times must be naive", value=wall.isoformat()
            )
        candidates: list[datetime] = []
        offsets = {self.standard_offset}
        if self.dst is not None:
            offsets.add(self.standard_offset + self.dst.shift)
        for offset in sorted(offsets, reverse=True):
            candidate = wall.replace(tzinfo=timezone.utc) - offset
            if self.offset_at(candidate) == offset:
                candidates.append(candidate)
        if not candidates:
            if on_gap == "raise":
                raise NonexistentTime(
                    "this wall-clock time is skipped by a clock change",
                    zone=self.name,
                    value=wall.isoformat(),
                )
            shift = self.dst.shift if self.dst else timedelta(hours=1)
            return self.from_local(wall + shift, fold=fold, on_gap="raise")
        if len(candidates) == 1:
            return candidates[0]
        candidates.sort()
        return candidates[min(fold, len(candidates) - 1)]

    def day_start(self, day: date) -> datetime:
        """Return the UTC instant at which the local calendar day begins.

        On a spring-forward day whose transition happens at midnight this is
        the first instant that exists, not the nominal one.
        """

        return self.from_local(datetime.combine(day, datetime.min.time()))

    def day_length_hours(self, day: date) -> int:
        """Return 23, 24 or 25 depending on any clock change that day."""

        start = self.day_start(day)
        end = self.day_start(day + timedelta(days=1))
        return int((end - start).total_seconds() // 3600)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        sign = "-" if self.standard_offset_minutes < 0 else "+"
        magnitude = abs(self.standard_offset_minutes)
        base = f"{self.name} (UTC{sign}{magnitude // 60:02d}:{magnitude % 60:02d})"
        if self.dst is None:
            return f"{base}, no daylight saving"
        return f"{base}, {self.dst.describe()}"


UTC = Zone("UTC", 0, None, "UTC")
"""The zone with no offset and no rules; the engine's storage zone."""

_US_DST = DstRule(
    start=NthWeekday(3, Weekday.SUNDAY, 2),
    end=NthWeekday(11, Weekday.SUNDAY, 1),
)

_EU_DST = DstRule(
    start=LastWeekday(3, Weekday.SUNDAY),
    end=LastWeekday(10, Weekday.SUNDAY),
    start_hour=1,
    end_hour=2,
)

_BUILTIN_ZONES: dict[str, Zone] = {
    "UTC": UTC,
    "America/New_York": Zone("America/New_York", -300, _US_DST, "EST", "EDT"),
    "America/Chicago": Zone("America/Chicago", -360, _US_DST, "CST", "CDT"),
    "America/Denver": Zone("America/Denver", -420, _US_DST, "MST", "MDT"),
    "America/Phoenix": Zone("America/Phoenix", -420, None, "MST"),
    "America/Los_Angeles": Zone("America/Los_Angeles", -480, _US_DST, "PST", "PDT"),
    "Europe/London": Zone("Europe/London", 0, _EU_DST, "GMT", "BST"),
    "Europe/Madrid": Zone("Europe/Madrid", 60, _EU_DST, "CET", "CEST"),
}


@dataclass(slots=True)
class ZoneRegistry:
    """A lookup from zone name to :class:`Zone`, extensible per dataset."""

    zones: dict[str, Zone] = field(default_factory=lambda: dict(_BUILTIN_ZONES))

    def register(self, zone: Zone) -> None:
        """Add or replace a zone."""

        self.zones[zone.name] = zone

    def extend(self, zones: Iterable[Zone]) -> None:
        """Add several zones."""

        for zone in zones:
            self.register(zone)

    def get(self, name: str) -> Zone:
        """Return the named zone or raise :class:`TimelineError`."""

        try:
            return self.zones[name]
        except KeyError:
            raise TimelineError(
                "unknown timezone",
                name=name,
                known=", ".join(sorted(self.zones)),
            ) from None

    def names(self) -> list[str]:
        """Return the registered zone names, sorted."""

        return sorted(self.zones)

    def as_mapping(self) -> Mapping[str, Zone]:
        """Return a read-only view of the registry."""

        return dict(self.zones)


_DEFAULT_REGISTRY = ZoneRegistry()


def common_zone(name: str) -> Zone:
    """Return one of the built-in zones by IANA-style name."""

    return _DEFAULT_REGISTRY.get(name)
