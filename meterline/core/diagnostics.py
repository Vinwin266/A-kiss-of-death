"""Structured diagnostics.

The engine almost never raises for bad *data* — only for bad *code paths*.
A meter read that fails validation, a tariff component that had nothing to
bill, a gap that had to be estimated: these are ordinary outcomes that belong
on the bill's record, not in a traceback.  They are collected here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator

__all__ = ["Severity", "Diagnostic", "DiagnosticBag"]


class Severity(str, Enum):
    """How much a diagnostic should worry the reader."""

    INFO = "info"
    """Something worth recording; the result is unaffected."""

    NOTICE = "notice"
    """A convention was applied that a reader might not expect."""

    WARNING = "warning"
    """The result is usable but rests on an assumption, e.g. an estimate."""

    ERROR = "error"
    """The result is not fit to bill from."""

    @property
    def rank(self) -> int:
        """Return an orderable rank; higher is more severe."""

        return _RANKS[self]

    def __lt__(self, other: "Severity") -> bool:  # type: ignore[override]
        return self.rank < other.rank


_RANKS = {
    Severity.INFO: 0,
    Severity.NOTICE: 1,
    Severity.WARNING: 2,
    Severity.ERROR: 3,
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One thing worth telling the reader about a computation."""

    code: str
    """A stable dotted identifier, safe to branch on."""

    message: str
    """A one-line human explanation."""

    severity: Severity = Severity.INFO
    subject: str = ""
    """Identifier of the record the diagnostic is about, if any."""

    context: tuple[tuple[str, str], ...] = ()
    """Sorted key/value detail, kept as strings so it always serialises."""

    @classmethod
    def make(
        cls,
        code: str,
        message: str,
        severity: Severity = Severity.INFO,
        subject: str = "",
        **context: Any,
    ) -> "Diagnostic":
        """Build a diagnostic with keyword context."""

        rendered = tuple(sorted((key, str(value)) for key, value in context.items()))
        return cls(code, message, severity, subject, rendered)

    @property
    def sort_key(self) -> tuple[int, str, str]:
        """Return a deterministic ordering key (most severe first)."""

        return (-self.severity.rank, self.code, self.subject)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view."""

        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "subject": self.subject,
            "context": dict(self.context),
        }

    def render(self) -> str:
        """Render as a single line for the CLI."""

        head = f"[{self.severity.value:>7}] {self.code}"
        if self.subject:
            head = f"{head} ({self.subject})"
        return f"{head}: {self.message}"


@dataclass(slots=True)
class DiagnosticBag:
    """An append-only, order-preserving collection of diagnostics."""

    items: list[Diagnostic] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        """Append one diagnostic."""

        self.items.append(diagnostic)

    def emit(
        self,
        code: str,
        message: str,
        severity: Severity = Severity.INFO,
        subject: str = "",
        **context: Any,
    ) -> None:
        """Build and append a diagnostic in one call."""

        self.add(Diagnostic.make(code, message, severity, subject, **context))

    def extend(self, diagnostics: Iterable[Diagnostic]) -> None:
        """Append many diagnostics."""

        self.items.extend(diagnostics)

    def merge(self, other: "DiagnosticBag") -> None:
        """Absorb another bag's contents."""

        self.items.extend(other.items)

    def of_severity(self, severity: Severity) -> list[Diagnostic]:
        """Return every diagnostic at exactly ``severity``."""

        return [item for item in self.items if item.severity is severity]

    def at_least(self, severity: Severity) -> list[Diagnostic]:
        """Return every diagnostic at or above ``severity``."""

        return [item for item in self.items if item.severity.rank >= severity.rank]

    @property
    def errors(self) -> list[Diagnostic]:
        """Return the error-level diagnostics."""

        return self.of_severity(Severity.ERROR)

    @property
    def warnings(self) -> list[Diagnostic]:
        """Return the warning-level diagnostics."""

        return self.of_severity(Severity.WARNING)

    @property
    def has_errors(self) -> bool:
        """Return ``True`` when anything error-level was recorded."""

        return any(item.severity is Severity.ERROR for item in self.items)

    @property
    def worst(self) -> Severity:
        """Return the highest severity present, or ``INFO`` when empty."""

        if not self.items:
            return Severity.INFO
        return max((item.severity for item in self.items), key=lambda s: s.rank)

    def sorted_items(self) -> list[Diagnostic]:
        """Return the diagnostics in a stable, severity-first order."""

        return sorted(self.items, key=lambda item: item.sort_key)

    def codes(self) -> list[str]:
        """Return the distinct codes present, sorted."""

        return sorted({item.code for item in self.items})

    def as_list(self) -> list[dict[str, Any]]:
        """Return a JSON friendly view in insertion order."""

        return [item.as_dict() for item in self.items]

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)
