"""Argument parsing."""

from __future__ import annotations

import argparse

from ..policy.presets import preset_names
from ..version import VERSION

__all__ = ["build_parser"]


def _add_dataset(parser: argparse.ArgumentParser) -> None:
    """Add the options every dataset-reading command shares."""

    parser.add_argument(
        "--dataset",
        required=True,
        metavar="PATH",
        help="path to the dataset JSON file",
    )
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="override the dataset's conventions with a named preset "
        f"({', '.join(preset_names())})",
    )


def _add_selection(parser: argparse.ArgumentParser) -> None:
    """Add the options that narrow which bills are produced."""

    parser.add_argument(
        "--service-point",
        metavar="ID",
        action="append",
        default=[],
        help="restrict to one service point; repeatable",
    )
    parser.add_argument(
        "--as-of",
        metavar="DATE",
        help="ignore cycles that end after this local date (YYYY-MM-DD)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the top-level argument parser."""

    parser = argparse.ArgumentParser(
        prog="meterline",
        description="A deterministic utility metering and tariff rating engine.",
    )
    parser.add_argument(
        "--version", action="version", version=f"meterline {VERSION}"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    version = subparsers.add_parser("version", help="print the engine version")
    version.set_defaults(handler="version")

    validate = subparsers.add_parser(
        "validate", help="check a dataset and its tariffs without billing"
    )
    _add_dataset(validate)
    validate.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on warnings as well as errors",
    )
    validate.set_defaults(handler="validate")

    rate = subparsers.add_parser("rate", help="produce bills from a dataset")
    _add_dataset(rate)
    _add_selection(rate)
    rate.add_argument("--out", metavar="PATH", help="write the output to a file")
    rate.add_argument(
        "--format",
        choices=("text", "json", "csv"),
        default="text",
        help="output format (default: text)",
    )
    rate.set_defaults(handler="rate")

    explain = subparsers.add_parser(
        "explain", help="show every line of a bill with its working"
    )
    _add_dataset(explain)
    _add_selection(explain)
    explain.add_argument("--cycle", metavar="ID", help="explain one cycle by id")
    explain.add_argument("--line", metavar="CODE", help="explain one line item only")
    explain.add_argument("--out", metavar="PATH", help="write the output to a file")
    explain.set_defaults(handler="explain")

    meters = subparsers.add_parser(
        "meters", help="show meter reads, derived consumption and gaps"
    )
    _add_dataset(meters)
    _add_selection(meters)
    meters.add_argument(
        "--intervals", action="store_true", help="include interval data"
    )
    meters.add_argument(
        "--format", choices=("text", "csv"), default="text", help="output format"
    )
    meters.set_defaults(handler="meters")

    tariff = subparsers.add_parser("tariff", help="describe and check tariffs")
    _add_dataset(tariff)
    tariff.add_argument("--code", metavar="CODE", help="describe one tariff")
    tariff.set_defaults(handler="tariff")

    policy = subparsers.add_parser(
        "policy", help="show the conventions in force and what they mean"
    )
    policy.add_argument("--dataset", metavar="PATH", help="read the profile from a dataset")
    policy.add_argument("--profile", metavar="NAME", help="show a named preset")
    policy.add_argument(
        "--list", action="store_true", dest="list_presets", help="list the presets"
    )
    policy.add_argument(
        "--diff", metavar="NAME", help="compare against another preset"
    )
    policy.set_defaults(handler="policy")

    replay = subparsers.add_parser(
        "replay", help="rate a dataset several times and check the results match"
    )
    _add_dataset(replay)
    _add_selection(replay)
    replay.add_argument(
        "--passes", type=int, default=3, metavar="N", help="how many times to rate"
    )
    replay.set_defaults(handler="replay")

    compare = subparsers.add_parser(
        "compare", help="rate a dataset under two profiles and show the difference"
    )
    _add_dataset(compare)
    _add_selection(compare)
    compare.add_argument(
        "--against", metavar="NAME", help="the profile to compare against"
    )
    compare.add_argument("--out", metavar="PATH", help="write the output to a file")
    compare.set_defaults(handler="compare")

    export = subparsers.add_parser(
        "export", help="write a dataset back out as canonical JSON"
    )
    _add_dataset(export)
    export.add_argument("--out", metavar="PATH", help="write the output to a file")
    export.set_defaults(handler="export")

    return parser
