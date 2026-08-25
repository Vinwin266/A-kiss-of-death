"""Text formatting helpers used by the report and CLI layers.

Rendering lives away from the engine so that changing how a bill *looks*
cannot change what it *says*.  Everything here is pure string work.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence

from .decimals import D
from .rounding import RoundingMode, quantize

__all__ = [
    "align",
    "bullet",
    "dedent_block",
    "ellipsis",
    "format_decimal",
    "heading",
    "indent",
    "plural",
    "rule",
    "titlecase",
    "wrap",
]


def format_decimal(value: Decimal | str | int, places: int = 2) -> str:
    """Render a decimal with a fixed number of places, half-up."""

    return f"{quantize(D(value), places, RoundingMode.HALF_UP):.{places}f}"


def align(text: str, width: int, how: str = "left") -> str:
    """Pad ``text`` to ``width`` using ``left``, ``right`` or ``center``."""

    if how == "right":
        return text.rjust(width)
    if how == "center":
        return text.center(width)
    return text.ljust(width)


def ellipsis(text: str, width: int) -> str:
    """Truncate ``text`` to ``width``, marking the cut with an ellipsis."""

    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def rule(width: int = 72, character: str = "-") -> str:
    """Return a horizontal rule."""

    return character * width


def heading(title: str, width: int = 72, character: str = "=") -> str:
    """Return a two-line heading: the title, then an underline."""

    return f"{title}\n{character * min(width, max(len(title), 4))}"


def indent(text: str, spaces: int = 2) -> str:
    """Indent every non-empty line of ``text``."""

    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


def dedent_block(text: str) -> str:
    """Remove the common leading whitespace from a block of lines."""

    lines = [line for line in text.split("\n")]
    widths = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    if not widths:
        return text
    cut = min(widths)
    return "\n".join(line[cut:] if line.strip() else line for line in lines)


def bullet(items: Iterable[str], marker: str = "-", spaces: int = 2) -> str:
    """Render an iterable as a bullet list."""

    pad = " " * spaces
    return "\n".join(f"{pad}{marker} {item}" for item in items)


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Return ``"1 day"`` or ``"3 days"``."""

    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural_form or singular + 's'}"


def titlecase(text: str) -> str:
    """Turn ``"peak_summer"`` into ``"Peak Summer"``."""

    return " ".join(part.capitalize() for part in text.replace("_", " ").split())


def wrap(text: str, width: int = 72) -> list[str]:
    """Wrap ``text`` to ``width`` without breaking words."""

    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def columns(rows: Sequence[Sequence[str]], gap: int = 2) -> list[str]:
    """Render rows of already-stringified cells as aligned columns."""

    if not rows:
        return []
    width_count = max(len(row) for row in rows)
    widths = [0] * width_count
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    separator = " " * gap
    return [
        separator.join(
            align(cell, widths[index]) for index, cell in enumerate(row)
        ).rstrip()
        for row in rows
    ]
