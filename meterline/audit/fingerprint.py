"""Fingerprints of the inputs a run depended on.

A fingerprint is a content hash, not a timestamp or a version number.  Two
runs that agree on every fingerprint must produce the same bills; if they do
not, the difference is in the engine and the journal says exactly which
input to rule out.
"""

from __future__ import annotations

from typing import Any

from ..core.ids import digest_of, short_digest
from ..dataset import Dataset
from ..policy.profile import UtilityProfile
from ..tariff.model import Tariff

__all__ = [
    "profile_fingerprint",
    "tariff_fingerprint",
    "dataset_fingerprint",
    "document_fingerprint",
]


def profile_fingerprint(profile: UtilityProfile, *, length: int = 12) -> str:
    """Return a fingerprint of every convention in a profile."""

    return short_digest(profile.as_dict(), length=length)


def tariff_fingerprint(tariff: Tariff, *, length: int = 12) -> str:
    """Return a fingerprint of a tariff's full configuration."""

    return short_digest(tariff.as_dict(), length=length)


def dataset_fingerprint(dataset: Dataset, *, length: int = 16) -> str:
    """Return a fingerprint of the records a dataset holds.

    Deliberately built from the identifying content rather than from the
    file: the same dataset assembled in memory and read from disk must
    fingerprint identically, or the tests and the CLI are not exercising the
    same thing.
    """

    parts: list[Any] = [
        dataset.name,
        profile_fingerprint(dataset.profile),
        sorted(dataset.accounts),
        sorted(dataset.premises),
        sorted(dataset.service_points),
        sorted(dataset.meters),
        [read.read_id for read in dataset.reads],
        [change.change_id for change in dataset.changes],
        sorted(dataset.series),
        {
            code: tariff_fingerprint(dataset.catalog.schedules[code].versions[-1].tariff)
            for code in dataset.catalog.codes()
        },
        sorted(dataset.jurisdictions.codes()),
    ]
    return short_digest(parts, length=length)


def document_fingerprint(document: Any, *, length: int = 16) -> str:
    """Return a fingerprint of any JSON-shaped document."""

    return digest_of(document)[:length]
