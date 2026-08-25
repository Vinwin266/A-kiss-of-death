"""The entry point."""

from __future__ import annotations

import sys
from typing import Sequence

from ..errors import MeterlineError
from .args import build_parser
from .commands import HANDLERS
from .render import EXIT_OK, EXIT_USAGE, fail

__all__ = ["main", "run"]


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, dispatch to a command and return an exit code."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler_name = getattr(args, "handler", "")
    if not handler_name:
        parser.print_help()
        return EXIT_OK
    handler = HANDLERS.get(handler_name)
    if handler is None:  # pragma: no cover - guarded by argparse
        parser.error(f"unknown command {handler_name}")
        return EXIT_USAGE
    try:
        return handler(args)
    except MeterlineError as error:
        return fail(error)
    except BrokenPipeError:  # pragma: no cover - depends on the shell
        return EXIT_OK


def run() -> None:
    """Console-script entry point."""

    sys.exit(main())
