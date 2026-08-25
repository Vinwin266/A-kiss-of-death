"""The priced pieces a tariff is assembled from.

Each component answers one question — "what does the standing charge come
to?", "what do the first 500 kWh cost?" — and returns line items.  They are
evaluated in stage order so that a component needing the subtotal so far,
such as a minimum charge, sees a complete picture.
"""

from __future__ import annotations

from .base import Component, Stage
from .blocks import Block, allocate_blocks
from .credit import ExportCredit
from .demand import DemandCharge
from .discount import AssistanceDiscount
from .fixed import FixedCharge
from .minimum import MinimumCharge
from .reactive import PowerFactorCharge
from .rider import Rider, RiderKind
from .step import SteppedCharge
from .tiered import TieredCharge
from .tou import TouCharge

__all__ = [
    "AssistanceDiscount",
    "Block",
    "allocate_blocks",
    "Component",
    "DemandCharge",
    "ExportCredit",
    "FixedCharge",
    "MinimumCharge",
    "PowerFactorCharge",
    "Rider",
    "RiderKind",
    "Stage",
    "SteppedCharge",
    "TieredCharge",
    "TouCharge",
]
