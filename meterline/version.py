"""Version metadata for the package.

The version is kept in one place so that the CLI, the audit journal and the
packaging metadata cannot drift apart.  Every artefact the engine writes
carries this string, because a bill that cannot be traced back to the code
that produced it is not reproducible in any useful sense.
"""

from __future__ import annotations

VERSION = "0.12.0"
"""Human readable version of the engine."""

VERSION_INFO = (0, 12, 0)
"""Machine comparable version tuple."""

ENGINE_NAME = "meterline"
"""Name written into audit journals and rendered documents."""


def version_string() -> str:
    """Return the ``name/version`` string stamped onto generated output."""

    return f"{ENGINE_NAME}/{VERSION}"


def at_least(major: int, minor: int = 0, patch: int = 0) -> bool:
    """Return ``True`` when the running engine is at least the given version.

    Dataset files may declare the minimum engine they were written for; the
    loader uses this to refuse a file it would silently misread.
    """

    return VERSION_INFO >= (major, minor, patch)
