"""Applying the credit bank and the negative-bill policy to a set of lines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..charge.basis import Basis, basis_amount
from ..charge.classes import ChargeClass, ChargeSide
from ..charge.lineitem import LineItem, LineItemBuilder
from ..core.decimals import ZERO
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.money import Money
from ..policy.conventions import BankExpiry, CashOutPolicy, NegativeBillPolicy
from ..policy.profile import UtilityProfile
from ..timeline.calendars import MonthKey
from .bank import CreditBank

__all__ = ["NettingResult", "apply_netting"]


@dataclass(slots=True)
class NettingResult:
    """The outcome of applying the bank to a bill."""

    lines: tuple[LineItem, ...]
    carried_in: Money
    carried_out: Money
    diagnostics: DiagnosticBag


def _line(
    code: str,
    label: str,
    amount: Money,
    charge_class: ChargeClass,
    note: str,
) -> LineItem:
    """Build one bank-related line item."""

    builder = LineItemBuilder(code, label, charge_class, "netting", ChargeSide.OTHER)
    builder.exempt()
    builder.note("bank", note)
    return builder.seal(amount)


def apply_netting(
    lines: Sequence[LineItem],
    bank: CreditBank,
    profile: UtilityProfile,
    month: MonthKey,
    currency: str,
) -> NettingResult:
    """Reconcile a bill against the customer's banked credits.

    The order is fixed and matters: expire first, then draw against a
    positive bill, then bank whatever a negative bill leaves over, then
    settle at the true-up month.  Settling before banking would cash out a
    credit the current bill had just earned, which is generous by accident
    rather than on purpose.
    """

    bag = DiagnosticBag()
    working = list(lines)
    carried_in = bank.money(currency)

    if profile.bank_expiry is BankExpiry.ROLLING_MONTHS:
        cutoff = month.shift(-profile.bank_rolling_months)
        expired = bank.expire_before(cutoff, month)
        if expired > ZERO:
            bag.emit(
                "rating.bank.expired",
                "banked credit older than the rolling window was removed",
                Severity.WARNING,
                bank.service_point_id,
                amount=str(expired),
                cutoff=str(cutoff),
            )

    total = basis_amount(working, Basis.TOTAL, currency)

    if total.amount > ZERO and not bank.is_empty:
        drawn = bank.apply(total.amount, month)
        if drawn > ZERO:
            working.append(
                _line(
                    "bank.applied",
                    "Banked credit applied",
                    Money(-drawn, currency),
                    ChargeClass.ADJUSTMENT,
                    "drawn from banked export credit",
                )
            )
            bag.emit(
                "rating.bank.applied",
                "banked credit reduced this bill",
                Severity.NOTICE,
                bank.service_point_id,
                amount=str(drawn),
            )
        total = basis_amount(working, Basis.TOTAL, currency)

    if total.amount < ZERO:
        surplus = -total.amount
        policy = profile.negative_bill
        if policy is NegativeBillPolicy.REFUND:
            bag.emit(
                "rating.bill.refund",
                "the bill is a net credit and will be refunded",
                Severity.NOTICE,
                bank.service_point_id,
                amount=str(surplus),
            )
        else:
            bank.earn(surplus, month, "surplus from bill")
            working.append(
                _line(
                    "bank.carried",
                    "Credit carried forward",
                    Money(surplus, currency),
                    ChargeClass.ADJUSTMENT,
                    "banked rather than refunded",
                )
            )
            bag.emit(
                "rating.bank.carried",
                "a net credit was banked rather than refunded",
                Severity.NOTICE,
                bank.service_point_id,
                amount=str(surplus),
                policy=policy.value,
            )

    if (
        profile.bank_expiry is BankExpiry.ANNUAL_TRUE_UP
        and month.month == profile.true_up_month
        and not bank.is_empty
    ):
        cash_out = profile.cash_out is CashOutPolicy.ANNUAL_AVOIDED_COST
        settled = bank.settle(month, cash_out=cash_out)
        if cash_out:
            working.append(
                _line(
                    "bank.cash_out",
                    "Annual true-up payment",
                    Money(-settled, currency),
                    ChargeClass.ADJUSTMENT,
                    "banked credit paid out at true-up",
                )
            )
            bag.emit(
                "rating.bank.cashed_out",
                "banked credit was paid out at the annual true-up",
                Severity.NOTICE,
                bank.service_point_id,
                amount=str(settled),
            )
        elif profile.cash_out is CashOutPolicy.FORFEIT:
            bag.emit(
                "rating.bank.forfeited",
                "banked credit was forfeited at the annual true-up",
                Severity.WARNING,
                bank.service_point_id,
                amount=str(settled),
            )
        else:
            bank.earn(settled, month, "true-up with no cash-out policy")

    return NettingResult(
        tuple(working), carried_in, bank.money(currency), bag
    )
