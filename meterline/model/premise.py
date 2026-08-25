"""Premises: the places service is delivered to."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Premise"]


@dataclass(frozen=True, slots=True)
class Premise:
    """A physical location, independent of who occupies it.

    Kept separate from :class:`~meterline.model.account.Account` because
    occupancy changes and metering does not: a move-out and a move-in on the
    same day produce two accounts, one premise and one continuous meter
    series, and any of the three getting merged into the others is how a
    final bill ends up containing the next tenant's usage.
    """

    premise_id: str
    address: str = ""
    locality: str = ""
    region: str = ""
    postcode: str = ""
    jurisdiction: str = ""
    """Tax jurisdiction code; resolved against the tax rule set."""

    climate_zone: str = ""
    """Used by weather-sensitive estimation strategies."""

    @property
    def display_address(self) -> str:
        """Return a single-line address for rendering."""

        parts = [part for part in (self.address, self.locality, self.region) if part]
        line = ", ".join(parts)
        return f"{line} {self.postcode}".strip() if self.postcode else line

    def describe(self) -> str:
        """Return a one-line description for reports."""

        return f"{self.premise_id}: {self.display_address or 'no address on file'}"
