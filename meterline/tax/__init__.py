"""Taxes and regulatory fees.

Kept apart from tariffs because they are set by a different body, change on
a different schedule and apply to a base that the tariff does not define.
A utility that folds them into the rate sheet loses the ability to answer
"what would this bill be in the next county", which is the whole point of
having a jurisdiction on the premise.
"""

from __future__ import annotations

from .engine import apply_taxes
from .exemption import Exemption, ExemptionSet
from .jurisdiction import Jurisdiction, JurisdictionSet
from .model import TaxRule, TaxKind

__all__ = [
    "Exemption",
    "ExemptionSet",
    "Jurisdiction",
    "JurisdictionSet",
    "TaxKind",
    "TaxRule",
    "apply_taxes",
]
