"""Deterministic ordering helpers.

Two runs of the engine must visit records in the same order, so no part of
the codebase iterates a set or an unsorted dict when the order can reach the
output.  These helpers make the sorted traversal the path of least effort.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

T = TypeVar("T")
K = TypeVar("K")

__all__ = [
    "by_attribute",
    "dedupe",
    "group_by",
    "sorted_items",
    "sorted_values",
    "stable_sort",
]


def sorted_items(mapping: Mapping[K, T]) -> list[tuple[K, T]]:
    """Return a mapping's items sorted by key."""

    return [(key, mapping[key]) for key in sorted(mapping)]  # type: ignore[type-var]


def sorted_values(mapping: Mapping[K, T]) -> list[T]:
    """Return a mapping's values ordered by their keys."""

    return [mapping[key] for key in sorted(mapping)]  # type: ignore[type-var]


def stable_sort(items: Iterable[T], key: Callable[[T], Any]) -> list[T]:
    """Sort with an explicit key; a thin alias that documents intent."""

    return sorted(items, key=key)


def by_attribute(name: str) -> Callable[[Any], Any]:
    """Return a key function reading ``name`` from each item."""

    def key(item: Any) -> Any:
        return getattr(item, name)

    return key


def group_by(items: Iterable[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    """Group ``items`` into a dict, preserving encounter order per group."""

    grouped: dict[K, list[T]] = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return grouped


def dedupe(items: Iterable[T], key: Callable[[T], Any] | None = None) -> list[T]:
    """Remove duplicates, keeping the first occurrence of each key."""

    seen: set[Any] = set()
    result: list[T] = []
    for item in items:
        marker = key(item) if key is not None else item
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def first(items: Sequence[T], default: T | None = None) -> T | None:
    """Return the first item or ``default`` for an empty sequence."""

    return items[0] if items else default


def last(items: Sequence[T], default: T | None = None) -> T | None:
    """Return the last item or ``default`` for an empty sequence."""

    return items[-1] if items else default
