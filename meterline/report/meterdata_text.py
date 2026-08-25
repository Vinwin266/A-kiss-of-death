"""Rendering meter data: reads, derived consumption and interval series."""

from __future__ import annotations

from typing import Sequence

from ..core.tables import Column, Table
from ..core.text import heading
from ..meterdata.consumption import Consumption
from ..meterdata.gaps import Gap
from ..model.reading import MeterRead
from ..model.series import IntervalSeries
from ..timeline.instants import format_instant
from ..timeline.zones import Zone

__all__ = ["render_reads", "render_consumption", "render_series", "render_gaps"]


def render_reads(reads: Sequence[MeterRead], zone: Zone) -> str:
    """Render a register's read history."""

    table = Table(
        (
            Column("when", "local time"),
            Column("register", "register"),
            Column("value", "dial", align="right"),
            Column("type", "type"),
            Column("quality", "quality"),
            Column("source", "source", max_width=18),
        ),
        title="meter reads",
    )
    for read in reads:
        table.add(
            when=zone.to_local(read.at).strftime("%Y-%m-%d %H:%M"),
            register=read.register_id,
            value=str(read.value),
            type=read.read_type.value,
            quality=read.quality.value,
            source=read.source,
        )
    return table.to_text()


def render_consumption(records: Sequence[Consumption], zone: Zone) -> str:
    """Render derived consumption records."""

    table = Table(
        (
            Column("from", "from"),
            Column("to", "to"),
            Column("usage", "usage", align="right"),
            Column("daily", "per day", align="right"),
            Column("quality", "quality"),
            Column("source", "source", max_width=14),
        ),
        title="derived consumption",
    )
    for record in records:
        table.add(
            **{
                "from": zone.to_local(record.span.start).strftime("%Y-%m-%d %H:%M"),
                "to": zone.to_local(record.span.end).strftime("%Y-%m-%d %H:%M"),
                "usage": record.quantity.format(1),
                "daily": f"{record.daily_rate:.1f}",
                "quality": record.quality.value,
                "source": record.source,
            }
        )
    return table.to_text()


def render_series(series: IntervalSeries, zone: Zone, *, limit: int = 24) -> str:
    """Render the head of an interval series."""

    lines = [heading(series.describe(), 72)]
    table = Table(
        (
            Column("when", "local time"),
            Column("value", "value", align="right"),
            Column("quality", "quality"),
        )
    )
    for index, point in enumerate(series):
        if index >= limit:
            break
        table.add(
            when=zone.to_local(point.span.start).strftime("%Y-%m-%d %H:%M"),
            value="missing" if point.is_missing else str(point.value),
            quality=point.quality.value,
        )
    lines.extend(table.render())
    if len(series) > limit:
        lines.append(f"... {len(series) - limit} further intervals")
    lines.append(f"total: {series.total().format(1)}")
    return "\n".join(lines)


def render_gaps(gaps: Sequence[Gap], zone: Zone) -> str:
    """Render the gaps found in a period."""

    if not gaps:
        return "no gaps"
    table = Table(
        (
            Column("from", "from"),
            Column("to", "to"),
            Column("hours", "hours", align="right"),
            Column("reason", "reason", max_width=30),
        ),
        title="gaps",
    )
    for gap in gaps:
        table.add(
            **{
                "from": zone.to_local(gap.span.start).strftime("%Y-%m-%d %H:%M"),
                "to": zone.to_local(gap.span.end).strftime("%Y-%m-%d %H:%M"),
                "hours": f"{gap.span.hours:.1f}",
                "reason": gap.reason,
            }
        )
    return table.to_text()


def render_read_span(read: MeterRead) -> str:
    """Render a single read as one line, in UTC."""

    return f"{format_instant(read.at)} {read.register_id} {read.value}"
