"""A value paired with the diagnostics produced while computing it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from .diagnostics import DiagnosticBag, Severity

T = TypeVar("T")
U = TypeVar("U")

__all__ = ["Outcome"]


@dataclass(slots=True)
class Outcome(Generic[T]):
    """The result of a fallible computation that does not raise.

    Most engine entry points return one of these.  Callers that only care
    about the answer read :attr:`value`; callers that have to justify the
    answer read :attr:`diagnostics`.  Neither can be dropped by accident,
    which is the point of pairing them.
    """

    value: T
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)

    @classmethod
    def ok(cls, value: T) -> "Outcome[T]":
        """Wrap a value with an empty diagnostic bag."""

        return cls(value, DiagnosticBag())

    @property
    def is_ok(self) -> bool:
        """Return ``True`` when no error-level diagnostic was recorded."""

        return not self.diagnostics.has_errors

    @property
    def severity(self) -> Severity:
        """Return the worst severity recorded."""

        return self.diagnostics.worst

    def map(self, function: Callable[[T], U]) -> "Outcome[U]":
        """Apply ``function`` to the value, carrying diagnostics across."""

        return Outcome(function(self.value), self.diagnostics)

    def absorb(self, other: "Outcome[Any]") -> "Outcome[T]":
        """Take another outcome's diagnostics into this one."""

        self.diagnostics.merge(other.diagnostics)
        return self

    def unwrap(self) -> T:
        """Return the value, ignoring diagnostics.

        Named loudly on purpose: reaching for this in library code usually
        means a diagnostic is about to be discarded silently.
        """

        return self.value

    def as_dict(self, render: Callable[[T], Any] | None = None) -> dict[str, Any]:
        """Return a JSON friendly view of value and diagnostics."""

        rendered = render(self.value) if render is not None else self.value
        return {"value": rendered, "diagnostics": self.diagnostics.as_list()}
