"""Static checks on a tariff, before any bill is produced.

These are the mistakes that survive a code review of a rate sheet: a
time-of-use tariff that prices three buckets while its windows produce four,
a season set with a two-day hole in it, two windows that both claim 18:00 on
a summer weekday.  None of them raise — a tariff can be deliberately odd —
but all of them are reported.
"""

from __future__ import annotations

from ..charge.classes import ChargeClass
from ..constants import MINUTES_PER_DAY
from ..core.decimals import ZERO
from ..core.diagnostics import DiagnosticBag, Severity
from ..policy.conventions import WindowPrecedence
from ..timeline.daytypes import DayType
from .components.blocks import Block
from .components.credit import ExportCredit
from .components.demand import DemandCharge
from .components.rider import Rider, RiderKind
from .components.step import SteppedCharge
from .components.tiered import TieredCharge
from .components.tou import TouCharge
from .model import Tariff

__all__ = ["validate_tariff"]


def _check_blocks(blocks: tuple[Block, ...], code: str, bag: DiagnosticBag) -> None:
    """Report blocks that are priced oddly."""

    for index, block in enumerate(blocks):
        if block.rate < ZERO:
            bag.emit(
                "tariff.block.negative_rate",
                "a block is priced below zero, which credits usage",
                Severity.WARNING,
                code,
                block=index + 1,
                rate=str(block.rate),
            )
    rates = [block.rate for block in blocks]
    if len(rates) > 1 and rates == sorted(rates, reverse=True):
        bag.emit(
            "tariff.block.declining",
            "the blocks decline, so heavy use is cheaper per unit",
            Severity.NOTICE,
            code,
        )


def _check_windows(tariff: Tariff, bag: DiagnosticBag) -> None:
    """Report window overlaps and gaps."""

    windows = tariff.windows
    if windows is None or not windows.windows:
        return
    day_types = (DayType.WEEKDAY, DayType.WEEKEND, DayType.HOLIDAY)
    seasons = tariff.seasons.codes if tariff.seasons is not None else ("",)
    marks = windows.boundaries()
    for season in seasons or ("",):
        for day_type in day_types:
            uncovered = 0
            for start, end in zip(marks, marks[1:]):
                probe = start
                matches = [
                    window
                    for window in windows.windows
                    if window.matches(probe, day_type, season)
                ]
                if not matches:
                    uncovered += end - start
                elif len(matches) > 1:
                    resolved = windows.resolve(
                        probe, day_type, season, WindowPrecedence.MOST_SPECIFIC
                    )
                    bag.emit(
                        "tariff.window.overlap",
                        "more than one window claims this time; precedence decides",
                        Severity.NOTICE,
                        tariff.code,
                        day_type=day_type.value,
                        season=season or "all",
                        minute=start,
                        buckets=", ".join(sorted(w.bucket for w in matches)),
                        resolved=resolved,
                    )
            if uncovered and uncovered < MINUTES_PER_DAY:
                bag.emit(
                    "tariff.window.gap",
                    "part of the day falls in no window and uses the default bucket",
                    Severity.NOTICE,
                    tariff.code,
                    day_type=day_type.value,
                    season=season or "all",
                    minutes=uncovered,
                    default=windows.default_bucket,
                )


def _check_tou_coverage(tariff: Tariff, bag: DiagnosticBag) -> None:
    """Report buckets a time-of-use component does not price."""

    declared = set(tariff.buckets)
    if not declared:
        return
    for component in tariff.components:
        if not isinstance(component, TouCharge):
            continue
        priced = set(component.rates)
        missing = sorted(declared - priced)
        extra = sorted(priced - declared)
        if missing:
            bag.emit(
                "tariff.tou.unpriced_bucket",
                "the windows produce buckets this component does not price",
                Severity.WARNING,
                component.code,
                buckets=", ".join(missing),
            )
        if extra:
            bag.emit(
                "tariff.tou.unused_rate",
                "the component prices buckets the windows never produce",
                Severity.NOTICE,
                component.code,
                buckets=", ".join(extra),
            )


def _check_seasons(tariff: Tariff, bag: DiagnosticBag) -> None:
    """Report a season set that does not cover the year."""

    seasons = tariff.seasons
    if seasons is None or not seasons.seasons:
        return
    if not seasons.covers_year() and not seasons.default_code:
        bag.emit(
            "tariff.season.gap",
            "some days fall in no season and no default season is declared",
            Severity.WARNING,
            tariff.code,
        )


def _check_structure(tariff: Tariff, bag: DiagnosticBag) -> None:
    """Report structural oddities in the component list."""

    minimums = tariff.components_of_class(ChargeClass.MINIMUM)
    if len(minimums) > 1:
        bag.emit(
            "tariff.minimum.multiple",
            "more than one minimum charge; each sees the other's make-up line",
            Severity.WARNING,
            tariff.code,
            components=", ".join(component.code for component in minimums),
        )
    for component in tariff.components:
        if isinstance(component, Rider) and component.rider_kind is RiderKind.PERCENT:
            later = [
                other
                for other in tariff.components
                if other.stage < component.stage
                and other.charge_class is ChargeClass.MINIMUM
            ]
            if later:
                bag.emit(
                    "tariff.rider.after_minimum",
                    "a percentage rider is assessed after the minimum make-up",
                    Severity.NOTICE,
                    component.code,
                )
        if isinstance(component, ExportCredit) and component.avoided_cost_rate <= ZERO:
            bag.emit(
                "tariff.credit.no_avoided_cost",
                "no avoided-cost rate; switching valuation would credit nothing",
                Severity.NOTICE,
                component.code,
            )
        if isinstance(component, DemandCharge) and component.rate <= ZERO:
            bag.emit(
                "tariff.demand.zero_rate",
                "the demand charge is priced at zero",
                Severity.WARNING,
                component.code,
            )
        if isinstance(component, (TieredCharge, SteppedCharge)):
            _check_blocks(component.blocks, component.code, bag)


def validate_tariff(tariff: Tariff) -> DiagnosticBag:
    """Return every diagnostic a static reading of the tariff produces."""

    bag = DiagnosticBag()
    _check_structure(tariff, bag)
    _check_windows(tariff, bag)
    _check_tou_coverage(tariff, bag)
    _check_seasons(tariff, bag)
    return bag
