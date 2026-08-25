"""A minimal fixed-width table renderer.

Bills and meter data reports are mostly tables, and every one of them has to
line up in a terminal at 80 columns.  This is the only table code in the
repository; report modules describe their columns and hand them over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .text import align, ellipsis

__all__ = ["Column", "Table", "render_table"]


@dataclass(frozen=True, slots=True)
class Column:
    """One column of a rendered table."""

    key: str
    title: str
    align: str = "left"
    width: int | None = None
    """Fixed width; when ``None`` the column sizes to its widest cell."""

    max_width: int | None = None
    """Upper bound applied to an auto-sized column before truncation."""


@dataclass(slots=True)
class Table:
    """An accumulating table of string cells."""

    columns: tuple[Column, ...]
    rows: list[dict[str, str]] = field(default_factory=list)
    title: str = ""

    def add(self, **cells: str) -> None:
        """Append a row given as keyword cells."""

        self.rows.append({key: str(value) for key, value in cells.items()})

    def add_row(self, row: dict[str, str]) -> None:
        """Append a row given as a mapping."""

        self.rows.append({key: str(value) for key, value in row.items()})

    def extend(self, rows: Iterable[dict[str, str]]) -> None:
        """Append several rows."""

        for row in rows:
            self.add_row(row)

    @property
    def is_empty(self) -> bool:
        """Return ``True`` when no rows have been added."""

        return not self.rows

    def widths(self) -> list[int]:
        """Compute the rendered width of every column."""

        result: list[int] = []
        for column in self.columns:
            if column.width is not None:
                result.append(column.width)
                continue
            widest = len(column.title)
            for row in self.rows:
                widest = max(widest, len(row.get(column.key, "")))
            if column.max_width is not None:
                widest = min(widest, column.max_width)
            result.append(widest)
        return result

    def render(self, *, separator: str = "  ", underline: str = "-") -> list[str]:
        """Render the table as a list of lines."""

        widths = self.widths()
        lines: list[str] = []
        if self.title:
            lines.append(self.title)
        header = separator.join(
            align(column.title, widths[index], column.align)
            for index, column in enumerate(self.columns)
        ).rstrip()
        lines.append(header)
        lines.append(
            separator.join(underline * width for width in widths).rstrip()
        )
        for row in self.rows:
            cells = [
                align(
                    ellipsis(row.get(column.key, ""), widths[index]),
                    widths[index],
                    column.align,
                )
                for index, column in enumerate(self.columns)
            ]
            lines.append(separator.join(cells).rstrip())
        return lines

    def to_text(self, **kwargs: str) -> str:
        """Render the table as a single string."""

        return "\n".join(self.render(**kwargs))


def render_table(
    columns: Sequence[Column],
    rows: Iterable[dict[str, str]],
    title: str = "",
) -> str:
    """Render columns and rows in one call."""

    table = Table(tuple(columns), title=title)
    table.extend(rows)
    return table.to_text()
