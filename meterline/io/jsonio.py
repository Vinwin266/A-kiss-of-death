"""Canonical JSON.

Two runs that produce the same data must produce the same bytes, so every
document the engine writes goes through :func:`canonical_dumps`: keys
sorted, a fixed indent, a trailing newline, and no reliance on the ASCII
escaping default changing between versions.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from ..errors import DatasetError

__all__ = ["canonical_dumps", "canonical_loads", "JsonEncoder"]


class JsonEncoder(json.JSONEncoder):
    """Encodes the few non-JSON types the engine produces."""

    def default(self, o: Any) -> Any:  # noqa: D102 - inherited
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (set, frozenset)):
            return sorted(str(item) for item in o)
        if hasattr(o, "as_dict"):
            return o.as_dict()
        if hasattr(o, "value") and hasattr(o, "name"):
            return o.value
        return super().default(o)


def canonical_dumps(document: Any, *, indent: int = 2) -> str:
    """Render a document as canonical JSON with a trailing newline."""

    return (
        json.dumps(
            document,
            cls=JsonEncoder,
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ": "),
        )
        + "\n"
    )


def canonical_loads(text: str, *, what: str = "document") -> Any:
    """Parse JSON, raising :class:`DatasetError` on malformed input."""

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise DatasetError(
            f"could not read {what} as JSON",
            line=error.lineno,
            column=error.colno,
            detail=error.msg,
        ) from None
