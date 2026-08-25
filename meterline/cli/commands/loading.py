"""Shared dataset loading for the commands that need one."""

from __future__ import annotations

import argparse

from ...dataset import Dataset
from ...io.files import load_dataset
from ...policy.presets import preset
from ...policy.profile import UtilityProfile
from ...session import Session

__all__ = ["open_session", "selected_points"]


def open_session(args: argparse.Namespace) -> Session:
    """Load the dataset named on the command line and start a session."""

    dataset: Dataset = load_dataset(args.dataset)
    profile: UtilityProfile | None = None
    if getattr(args, "profile", None):
        profile = preset(args.profile)
    return Session.of(dataset, profile)


def selected_points(session: Session, args: argparse.Namespace) -> list[str]:
    """Return the service points a command should act on."""

    wanted = list(getattr(args, "service_point", []) or [])
    if not wanted:
        return session.service_point_ids()
    return sorted(wanted)
