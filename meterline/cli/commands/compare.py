"""The ``compare`` command: the same data under two sets of conventions."""

from __future__ import annotations

import argparse

from ...core.money import Money
from ...core.tables import Column, Table
from ...errors import MeterlineError
from ...policy.describe import explain_convention
from ...policy.presets import preset
from ...rating.invoice import Invoice
from ...session import Session
from ..render import EXIT_OK, emit, fail, parse_as_of
from .loading import open_session, selected_points

__all__ = ["run"]


def _index(invoices: list[Invoice]) -> dict[str, Invoice]:
    """Key bills by service point and period so two runs can be aligned."""

    return {
        f"{invoice.service_point_id}|{invoice.span.start.isoformat()}": invoice
        for invoice in invoices
    }


def _differences(profile_a, profile_b) -> list[str]:  # noqa: ANN001
    """Return one line per convention the two profiles disagree on."""

    left = profile_a.as_dict()
    right = profile_b.as_dict()
    lines: list[str] = []
    for key in sorted(left):
        if key in ("name", "description") or left[key] == right.get(key):
            continue
        meaning = explain_convention(getattr(profile_b, key))
        suffix = f" — {meaning}" if meaning else ""
        lines.append(f"{key}: {left[key]} -> {right.get(key)}{suffix}")
    return lines


def run(args: argparse.Namespace) -> int:
    """Rate a dataset twice and show what the conventions changed."""

    try:
        session = open_session(args)
        as_of = parse_as_of(args.as_of)
        points = selected_points(session, args)
        first = session.rate_all(as_of=as_of, service_point_ids=points).value
        other_profile = preset(args.against) if args.against else session.dataset.profile
        second_session = Session.of(session.dataset, other_profile)
        second = second_session.rate_all(as_of=as_of, service_point_ids=points).value
    except MeterlineError as error:
        return fail(error)

    left_index = _index(first)
    right_index = _index(second)
    currency = first[0].currency if first else "USD"

    table = Table(
        (
            Column("service_point", "service point"),
            Column("period", "period"),
            Column("left", session.active_profile.name, align="right"),
            Column("right", other_profile.name, align="right"),
            Column("delta", "difference", align="right"),
        )
    )
    total_delta = Money.zero(currency)
    for key in sorted(set(left_index) | set(right_index)):
        left = left_index.get(key)
        right = right_index.get(key)
        left_total = left.total if left else Money.zero(currency)
        right_total = right.total if right else Money.zero(currency)
        delta = right_total - left_total
        total_delta = total_delta + delta
        reference = left or right
        assert reference is not None
        table.add(
            service_point=reference.service_point_id,
            period=reference.span.start.date().isoformat(),
            left=left_total.format(),
            right=right_total.format(),
            delta=delta.format(),
        )

    blocks = [table.to_text(), "", f"net difference: {total_delta.format()} {currency}"]
    conventions = _differences(session.active_profile, other_profile)
    if conventions:
        blocks.append("")
        blocks.append("conventions that changed:")
        blocks.extend(f"  - {line}" for line in conventions)
    emit("\n".join(blocks), args.out)
    return EXIT_OK
