"""The record types the engine reads.

These are plain, frozen data classes with no behaviour beyond lookups and
invariants.  Anything that computes a number lives in :mod:`meterline.meterdata`
or :mod:`meterline.rating`; keeping the records inert is what lets a dataset
be loaded, inspected and re-serialised without the engine having run.
"""

from __future__ import annotations

from .account import Account, AccountStatus
from .channel import ChannelKind, ChannelSpec
from .enrollment import EnrollmentHistory, TariffEnrollment
from .meter import Meter, MeterKind
from .premise import Premise
from .quality import QualityCode, QualityMergeRule, ReadType, merge_quality
from .reading import MeterRead, RegisterChange
from .register import Register
from .series import IntervalSeries, SeriesPoint
from .service_point import ServiceKind, ServicePoint

__all__ = [
    "Account",
    "AccountStatus",
    "ChannelKind",
    "ChannelSpec",
    "EnrollmentHistory",
    "Meter",
    "MeterKind",
    "MeterRead",
    "Premise",
    "QualityCode",
    "QualityMergeRule",
    "ReadType",
    "IntervalSeries",
    "Register",
    "SeriesPoint",
    "RegisterChange",
    "ServiceKind",
    "ServicePoint",
    "TariffEnrollment",
    "merge_quality",
]
