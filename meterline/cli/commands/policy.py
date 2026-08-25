"""The ``policy`` command."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...io.files import load_dataset
from ...policy.describe import profile_highlights, profile_table
from ...policy.presets import PRESETS, preset, preset_names
from ...policy.profile import UtilityProfile
from ..render import EXIT_OK, EXIT_USAGE, emit, fail

__all__ = ["run"]


def _resolve(args: argparse.Namespace) -> UtilityProfile:
    """Return the profile the user asked about."""

    if args.profile:
        return preset(args.profile)
    if args.dataset:
        return load_dataset(args.dataset).profile
    return UtilityProfile()


def _diff(left: UtilityProfile, right: UtilityProfile) -> str:
    """Render the settings on which two profiles disagree."""

    left_values = left.as_dict()
    right_values = right.as_dict()
    rows = []
    for key in sorted(left_values):
        if key in ("name", "description"):
            continue
        if left_values[key] != right_values.get(key):
            rows.append((key, str(left_values[key]), str(right_values.get(key))))
    if not rows:
        return f"{left.name} and {right.name} agree on every convention"
    width = max(len(key) for key, _, _ in rows)
    lines = [f"{left.name} vs {right.name}", ""]
    for key, mine, theirs in rows:
        lines.append(f"  {key.ljust(width)}  {mine}  ->  {theirs}")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Show a profile, list the presets, or diff two profiles."""

    if args.list_presets:
        lines = []
        for name in preset_names():
            profile = PRESETS[name]
            lines.append(f"{name}")
            if profile.description:
                lines.append(f"    {profile.description}")
        emit("\n".join(lines))
        return EXIT_OK

    try:
        profile = _resolve(args)
        if args.diff:
            emit(_diff(profile, preset(args.diff)))
            return EXIT_OK
    except MeterlineError as error:
        return fail(error)

    if not args.profile and not args.dataset:
        emit("give --profile NAME, --dataset PATH or --list")
        return EXIT_USAGE

    blocks = [profile_table(profile).to_text(), "", "in short:"]
    blocks.extend(f"  - {line}" for line in profile_highlights(profile))
    emit("\n".join(blocks))
    return EXIT_OK
