"""The rating engine: from a dataset and a cycle to a bill."""

from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from ..charge.basis import Basis
from ..charge.classes import ChargeClass
from ..charge.context import RatingContext
from ..charge.determinant import DeterminantSet
from ..charge.lineitem import LineItem
from ..core.diagnostics import DiagnosticBag, Severity
from ..core.money import Money
from ..core.outcome import Outcome
from ..dataset import Dataset
from ..errors import RatingError, UnknownReferenceError
from ..meterdata.determinants import build_determinants
from ..model.quality import QualityCode
from ..policy.conventions import AssistanceStage, RoundingStage
from ..policy.profile import UtilityProfile
from ..tariff.components.discount import AssistanceDiscount
from ..tariff.model import Tariff
from ..tax.engine import apply_taxes
from ..timeline.calendars import MonthKey
from ..timeline.cycles import BillingCycle
from ..timeline.spans import Span
from ..version import version_string
from .bank import CreditBank
from .invoice import Invoice
from .netting import apply_netting
from .sequence import apply_rounding, run_components, round_total

__all__ = ["rate_cycle", "rate_period"]


def _segments(
    dataset: Dataset, service_point_id: str, span: Span, profile: UtilityProfile
) -> list[tuple[Span, Tariff]]:
    """Return the sub-spans of ``span`` and the tariff version rating each.

    Two independent things can change mid-cycle: which tariff the customer
    is enrolled on, and which version of that tariff is in force.  Both
    produce segments; the enrolment-resolution convention decides whether
    the first is honoured or collapsed onto one tariff for the whole cycle.
    """

    history = dataset.enrollment(service_point_id)
    resolved = history.resolve(span, profile.enrollment_resolution)
    segments: list[tuple[Span, Tariff]] = []
    for piece, enrollment in resolved:
        for sub_span, version in dataset.catalog.segments(enrollment.tariff_code, piece):
            segments.append((sub_span, version.tariff))
    segments.sort(key=lambda item: item[0].start)
    return segments


def _discount_components(tariff: Tariff) -> list[AssistanceDiscount]:
    """Return the assistance discounts a tariff declares."""

    return [
        component
        for component in tariff.components
        if isinstance(component, AssistanceDiscount)
    ]


def rate_period(
    dataset: Dataset,
    service_point_id: str,
    span: Span,
    cycle_span: Span,
    tariff: Tariff,
    profile: UtilityProfile,
    *,
    determinants: DeterminantSet | None = None,
) -> Outcome[list[LineItem]]:
    """Rate one homogeneous sub-period against one tariff version."""

    bag = DiagnosticBag()
    point = dataset.service_point(service_point_id)
    zone = dataset.zone_of(service_point_id)
    served = point.served_portion(span)
    if served is None:
        bag.emit(
            "rating.not_served",
            "service was not connected during this period",
            Severity.NOTICE,
            service_point_id,
            span=span.describe(),
        )
        return Outcome([], bag)

    quality = QualityCode.VALID
    if determinants is None:
        built = build_determinants(dataset, service_point_id, span, cycle_span, tariff, profile)
        bag.merge(built.diagnostics)
        if built.value.held:
            return Outcome([], bag)
        determinants = built.value.determinants
        quality = built.value.quality

    context = RatingContext(
        span,
        cycle_span,
        zone,
        profile,
        determinants,
        service_point_id,
        tariff.code,
        tariff.currency,
        dataset.holidays,
        served,
        bag,
    )
    account = dataset.account(point.account_id)
    ineligible = {
        component.code
        for component in _discount_components(tariff)
        if not component.applies_to(account.assistance_program)
    }
    lines = [
        line
        for line in run_components(context, tariff)
        if line.component not in ineligible
    ]
    if ineligible:
        bag.emit(
            "rating.discount.not_enrolled",
            "a discount the tariff offers was skipped; the account is not enrolled",
            Severity.NOTICE,
            service_point_id,
            components=", ".join(sorted(ineligible)),
        )
    if quality is not QualityCode.VALID:
        lines = [
            line if line.quality.rank >= quality.rank else _reflag(line, quality)
            for line in lines
        ]
    return Outcome(lines, bag)


def _reflag(line: LineItem, quality: QualityCode) -> LineItem:
    """Return a copy of ``line`` carrying a worse quality code."""

    return LineItem(
        line.line_id,
        line.code,
        line.label,
        line.charge_class,
        line.amount,
        line.quantity,
        line.rate,
        line.side,
        quality,
        line.component,
        line.taxable,
        line.trace,
        line.detail,
    )


def rate_cycle(
    dataset: Dataset,
    service_point_id: str,
    cycle: BillingCycle,
    *,
    profile: UtilityProfile | None = None,
    bank: CreditBank | None = None,
) -> Outcome[Invoice]:
    """Produce the bill for one service point over one billing cycle."""

    active = profile or dataset.profile
    bag = DiagnosticBag()
    point = dataset.service_point(service_point_id)
    account = dataset.account(point.account_id)
    zone = dataset.zone_of(service_point_id)
    currency = account.currency

    segments = _segments(dataset, service_point_id, cycle.span, active)
    if not segments:
        raise RatingError(
            "no tariff covers this billing cycle",
            service_point=service_point_id,
            cycle=cycle.cycle_id,
        )

    lines: list[LineItem] = []
    determinant_view: list[tuple[str, str]] = []
    tariff_codes: list[str] = []
    quality = QualityCode.VALID
    for span, tariff in segments:
        built = build_determinants(
            dataset, service_point_id, span, cycle.span, tariff, active
        )
        bag.merge(built.diagnostics)
        if built.value.held:
            bag.emit(
                "rating.held",
                "the bill was not produced because the meter data is on hold",
                Severity.ERROR,
                service_point_id,
                cycle=cycle.cycle_id,
            )
            invoice = Invoice.build(
                account.account_id,
                service_point_id,
                cycle.span,
                currency,
                cycle_id=cycle.cycle_id,
                profile_name=active.name,
                quality=QualityCode.MISSING,
                diagnostics=bag,
                engine_version=version_string(),
            )
            return Outcome(invoice, bag)
        if built.value.quality.rank > quality.rank:
            quality = built.value.quality
        outcome = rate_period(
            dataset,
            service_point_id,
            span,
            cycle.span,
            tariff,
            active,
            determinants=built.value.determinants,
        )
        bag.merge(outcome.diagnostics)
        lines.extend(outcome.value)
        tariff_codes.append(tariff.code)
        for determinant in built.value.determinants:
            determinant_view.append((determinant.name, determinant.quantity.format()))

    lines = apply_rounding(lines, active)

    premise = dataset.premises.get(point.premise_id)
    jurisdiction = premise.jurisdiction if premise is not None else ""
    rules = []
    if jurisdiction:
        try:
            rules = dataset.jurisdictions.rules_for(jurisdiction)
        except UnknownReferenceError:
            bag.emit(
                "rating.tax.unknown_jurisdiction",
                "the premise names a jurisdiction with no tax rules; no tax was applied",
                Severity.ERROR,
                service_point_id,
                jurisdiction=jurisdiction,
            )
    if rules:
        taxable_lines = list(lines)
        if active.assistance_stage is AssistanceStage.POST_TAX:
            taxable_lines = [
                line for line in lines if line.charge_class is not ChargeClass.DISCOUNT
            ]
        context = RatingContext(
            cycle.span,
            cycle.span,
            zone,
            active,
            DeterminantSet(),
            service_point_id,
            tariff_codes[0] if tariff_codes else "",
            currency,
            dataset.holidays,
            point.served_portion(cycle.span),
            bag,
        )
        tax_lines = apply_taxes(
            context,
            taxable_lines,
            rules,
            exemptions=dataset.exemptions,
            held_exemptions=account.tax_exemption_codes,
        )
        if active.rounding_stage is not RoundingStage.ON_TOTAL:
            tax_lines = apply_rounding(tax_lines, active)
        lines.extend(tax_lines)

    working_bank = bank if bank is not None else CreditBank(service_point_id)
    month = MonthKey.of(zone.local_date(cycle.span.end - timedelta(microseconds=1)))
    netting = apply_netting(lines, working_bank, active, month, currency)
    bag.merge(netting.diagnostics)
    lines = list(netting.lines)

    invoice = Invoice.build(
        account.account_id,
        service_point_id,
        cycle.span,
        currency,
        lines=tuple(lines),
        cycle_id=cycle.cycle_id,
        tariff_codes=tuple(dict.fromkeys(tariff_codes)),
        profile_name=active.name,
        quality=quality,
        determinants=tuple(sorted(set(determinant_view))),
        diagnostics=bag,
        credit_carried_in=netting.carried_in,
        credit_carried_out=netting.carried_out,
        engine_version=version_string(),
    )
    _check_total(invoice, active, bag)
    return Outcome(invoice, bag)


def _check_total(invoice: Invoice, profile: UtilityProfile, bag: DiagnosticBag) -> None:
    """Record a diagnostic when the rounded total differs from the exact one."""

    exact = invoice.subtotal(Basis.TOTAL)
    rounded = round_total(exact, profile)
    if rounded != exact.quantized(profile.money_places, profile.rounding_mode):
        bag.emit(
            "rating.total.snapped",
            "the total was snapped to the profile's increment",
            Severity.NOTICE,
            invoice.service_point_id,
            exact=exact.format(6),
            snapped=rounded.format(profile.money_places),
        )


def total_of(invoices: Sequence[Invoice], currency: str) -> Money:
    """Return the combined total of several bills."""

    total = Money.zero(currency)
    for invoice in invoices:
        total = total + invoice.total
    return total
