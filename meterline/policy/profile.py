"""The utility profile: every convention in one place."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from decimal import Decimal
from typing import Any

from ..constants import DEFAULT_CURRENCY, RATCHET_LOOKBACK_MONTHS
from ..core.decimals import D
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

__all__ = ["UtilityProfile"]


@dataclass(frozen=True, slots=True)
class UtilityProfile:
    """A named, complete set of billing conventions.

    Every field has a default, and the defaults are not neutral: they encode
    one plausible utility.  A profile is meant to be *stated*, not inherited
    by accident, so :meth:`describe` renders the whole thing and the audit
    journal records its fingerprint alongside every bill.
    """

    name: str = "default"
    description: str = ""
    currency: str = DEFAULT_CURRENCY

    # -- money ----------------------------------------------------------
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    rounding_stage: RoundingStage = RoundingStage.PER_LINE
    money_places: int = 2
    total_increment: str = "0"
    """Snap the final total to this increment; ``0`` disables snapping."""

    negative_bill: NegativeBillPolicy = NegativeBillPolicy.CARRY_FORWARD

    # -- calendar -------------------------------------------------------
    day_count: DayCount = DayCount.ACTUAL
    day_types: DayTypeRules = DayTypeRules()
    holiday_calendar: str = "us-tariff"

    # -- periods --------------------------------------------------------
    proration: ProrationBasis = ProrationBasis.DAILY_ACTUAL
    tier_basis: TierBasis = TierBasis.CYCLE
    enrollment_resolution: EnrollmentResolution = EnrollmentResolution.SPLIT
    window_precedence: WindowPrecedence = WindowPrecedence.MOST_SPECIFIC

    # -- meter data -----------------------------------------------------
    rollover: RolloverPolicy = RolloverPolicy.THRESHOLD
    rollover_threshold_factor: str = "0.5"
    """Fraction of a dial width below which a wrap is accepted as a rollover."""

    gaps: GapPolicy = GapPolicy.ESTIMATE
    estimation: EstimationStrategy = EstimationStrategy.TRAILING_AVERAGE
    estimation_lookback_cycles: int = 3
    suspect_data: SuspectDataPolicy = SuspectDataPolicy.BILL_ANYWAY
    quality_merge: QualityMergeRule = QualityMergeRule.WORST_WINS
    true_up: TrueUpPolicy = TrueUpPolicy.NEXT_ACTUAL

    # -- validation limits ----------------------------------------------
    spike_factor: str = "4"
    """A cycle above this multiple of the trailing average is suspect."""

    zero_usage_days: int = 45
    """Consecutive zero days after which a meter is flagged as stopped."""

    interval_sum_tolerance: str = "0.02"
    """Allowed relative gap between interval totals and register deltas."""

    # -- demand ---------------------------------------------------------
    demand_method: DemandMethod = DemandMethod.BLOCK
    demand_window_minutes: int = 15
    demand_increment: str = "0"
    ratchet: RatchetBasis = RatchetBasis.NONE
    ratchet_percent: str = "60"
    ratchet_lookback_months: int = RATCHET_LOOKBACK_MONTHS

    # -- charges --------------------------------------------------------
    minimum_basis: MinimumBasis = MinimumBasis.ENERGY_AND_FIXED
    assistance_stage: AssistanceStage = AssistanceStage.PRE_TAX
    tax_compounding: TaxCompounding = TaxCompounding.PARALLEL

    # -- net metering ---------------------------------------------------
    netting: NettingGranularity = NettingGranularity.CYCLE
    credit_valuation: CreditValuation = CreditValuation.RETAIL
    credit_percent_of_retail: str = "100"
    bank_expiry: BankExpiry = BankExpiry.ANNUAL_TRUE_UP
    bank_rolling_months: int = 12
    true_up_month: int = 4
    cash_out: CashOutPolicy = CashOutPolicy.NONE

    def __post_init__(self) -> None:
        if self.money_places < 0 or self.money_places > 6:
            raise PolicyError("money places out of range", places=self.money_places)
        if not 1 <= self.true_up_month <= 12:
            raise PolicyError("true-up month out of range", month=self.true_up_month)
        if D(self.rollover_threshold_factor) <= 0:
            raise PolicyError("rollover threshold must be positive")
        if self.estimation_lookback_cycles < 1:
            raise PolicyError("estimation lookback must be at least one cycle")
        if self.demand_window_minutes <= 0:
            raise PolicyError("demand window must be positive")
        if (
            self.netting is not NettingGranularity.CYCLE
            and self.credit_valuation is CreditValuation.RETAIL
        ):
            # Sub-cycle netting with a retail credit is not the same thing as
            # cycle netting and is not implemented; refuse rather than
            # silently produce cycle-netted numbers under another name.
            raise PolicyError(
                "sub-cycle netting is not implemented for retail-valued credits",
                netting=self.netting.value,
            )

    # -- derived values -------------------------------------------------

    @property
    def spike_multiple(self) -> Decimal:
        """Return the spike factor as a decimal."""

        return D(self.spike_factor)

    @property
    def ratchet_fraction(self) -> Decimal:
        """Return the ratchet percentage as a fraction of one."""

        return D(self.ratchet_percent) / D(100)

    @property
    def credit_fraction(self) -> Decimal:
        """Return the export credit percentage as a fraction of one."""

        return D(self.credit_percent_of_retail) / D(100)

    @property
    def rollover_threshold(self) -> Decimal:
        """Return the rollover acceptance threshold as a fraction of one."""

        return D(self.rollover_threshold_factor)

    @property
    def rounds_each_line(self) -> bool:
        """Return ``True`` when line items are rounded individually."""

        return self.rounding_stage is RoundingStage.PER_LINE

    @property
    def banks_credits(self) -> bool:
        """Return ``True`` when unused credits survive to the next cycle."""

        return self.bank_expiry is not BankExpiry.NEVER or True

    # -- manipulation ---------------------------------------------------

    def with_changes(self, **changes: Any) -> "UtilityProfile":
        """Return a copy with the given fields replaced."""

        unknown = sorted(set(changes) - {field.name for field in fields(self)})
        if unknown:
            raise PolicyError("unknown profile fields", fields=", ".join(unknown))
        return replace(self, **changes)

    def field_names(self) -> list[str]:
        """Return every field name, in declaration order."""

        return [field.name for field in fields(self)]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the profile."""

        result: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, DayTypeRules):
                result[field.name] = {
                    "saturday_is_weekend": value.saturday_is_weekend,
                    "sunday_is_weekend": value.sunday_is_weekend,
                    "holidays_are_distinct": value.holidays_are_distinct,
                    "holiday_wins_over_weekend": value.holiday_wins_over_weekend,
                }
            elif hasattr(value, "value"):
                result[field.name] = value.value
            else:
                result[field.name] = value
        return result

    def describe(self) -> str:
        """Render the profile as aligned ``name: value`` lines."""

        rendered = self.as_dict()
        width = max(len(key) for key in rendered)
        lines = [f"profile {self.name}"]
        if self.description:
            lines.append(f"  {self.description}")
        for key in sorted(rendered):
            if key in ("name", "description"):
                continue
            value = rendered[key]
            if isinstance(value, dict):
                value = ", ".join(f"{k}={v}" for k, v in sorted(value.items()))
            lines.append(f"  {key.ljust(width)}  {value}")
        return "\n".join(lines)
