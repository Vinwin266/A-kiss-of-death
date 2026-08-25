"""Construction, parsing and rendering of UTC instants."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..errors import TimelineError

__all__ = [
    "EPOCH",
    "ensure_utc",
    "format_date",
    "format_instant",
    "is_aware",
    "parse_date",
    "parse_instant",
    "utc",
    "utc_from_date",
]

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
"""The reference instant; used as an ordering floor, never as "now"."""


def utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    """Build an aware UTC instant."""

    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def utc_from_date(day: date) -> datetime:
    """Return midnight UTC on ``day``."""

    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def is_aware(value: datetime) -> bool:
    """Return ``True`` when ``value`` carries a usable UTC offset."""

    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def ensure_utc(value: datetime, *, what: str = "instant") -> datetime:
    """Return ``value`` normalised to UTC, refusing naive datetimes.

    Refusing rather than assuming is deliberate: a naive datetime that
    reaches the engine is either a wall-clock time that lost its zone or a
    UTC instant that lost its marker, and guessing which produces a bill
    that is wrong by an offset nobody notices until October.
    """

    if not is_aware(value):
        raise TimelineError(f"{what} must be timezone-aware", value=value.isoformat())
    return value.astimezone(timezone.utc)


def parse_instant(text: str, *, what: str = "instant") -> datetime:
    """Parse an ISO-8601 instant, accepting a trailing ``Z``."""

    cleaned = text.strip()
    if cleaned.endswith(("Z", "z")):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        raise TimelineError(f"could not read {what}", value=text) from None
    if not is_aware(parsed):
        raise TimelineError(
            f"{what} needs an explicit offset or a trailing Z", value=text
        )
    return parsed.astimezone(timezone.utc)


def parse_date(text: str, *, what: str = "date") -> date:
    """Parse an ISO-8601 calendar date."""

    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise TimelineError(f"could not read {what}", value=text) from None


def format_instant(value: datetime, *, seconds: bool = False) -> str:
    """Render an instant as ``2025-06-01T00:00Z``."""

    normalised = ensure_utc(value)
    pattern = "%Y-%m-%dT%H:%M:%SZ" if seconds else "%Y-%m-%dT%H:%MZ"
    return normalised.strftime(pattern)


def format_date(value: date) -> str:
    """Render a calendar date as ``2025-06-01``."""

    return value.isoformat()


def floor_to(value: datetime, minutes: int) -> datetime:
    """Round an instant down to a multiple of ``minutes`` past the hour."""

    if minutes <= 0:
        raise TimelineError("interval width must be positive", minutes=minutes)
    normalised = ensure_utc(value)
    total = normalised.hour * 60 + normalised.minute
    floored = (total // minutes) * minutes
    return normalised.replace(
        hour=floored // 60, minute=floored % 60, second=0, microsecond=0
    )


def ceil_to(value: datetime, minutes: int) -> datetime:
    """Round an instant up to a multiple of ``minutes`` past the hour."""

    floored = floor_to(value, minutes)
    if floored == ensure_utc(value):
        return floored
    return floored + timedelta(minutes=minutes)
