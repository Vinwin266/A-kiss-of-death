"""The facade: one object that holds a dataset and rates it.

A session exists so that callers do not have to remember the order things
happen in.  Bills for one service point must be produced oldest first,
because the credit bank carries between them, and a caller that rates
June before May gets a different — and wrong — answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from .audit.events import EventKind
from .audit.fingerprint import dataset_fingerprint, profile_fingerprint
from .audit.journal import Journal
from .core.diagnostics import DiagnosticBag, Severity
from .core.outcome import Outcome
from .dataset import Dataset
from .errors import RatingError
from .policy.profile import UtilityProfile
from .rating.bank import CreditBank
from .rating.engine import rate_cycle
from .rating.invoice import Invoice
from .report.summary import Summary, summarise
from .timeline.cycles import BillingCycle

__all__ = ["Session"]


@dataclass(slots=True)
class Session:
    """A dataset, a policy and the state that carries between bills."""

    dataset: Dataset
    profile: UtilityProfile | None = None
    journal: Journal = field(default_factory=Journal)
    banks: dict[str, CreditBank] = field(default_factory=dict)

    @classmethod
    def of(cls, dataset: Dataset, profile: UtilityProfile | None = None) -> "Session":
        """Build a session and record the opening journal event."""

        session = cls(dataset, profile)
        session.journal.run_label = dataset.name
        session.journal.started(dataset.name, dataset_fingerprint(dataset))
        session.journal.record(
            EventKind.PROFILE_SELECTED,
            session.active_profile.name,
            fingerprint=profile_fingerprint(session.active_profile),
        )
        return session

    @property
    def active_profile(self) -> UtilityProfile:
        """Return the profile in force for this session."""

        return self.profile or self.dataset.profile

    def bank_for(self, service_point_id: str) -> CreditBank:
        """Return the credit bank of a service point, creating it if needed."""

        bank = self.banks.get(service_point_id)
        if bank is None:
            bank = CreditBank(service_point_id)
            self.banks[service_point_id] = bank
        return bank

    # -- selection ------------------------------------------------------

    def service_point_ids(self) -> list[str]:
        """Return every service point in the dataset, sorted."""

        return sorted(self.dataset.service_points)

    def cycles_for(
        self, service_point_id: str, *, as_of: date | None = None
    ) -> list[BillingCycle]:
        """Return the cycles to bill, oldest first.

        ``as_of`` excludes cycles that have not finished yet, which is how a
        mid-month run avoids issuing a bill for a period the meter has not
        been read for.
        """

        cycles = sorted(
            self.dataset.cycles_of(service_point_id),
            key=lambda cycle: cycle.span.start,
        )
        if as_of is None:
            return cycles
        zone = self.dataset.zone_of(service_point_id)
        return [
            cycle
            for cycle in cycles
            if zone.local_date(cycle.span.end - timedelta(microseconds=1)) <= as_of
        ]

    # -- rating ---------------------------------------------------------

    def rate_service_point(
        self, service_point_id: str, *, as_of: date | None = None
    ) -> Outcome[list[Invoice]]:
        """Rate every eligible cycle of one service point, oldest first."""

        bag = DiagnosticBag()
        invoices: list[Invoice] = []
        bank = self.bank_for(service_point_id)
        for cycle in self.cycles_for(service_point_id, as_of=as_of):
            outcome = rate_cycle(
                self.dataset,
                service_point_id,
                cycle,
                profile=self.active_profile,
                bank=bank,
            )
            bag.merge(outcome.diagnostics)
            invoice = outcome.value
            invoices.append(invoice)
            if invoice.has_errors:
                self.journal.record(
                    EventKind.BILL_HELD,
                    invoice.bill_id,
                    service_point=service_point_id,
                    cycle=cycle.cycle_id,
                )
            else:
                self.journal.record(
                    EventKind.BILL_ISSUED,
                    invoice.bill_id,
                    service_point=service_point_id,
                    cycle=cycle.cycle_id,
                    total=invoice.total.format(),
                    quality=invoice.quality.value,
                )
        return Outcome(invoices, bag)

    def rate_all(
        self,
        *,
        as_of: date | None = None,
        service_point_ids: Sequence[str] | None = None,
    ) -> Outcome[list[Invoice]]:
        """Rate every service point, in a deterministic order."""

        bag = DiagnosticBag()
        invoices: list[Invoice] = []
        targets = list(service_point_ids or self.service_point_ids())
        for service_point_id in sorted(targets):
            if service_point_id not in self.dataset.service_points:
                bag.emit(
                    "session.unknown_service_point",
                    "no such service point in this dataset",
                    Severity.ERROR,
                    service_point_id,
                )
                continue
            outcome = self.rate_service_point(service_point_id, as_of=as_of)
            bag.merge(outcome.diagnostics)
            invoices.extend(outcome.value)
        self.journal.finished(len(invoices))
        return Outcome(invoices, bag)

    def bill(
        self, service_point_id: str, cycle_id: str
    ) -> Outcome[Invoice]:
        """Rate one named cycle, replaying earlier ones for bank state."""

        cycles = self.cycles_for(service_point_id)
        wanted = [cycle for cycle in cycles if cycle.cycle_id == cycle_id]
        if not wanted:
            raise RatingError(
                "no such billing cycle for this service point",
                service_point=service_point_id,
                cycle=cycle_id,
            )
        bag = DiagnosticBag()
        bank = CreditBank(service_point_id)
        result: Invoice | None = None
        for cycle in cycles:
            outcome = rate_cycle(
                self.dataset,
                service_point_id,
                cycle,
                profile=self.active_profile,
                bank=bank,
            )
            if cycle.cycle_id == cycle_id:
                bag.merge(outcome.diagnostics)
                result = outcome.value
                break
        assert result is not None  # guarded by the membership test above
        return Outcome(result, bag)

    # -- reporting ------------------------------------------------------

    def summarise(self, invoices: Iterable[Invoice]) -> Summary:
        """Aggregate a run of bills."""

        materialised = list(invoices)
        currency = materialised[0].currency if materialised else "USD"
        return summarise(materialised, currency)

    def fingerprints(self) -> dict[str, str]:
        """Return the fingerprints a reproducible run depends on."""

        return {
            "dataset": dataset_fingerprint(self.dataset),
            "profile": profile_fingerprint(self.active_profile),
            "journal": self.journal.digest,
        }
