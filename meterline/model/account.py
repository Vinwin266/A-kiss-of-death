"""Accounts: who receives the bill."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..constants import DEFAULT_CURRENCY

__all__ = ["AccountStatus", "Account"]


class AccountStatus(str, Enum):
    """The billing state of an account."""

    ACTIVE = "active"
    FINAL = "final"
    """Closed; a final bill has been or is about to be issued."""

    INACTIVE = "inactive"
    """No service points connected, but the account is retained."""

    @property
    def bills(self) -> bool:
        """Return ``True`` when the account still receives bills."""

        return self is not AccountStatus.INACTIVE


@dataclass(frozen=True, slots=True)
class Account:
    """A billing relationship with a customer."""

    account_id: str
    name: str = ""
    currency: str = DEFAULT_CURRENCY
    status: AccountStatus = AccountStatus.ACTIVE
    service_point_ids: tuple[str, ...] = ()
    assistance_program: str = ""
    """Code of the discount programme the account is enrolled in, if any."""

    budget_plan_id: str = ""
    """Levelised-payment plan the account is on, if any."""

    tax_exemption_codes: tuple[str, ...] = ()
    mailing_premise_id: str = ""

    @property
    def display_name(self) -> str:
        """Return the customer name, falling back to the identifier."""

        return self.name or self.account_id

    @property
    def is_on_assistance(self) -> bool:
        """Return ``True`` when a discount programme applies."""

        return bool(self.assistance_program)

    @property
    def is_on_budget_billing(self) -> bool:
        """Return ``True`` when the account pays a levelised amount."""

        return bool(self.budget_plan_id)

    def describe(self) -> str:
        """Return a one-line description for reports."""

        parts = [f"{self.display_name} ({self.status.value})"]
        if self.service_point_ids:
            parts.append(f"{len(self.service_point_ids)} service point(s)")
        if self.assistance_program:
            parts.append(f"assistance {self.assistance_program}")
        return ", ".join(parts)
