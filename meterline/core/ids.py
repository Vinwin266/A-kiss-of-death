"""Deterministic identifiers.

Nothing in the engine may reach for :mod:`uuid` or :mod:`random`.  A bill
produced twice from the same inputs must carry the same line item ids, or a
byte-for-byte comparison of two runs is impossible and the determinism claim
in the README is untestable.  Ids are therefore content hashes.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

__all__ = ["stable_id", "digest_of", "short_digest", "sequence_id"]

_DEFAULT_LENGTH = 12


def _normalise(part: Any) -> str:
    """Render one component of an id in a stable, unambiguous way."""

    if part is None:
        return "\x00none"
    if isinstance(part, bool):
        return "\x00true" if part else "\x00false"
    if isinstance(part, (list, tuple)):
        return "[" + "\x1f".join(_normalise(item) for item in part) + "]"
    if isinstance(part, dict):
        rendered = "\x1f".join(
            f"{key}\x1e{_normalise(part[key])}" for key in sorted(part)
        )
        return "{" + rendered + "}"
    return str(part)


def digest_of(*parts: Any) -> str:
    """Return the full hex SHA-256 digest of the normalised ``parts``."""

    joined = "\x1d".join(_normalise(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def short_digest(*parts: Any, length: int = _DEFAULT_LENGTH) -> str:
    """Return a truncated digest, long enough to not collide in practice."""

    return digest_of(*parts)[:length]


def stable_id(prefix: str, *parts: Any, length: int = _DEFAULT_LENGTH) -> str:
    """Return ``prefix-<hash>`` derived from ``parts``.

    Two runs over the same inputs produce identical ids; changing any input
    changes the id, which makes a diff of two bills point at what moved.
    """

    return f"{prefix}-{short_digest(*parts, length=length)}"


def sequence_id(prefix: str, index: int, *, width: int = 4) -> str:
    """Return ``prefix-0007`` for ordered collections such as line items."""

    return f"{prefix}-{index:0{width}d}"


def fingerprint(items: Iterable[Any]) -> str:
    """Return one digest covering an ordered collection."""

    return digest_of(list(items))
