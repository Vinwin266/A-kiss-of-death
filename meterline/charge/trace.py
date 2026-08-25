"""A record of how a number was arrived at.

Any line item can be asked to justify itself.  The trace is a flat list of
steps, each naming an input, an operation and a result, which is what the
``explain`` command renders.  It is deliberately not a tree: nesting made it
tempting to skip steps, and a skipped step is exactly the one a
reconciliation dispute turns on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

__all__ = ["TraceStep", "Trace"]


@dataclass(frozen=True, slots=True)
class TraceStep:
    """One recorded step of a computation."""

    label: str
    detail: str = ""
    value: str = ""

    def render(self, width: int = 28) -> str:
        """Render as a single aligned line."""

        head = self.label.ljust(width)
        if self.detail and self.value:
            return f"{head}{self.detail} = {self.value}"
        return f"{head}{self.detail or self.value}"

    def as_dict(self) -> dict[str, str]:
        """Return a JSON friendly view."""

        return {"label": self.label, "detail": self.detail, "value": self.value}


@dataclass(slots=True)
class Trace:
    """An ordered, append-only collection of steps."""

    steps: list[TraceStep] = field(default_factory=list)

    def add(self, label: str, detail: str = "", value: Any = "") -> None:
        """Append one step."""

        self.steps.append(TraceStep(label, str(detail), str(value)))

    def extend(self, steps: Iterable[TraceStep]) -> None:
        """Append several steps."""

        self.steps.extend(steps)

    def merge(self, other: "Trace", prefix: str = "") -> None:
        """Absorb another trace, optionally prefixing its labels."""

        for step in other.steps:
            label = f"{prefix}{step.label}" if prefix else step.label
            self.steps.append(TraceStep(label, step.detail, step.value))

    def freeze(self) -> tuple[TraceStep, ...]:
        """Return an immutable snapshot of the steps."""

        return tuple(self.steps)

    def render(self, indent: int = 0) -> str:
        """Render every step, one per line."""

        pad = " " * indent
        return "\n".join(pad + step.render() for step in self.steps)

    def as_list(self) -> list[dict[str, str]]:
        """Return a JSON friendly view."""

        return [step.as_dict() for step in self.steps]

    def __iter__(self) -> Iterator[TraceStep]:
        return iter(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    def __bool__(self) -> bool:
        return bool(self.steps)
