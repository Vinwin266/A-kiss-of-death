"""Seasons: month-and-day ranges that select a rate.

Seasons wrap the year end more often than not — a winter season running
November to March is the common case — so the containment test cannot be a
simple pair of comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..errors import TariffError

__all__ = ["Season", "SeasonSet"]


@dataclass(frozen=True, slots=True)
class Season:
    """A named part of the year, inclusive of both endpoints."""

    code: str
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    label: str = ""

    def __post_init__(self) -> None:
        for month in (self.start_month, self.end_month):
            if not 1 <= month <= 12:
                raise TariffError("season month out of range", season=self.code)
        for day in (self.start_day, self.end_day):
            if not 1 <= day <= 31:
                raise TariffError("season day out of range", season=self.code)

    @property
    def wraps_year_end(self) -> bool:
        """Return ``True`` when the season runs through 31 December."""

        return (self.end_month, self.end_day) < (self.start_month, self.start_day)

    def contains(self, day: date) -> bool:
        """Return ``True`` when ``day`` falls in the season."""

        marker = (day.month, day.day)
        start = (self.start_month, self.start_day)
        end = (self.end_month, self.end_day)
        if self.wraps_year_end:
            return marker >= start or marker <= end
        return start <= marker <= end

    @property
    def display_name(self) -> str:
        """Return the label, falling back to the code."""

        return self.label or self.code

    def as_dict(self) -> dict[str, object]:
        """Return the document form the loader reads back."""

        return {
            "code": self.code,
            "start_month": self.start_month,
            "start_day": self.start_day,
            "end_month": self.end_month,
            "end_day": self.end_day,
            "label": self.label,
        }

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return (
            f"{self.display_name}: {self.start_month:02d}-{self.start_day:02d} "
            f"to {self.end_month:02d}-{self.end_day:02d}"
        )


@dataclass(frozen=True, slots=True)
class SeasonSet:
    """An ordered collection of seasons covering the year."""

    seasons: tuple[Season, ...] = ()
    default_code: str = ""

    def season_for(self, day: date) -> str:
        """Return the code of the season containing ``day``.

        The first matching season wins, so overlapping definitions resolve
        in declaration order rather than raising; the tariff validator is
        where an overlap is reported.
        """

        for season in self.seasons:
            if season.contains(day):
                return season.code
        return self.default_code

    def get(self, code: str) -> Season:
        """Return a season by code."""

        for season in self.seasons:
            if season.code == code:
                return season
        raise TariffError("unknown season", code=code)

    @property
    def codes(self) -> tuple[str, ...]:
        """Return the season codes in declaration order."""

        return tuple(season.code for season in self.seasons)

    def covers_year(self) -> bool:
        """Return ``True`` when every day of a year lands in some season."""

        probe = date(2024, 1, 1)
        for offset in range(366):
            day = date.fromordinal(probe.toordinal() + offset)
            if not any(season.contains(day) for season in self.seasons):
                return False
        return True

    def as_dict(self) -> dict[str, object]:
        """Return the document form the loader reads back."""

        return {
            "seasons": [season.as_dict() for season in self.seasons],
            "default_season": self.default_code,
        }

    def describe(self) -> str:
        """Return one line per season."""

        return "\n".join(season.describe() for season in self.seasons)
