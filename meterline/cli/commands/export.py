"""The ``export`` command."""

from __future__ import annotations

import argparse

from ...errors import MeterlineError
from ...io.encode import dataset_to_dict
from ..render import EXIT_OK, emit_json, fail
from .loading import open_session

__all__ = ["run"]


def run(args: argparse.Namespace) -> int:
    """Write a dataset back out as canonical JSON.

    Useful on its own, and used by the round-trip test: a dataset that does
    not survive export and re-import has a field the decoder is dropping.
    """

    try:
        session = open_session(args)
    except MeterlineError as error:
        return fail(error)
    emit_json(dataset_to_dict(session.dataset), args.out)
    return EXIT_OK
