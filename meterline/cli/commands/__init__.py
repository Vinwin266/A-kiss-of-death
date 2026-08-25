"""One module per command.

Each exposes ``run(args)`` returning a process exit code.  Nothing here
raises for an expected condition: an unreadable dataset or an unknown tariff
is an error message and a non-zero code, not a traceback.
"""

from __future__ import annotations

from . import (
    compare,
    explain,
    export,
    meters,
    policy,
    rate,
    replay,
    tariff,
    validate,
    version,
)

HANDLERS = {
    "compare": compare.run,
    "explain": explain.run,
    "export": export.run,
    "meters": meters.run,
    "policy": policy.run,
    "rate": rate.run,
    "replay": replay.run,
    "tariff": tariff.run,
    "validate": validate.run,
    "version": version.run,
}

__all__ = ["HANDLERS"]
