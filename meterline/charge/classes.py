"""How a line item is classified for subtotals and reporting."""

from __future__ import annotations

from enum import Enum

__all__ = ["ChargeClass", "ChargeSide"]


class ChargeClass(str, Enum):
    """What kind of charge a line item represents."""

    FIXED = "fixed"
    """A standing charge, quoted per day or per month."""

    ENERGY = "energy"
    """A volumetric charge on consumption."""

    DEMAND = "demand"
    """A charge on a peak rate of consumption."""

    REACTIVE = "reactive"
    """A power-factor or reactive-energy charge."""

    RIDER = "rider"
    """A surcharge expressed as a rate or a percentage of a basis."""

    CREDIT = "credit"
    """A credit for exported energy."""

    MINIMUM = "minimum"
    """The make-up amount that lifts a bill to its minimum."""

    DISCOUNT = "discount"
    """An assistance or programme discount."""

    ADJUSTMENT = "adjustment"
    """A correction to a previously issued bill."""

    TAX = "tax"
    """A tax or a regulatory fee assessed on other charges."""

    @property
    def is_volumetric(self) -> bool:
        """Return ``True`` when the charge scales with a metered quantity."""

        return self in (
            ChargeClass.ENERGY,
            ChargeClass.DEMAND,
            ChargeClass.REACTIVE,
            ChargeClass.CREDIT,
        )

    @property
    def is_taxable_by_default(self) -> bool:
        """Return ``True`` when the class normally enters the tax base."""

        return self is not ChargeClass.TAX

    @property
    def sort_order(self) -> int:
        """Return the order the class appears in on a rendered bill."""

        return _ORDER[self]


_ORDER = {
    ChargeClass.FIXED: 0,
    ChargeClass.ENERGY: 1,
    ChargeClass.DEMAND: 2,
    ChargeClass.REACTIVE: 3,
    ChargeClass.RIDER: 4,
    ChargeClass.CREDIT: 5,
    ChargeClass.MINIMUM: 6,
    ChargeClass.DISCOUNT: 7,
    ChargeClass.ADJUSTMENT: 8,
    ChargeClass.TAX: 9,
}


class ChargeSide(str, Enum):
    """Which side of an unbundled bill a charge belongs to.

    In a deregulated market the delivery and supply halves are billed by
    different companies and a minimum charge usually applies to only one of
    them, so the split has to survive into the line items.
    """

    DELIVERY = "delivery"
    SUPPLY = "supply"
    OTHER = "other"
