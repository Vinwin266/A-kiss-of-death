"""Building a :class:`UtilityProfile` from plain data.

Datasets carry profiles as JSON objects.  Decoding is explicit rather than
reflective: each field is listed with the enum it belongs to, so an unknown
convention name produces a readable error naming the alternatives instead of
a :class:`TypeError` three frames deep.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable, Mapping

from ..core.rounding import RoundingMode
from ..errors import PolicyError
from ..model.enrollment import EnrollmentResolution
from ..model.quality import QualityMergeRule
from ..timeline.daycount import DayCount
from ..timeline.daytypes import DayTypeRules
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
from .presets import preset
from .profile import UtilityProfile

__all__ = ["profile_from_dict", "profile_overrides", "ENUM_FIELDS"]


ENUM_FIELDS: dict[str, type] = {
    "rounding_mode": RoundingMode,
    "rounding_stage": RoundingStage,
    "negative_bill": NegativeBillPolicy,
    "day_count": DayCount,
    "proration": ProrationBasis,
    "tier_basis": TierBasis,
    "enrollment_resolution": EnrollmentResolution,
    "window_precedence": WindowPrecedence,
    "rollover": RolloverPolicy,
    "gaps": GapPolicy,
    "estimation": EstimationStrategy,
    "suspect_data": SuspectDataPolicy,
    "quality_merge": QualityMergeRule,
    "true_up": TrueUpPolicy,
    "demand_method": DemandMethod,
    "ratchet": RatchetBasis,
    "minimum_basis": MinimumBasis,
    "assistance_stage": AssistanceStage,
    "tax_compounding": TaxCompounding,
    "netting": NettingGranularity,
    "credit_valuation": CreditValuation,
    "bank_expiry": BankExpiry,
    "cash_out": CashOutPolicy,
}

_INT_FIELDS = {
    "money_places",
    "estimation_lookback_cycles",
    "zero_usage_days",
    "demand_window_minutes",
    "ratchet_lookback_months",
    "bank_rolling_months",
    "true_up_month",
}


def _coerce_enum(name: str, value: Any) -> Any:
    """Turn a string into the enum member the field expects."""

    enum_type = ENUM_FIELDS[name]
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except ValueError:
        options = ", ".join(sorted(member.value for member in enum_type))
        raise PolicyError(
            "unknown convention value",
            field=name,
            value=str(value),
            options=options,
        ) from None


def _coerce_day_types(value: Any) -> DayTypeRules:
    """Build :class:`DayTypeRules` from a mapping of booleans."""

    if isinstance(value, DayTypeRules):
        return value
    if not isinstance(value, Mapping):
        raise PolicyError("day_types must be an object", value=str(value))
    known = {
        "saturday_is_weekend",
        "sunday_is_weekend",
        "holidays_are_distinct",
        "holiday_wins_over_weekend",
    }
    unknown = sorted(set(value) - known)
    if unknown:
        raise PolicyError("unknown day-type settings", fields=", ".join(unknown))
    return DayTypeRules(**{key: bool(value[key]) for key in value})


def _converter(name: str) -> Callable[[Any], Any]:
    """Return the converter for one profile field."""

    if name in ENUM_FIELDS:
        return lambda value: _coerce_enum(name, value)
    if name == "day_types":
        return _coerce_day_types
    if name in _INT_FIELDS:
        return int
    return str


def profile_overrides(data: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a mapping of raw values into profile keyword arguments."""

    known = {field.name for field in fields(UtilityProfile)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise PolicyError(
            "unknown profile fields",
            fields=", ".join(unknown),
            known=", ".join(sorted(known)),
        )
    return {name: _converter(name)(data[name]) for name in sorted(data)}


def profile_from_dict(data: Mapping[str, Any]) -> UtilityProfile:
    """Build a profile from a mapping, optionally extending a preset.

    A ``base`` key names a preset to start from; everything else overrides
    it.  Naming a base is the recommended form, because a profile written
    from scratch silently inherits this module's defaults for anything it
    forgets to mention.
    """

    payload = dict(data)
    base_name = payload.pop("base", None)
    base = preset(str(base_name)) if base_name else UtilityProfile()
    overrides = profile_overrides(payload)
    return base.with_changes(**overrides)
