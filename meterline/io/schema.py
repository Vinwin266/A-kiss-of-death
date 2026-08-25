"""A very small schema helper.

Not a validation framework — just enough structure that a malformed dataset
produces "accounts[2] is missing 'account_id'" instead of a ``KeyError``
raised four frames into the decoder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import SchemaError

__all__ = ["Field", "require_keys", "take_str", "take_int", "take_bool", "take_list", "take_map"]


@dataclass(frozen=True, slots=True)
class Field:
    """One expected key of a document."""

    name: str
    required: bool = True
    description: str = ""


def _path(context: str, key: str) -> str:
    """Render a dotted path for an error message."""

    return f"{context}.{key}" if context else key


def require_keys(
    document: Mapping[str, Any], keys: Sequence[str], *, context: str = ""
) -> None:
    """Raise when any of ``keys`` is missing."""

    missing = [key for key in keys if key not in document]
    if missing:
        raise SchemaError(
            "required keys are missing",
            context=context or "document",
            missing=", ".join(missing),
            present=", ".join(sorted(str(key) for key in document)),
        )


def take_str(
    document: Mapping[str, Any], key: str, *, context: str = "", default: str | None = None
) -> str:
    """Return a string field, or ``default`` when absent."""

    if key not in document:
        if default is None:
            raise SchemaError("required key is missing", context=_path(context, key))
        return default
    value = document[key]
    if not isinstance(value, str):
        raise SchemaError(
            "expected a string", context=_path(context, key), found=type(value).__name__
        )
    return value


def take_int(
    document: Mapping[str, Any], key: str, *, context: str = "", default: int | None = None
) -> int:
    """Return an integer field, or ``default`` when absent."""

    if key not in document:
        if default is None:
            raise SchemaError("required key is missing", context=_path(context, key))
        return default
    value = document[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(
            "expected an integer", context=_path(context, key), found=type(value).__name__
        )
    return value


def take_bool(
    document: Mapping[str, Any], key: str, *, context: str = "", default: bool = False
) -> bool:
    """Return a boolean field, or ``default`` when absent."""

    value = document.get(key, default)
    if not isinstance(value, bool):
        raise SchemaError(
            "expected true or false", context=_path(context, key), found=str(value)
        )
    return value


def take_list(
    document: Mapping[str, Any], key: str, *, context: str = ""
) -> list[Any]:
    """Return a list field, defaulting to an empty list."""

    value = document.get(key, [])
    if not isinstance(value, list):
        raise SchemaError(
            "expected a list", context=_path(context, key), found=type(value).__name__
        )
    return value


def take_map(
    document: Mapping[str, Any], key: str, *, context: str = ""
) -> dict[str, Any]:
    """Return an object field, defaulting to an empty mapping."""

    value = document.get(key, {})
    if not isinstance(value, dict):
        raise SchemaError(
            "expected an object", context=_path(context, key), found=type(value).__name__
        )
    return value
