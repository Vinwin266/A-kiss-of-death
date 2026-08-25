"""Operator edits, and the record they leave behind.

The "E" of VEE that is not estimation.  An edit replaces a measured value
with a corrected one, and the only thing that makes it defensible is that
the original survives next to it with a reason attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from ..core.decimals import D
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.ids import stable_id
from ..core.quantity import Quantity
from ..model.quality import QualityCode
from ..timeline.instants import ensure_utc, format_instant
from ..timeline.spans import Span
from .consumption import Consumption

__all__ = ["EditRecord", "apply_edits"]


@dataclass(frozen=True, slots=True)
class EditRecord:
    """One operator correction to a period of consumption."""

    edit_id: str
    subject: str
    """The register or channel the edit applies to."""

    span: Span
    value: Decimal
    reason: str
    operator: str = ""
    recorded_at: datetime | None = None
    quality: QualityCode = QualityCode.EDITED

    @classmethod
    def build(
        cls,
        subject: str,
        span: Span,
        value: Decimal | str | int,
        reason: str,
        operator: str = "",
        recorded_at: datetime | None = None,
    ) -> "EditRecord":
        """Build an edit with a deterministic identifier."""

        moment = ensure_utc(recorded_at) if recorded_at is not None else None
        edit_id = stable_id(
            "edit", subject, span.start.isoformat(), span.end.isoformat(), str(D(value))
        )
        return cls(edit_id, subject, span, D(value), reason, operator, moment)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        when = format_instant(self.recorded_at) if self.recorded_at else "undated"
        who = self.operator or "unattributed"
        return f"{self.span.describe()} -> {self.value} ({self.reason}, {who}, {when})"


def apply_edits(
    records: Sequence[Consumption],
    edits: Sequence[EditRecord],
    *,
    subject: str = "",
) -> tuple[list[Consumption], DiagnosticBag]:
    """Return the records with edits applied, plus a diagnostic for each.

    An edit replaces every record it fully covers and is ignored where it
    only partially overlaps: splitting a measured interval to fit an edit
    would invent two values from one, and the operator who made the edit is
    better placed to say which half was wrong.
    """

    bag = DiagnosticBag()
    if not edits:
        return list(records), bag
    result: list[Consumption] = []
    applied: set[str] = set()
    for record in records:
        replacement: EditRecord | None = None
        for edit in edits:
            if edit.subject not in ("", record.register_id, subject):
                continue
            if edit.span.contains_span(record.span):
                replacement = edit
        if replacement is None:
            result.append(record)
            continue
        applied.add(replacement.edit_id)
        share = D(record.span.seconds) / D(replacement.span.seconds)
        bag.emit(
            "meterdata.edit.applied",
            "an operator edit replaced measured usage",
            Severity.NOTICE,
            record.register_id or subject,
            edit=replacement.edit_id,
            reason=replacement.reason,
            original=str(record.quantity.value),
        )
        result.append(
            Consumption(
                record.span,
                Quantity(replacement.value * share, record.unit),
                replacement.quality,
                record.register_id,
                "edit",
                replacement.reason,
            )
        )
    for edit in edits:
        if edit.edit_id not in applied:
            bag.emit(
                "meterdata.edit.unapplied",
                "an edit matched no whole record and was ignored",
                Severity.WARNING,
                edit.subject or subject,
                edit=edit.edit_id,
                span=edit.span.describe(),
            )
    return result, bag
