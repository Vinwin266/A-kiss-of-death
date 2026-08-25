"""Policy: the conventions a utility has chosen.

This package is the heart of the repository.  Almost every number the engine
produces depends on a choice that is defensible either way and that real
utilities make differently — how a partial month is prorated, whether a
tier threshold shrinks with the cycle, what happens to an export credit
that is never used.  Those choices are gathered into one explicit,
serialisable :class:`~meterline.policy.profile.UtilityProfile` rather than
being scattered through the rating code as defaults.

The test for whether something belongs here is simple: if two competent
implementations of the same rate sheet could disagree about it, it is a
convention and it goes in the profile.
"""

from __future__ import annotations

from .conventions import (
    AssistanceStage,
    BankExpiry,
    CashOutPolicy,
    CreditValuation,
    DemandMethod,
    EstimationStrategy,
    GapPolicy,
    MinimumBasis,
    NegativeBillPolicy,
    NettingGranularity,
    ProrationBasis,
    RatchetBasis,
    RolloverPolicy,
    RoundingStage,
    SuspectDataPolicy,
    TaxCompounding,
    TierBasis,
    TrueUpPolicy,
    WindowPrecedence,
)
from .presets import PRESETS, preset
from .profile import UtilityProfile

__all__ = [
    "AssistanceStage",
    "BankExpiry",
    "CashOutPolicy",
    "CreditValuation",
    "DemandMethod",
    "EstimationStrategy",
    "GapPolicy",
    "MinimumBasis",
    "NegativeBillPolicy",
    "NettingGranularity",
    "PRESETS",
    "ProrationBasis",
    "RatchetBasis",
    "RolloverPolicy",
    "RoundingStage",
    "SuspectDataPolicy",
    "TaxCompounding",
    "TierBasis",
    "TrueUpPolicy",
    "UtilityProfile",
    "WindowPrecedence",
    "preset",
]
