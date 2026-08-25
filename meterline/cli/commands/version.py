"""The ``version`` command."""

from __future__ import annotations

import argparse
import platform

from ...version import ENGINE_NAME, VERSION, version_string
from ..render import EXIT_OK, emit

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Print the engine version and the interpreter it is running on."""

    del args
    lines = [
        version_string(),
        f"engine     {ENGINE_NAME} {VERSION}",
        f"python     {platform.python_version()}",
        "runtime    standard library only, no runtime dependencies",
    ]
    emit("\n".join(lines))
    return EXIT_OK
