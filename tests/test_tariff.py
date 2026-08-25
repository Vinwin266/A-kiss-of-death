"""Tariffs: assembly, versioning, loading and static checks."""

from __future__ import annotations

import unittest

from meterline.charge.classes import ChargeClass
from meterline.core.diagnostics import Severity
from meterline.errors import TariffError, UnknownComponentError
from meterline.model.service_point import ServiceKind
from meterline.tariff.catalog import TariffCatalog
from meterline.tariff.components.base import Stage
from meterline.tariff.components.blocks import Block
from meterline.tariff.components.fixed import FixedCharge
from meterline.tariff.components.minimum import MinimumCharge
from meterline.tariff.components.tiered import TieredCharge
from meterline.tariff.loader import component_from_dict, tariff_from_dict
from meterline.tariff.model import Tariff
from meterline.tariff.schedule import TariffSchedule, TariffVersion
from meterline.tariff.validate import validate_tariff
from meterline.timeline.instants import utc
from meterline.timeline.spans import Span

from tests.support import residential_tariff, tou_tariff


class TariffStructureTests(unittest.TestCase):
    def test_components_run_in_stage_order(self) -> None:
        tariff = Tariff(
            "T",
            "Test",
            (
                MinimumCharge("min", "Minimum", "10"),
                FixedCharge("basic", "Basic", "5"),
            ),
        )
        self.assertEqual(
            [component.code for component in tariff.ordered_components()],
            ["basic", "min"],
        )

    def test_declaration_order_breaks_stage_ties(self) -> None:
        tariff = Tariff(
            "T",
            "Test",
            (
                FixedCharge("second", "Second", "5"),
                FixedCharge("first", "First", "5"),
            ),
        )
        self.assertEqual(
            [component.code for component in tariff.ordered_components()],
            ["second", "first"],
        )

    def test_duplicate_component_codes_are_refused(self) -> None:
        with self.assertRaises(TariffError):
            Tariff(
                "T",
                "Test",
                (FixedCharge("basic", "A", "1"), FixedCharge("basic", "B", "2")),
            )

    def test_a_tariff_needs_a_component(self) -> None:
        with self.assertRaises(TariffError):
            Tariff("T", "Test", ())

    def test_unknown_components_are_reported(self) -> None:
        with self.assertRaises(TariffError):
            residential_tariff().component("nope")

    def test_a_tariff_lists_the_determinants_it_reads(self) -> None:
        self.assertIn("energy.total", residential_tariff().determinant_names())

    def test_service_class_eligibility(self) -> None:
        tariff = tou_tariff()
        self.assertTrue(tariff.accepts(ServiceKind.SMALL_COMMERCIAL))
        self.assertFalse(tariff.accepts(ServiceKind.RESIDENTIAL))

    def test_an_unrestricted_tariff_accepts_everyone(self) -> None:
        self.assertTrue(residential_tariff().accepts(ServiceKind.INDUSTRIAL))

    def test_derived_flags(self) -> None:
        tariff = tou_tariff()
        self.assertTrue(tariff.is_time_of_use)
        self.assertTrue(tariff.is_demand_billed)
        self.assertFalse(tariff.credits_exports)

    def test_stages_are_reported_in_order(self) -> None:
        self.assertEqual(
            residential_tariff().stages(), [Stage.FIXED, Stage.ENERGY, Stage.MINIMUM]
        )

    def test_a_tariff_describes_itself(self) -> None:
        described = tou_tariff().describe()
        self.assertIn("windows:", described)
        self.assertIn("seasons:", described)

    def test_stage_names_round_trip(self) -> None:
        self.assertEqual(Stage.name_of(Stage.ENERGY), "energy")
        self.assertEqual(Stage.name_of(99), "stage-99")


class ScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = TariffVersion("1", utc(2025, 1, 1), residential_tariff())
        self.second = TariffVersion(
            "2", utc(2025, 4, 1), residential_tariff(first_block_rate="0.20")
        )
        self.schedule = TariffSchedule.of("RES", [self.second, self.first])

    def test_versions_are_sorted(self) -> None:
        self.assertEqual(
            [version.version for version in self.schedule.versions], ["1", "2"]
        )

    def test_an_open_version_is_closed_by_its_successor(self) -> None:
        self.assertEqual(self.schedule.versions[0].effective_to, utc(2025, 4, 1))

    def test_only_one_version_covers_an_instant(self) -> None:
        covering = [
            version
            for version in self.schedule.versions
            if version.covers(utc(2025, 5, 1))
        ]
        self.assertEqual(len(covering), 1)
        self.assertEqual(covering[0].version, "2")

    def test_a_span_across_the_change_produces_two_segments(self) -> None:
        segments = self.schedule.segments(Span(utc(2025, 3, 15), utc(2025, 4, 15)))
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0].end, utc(2025, 4, 1))
        self.assertEqual(segments[1][1].version, "2")

    def test_segments_tile_the_span(self) -> None:
        span = Span(utc(2025, 3, 15), utc(2025, 4, 15))
        segments = self.schedule.segments(span)
        self.assertEqual(segments[0][0].start, span.start)
        self.assertEqual(segments[-1][0].end, span.end)

    def test_a_period_before_any_version_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            self.schedule.at(utc(2024, 1, 1))

    def test_a_version_cannot_end_before_it_starts(self) -> None:
        with self.assertRaises(TariffError):
            TariffVersion("x", utc(2025, 4, 1), residential_tariff(), utc(2025, 1, 1))


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = TariffCatalog.single_version(
            [residential_tariff("RES"), tou_tariff("TOU")], utc(2025, 1, 1)
        )

    def test_codes_are_sorted(self) -> None:
        self.assertEqual(self.catalog.codes(), ["RES", "TOU"])

    def test_membership_and_length(self) -> None:
        self.assertIn("RES", self.catalog)
        self.assertEqual(len(self.catalog), 2)

    def test_unknown_codes_list_the_known_ones(self) -> None:
        with self.assertRaises(TariffError) as caught:
            self.catalog.schedule("NOPE")
        self.assertIn("known", caught.exception.context)

    def test_eligibility_filters_by_service_class(self) -> None:
        eligible = self.catalog.eligible_for(
            ServiceKind.RESIDENTIAL, utc(2025, 6, 1)
        )
        self.assertEqual(eligible, ["RES"])

    def test_adding_a_version_extends_the_schedule(self) -> None:
        self.catalog.add_version(
            TariffVersion("2", utc(2025, 6, 1), residential_tariff("RES"))
        )
        self.assertTrue(self.catalog.schedule("RES").is_versioned)


class LoaderTests(unittest.TestCase):
    def test_a_minimal_tariff_loads(self) -> None:
        tariff = tariff_from_dict(
            {
                "code": "X",
                "name": "Example",
                "components": [
                    {"kind": "fixed", "code": "basic", "amount": "10"},
                    {
                        "kind": "tiered",
                        "code": "energy",
                        "blocks": [{"limit": None, "rate": "0.1"}],
                    },
                ],
            }
        )
        self.assertEqual(len(tariff.components), 2)

    def test_an_unknown_kind_lists_the_known_ones(self) -> None:
        with self.assertRaises(UnknownComponentError) as caught:
            component_from_dict({"kind": "magic", "code": "x"})
        self.assertIn("tiered", caught.exception.context["known"])

    def test_a_component_without_a_code_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            component_from_dict({"kind": "fixed", "amount": "1"})

    def test_a_tariff_without_a_code_is_refused(self) -> None:
        with self.assertRaises(TariffError):
            tariff_from_dict({"name": "no code"})

    def test_windows_and_seasons_load(self) -> None:
        tariff = tariff_from_dict(
            {
                "code": "T",
                "components": [
                    {
                        "kind": "tou",
                        "code": "energy",
                        "rates": {"peak": "0.2", "offpeak": "0.1"},
                    }
                ],
                "windows": [
                    {
                        "bucket": "peak",
                        "start": "14:00",
                        "end": "19:00",
                        "day_types": ["weekday"],
                    }
                ],
                "seasons": [
                    {
                        "code": "summer",
                        "start_month": 6,
                        "start_day": 1,
                        "end_month": 9,
                        "end_day": 30,
                    }
                ],
            }
        )
        self.assertTrue(tariff.is_time_of_use)
        self.assertEqual(tariff.seasons.codes, ("summer",))

    def test_a_loaded_tariff_round_trips_through_its_dict(self) -> None:
        original = residential_tariff()
        rendered = original.as_dict()
        self.assertEqual(rendered["code"], original.code)
        self.assertEqual(len(rendered["components"]), len(original.components))


class ValidationTests(unittest.TestCase):
    def test_a_clean_tariff_produces_nothing(self) -> None:
        bag = validate_tariff(residential_tariff())
        self.assertEqual(bag.at_least(Severity.WARNING), [])

    def test_an_unpriced_bucket_is_a_warning(self) -> None:
        tariff = tou_tariff()
        stripped = Tariff(
            tariff.code,
            tariff.name,
            tuple(
                component
                for component in tariff.components
                if component.code != "energy"
            )
            + (
                type(tariff.component("energy"))(
                    "energy", "Energy", {"peak": "0.2"}
                ),
            ),
            windows=tariff.windows,
            seasons=tariff.seasons,
        )
        bag = validate_tariff(stripped)
        self.assertIn("tariff.tou.unpriced_bucket", bag.codes())

    def test_overlapping_windows_are_noted(self) -> None:
        bag = validate_tariff(tou_tariff())
        self.assertIn("tariff.window.overlap", bag.codes())

    def test_two_minimum_charges_are_a_warning(self) -> None:
        tariff = Tariff(
            "T",
            "Test",
            (
                TieredCharge("energy", "Energy", [Block.of(None, "0.1")]),
                MinimumCharge("m1", "Minimum", "10"),
                MinimumCharge("m2", "Minimum", "20"),
            ),
        )
        bag = validate_tariff(tariff)
        self.assertIn("tariff.minimum.multiple", bag.codes())

    def test_a_declining_block_schedule_is_noted(self) -> None:
        tariff = Tariff(
            "T",
            "Test",
            (
                TieredCharge(
                    "energy",
                    "Energy",
                    [Block.of(500, "0.15"), Block.of(None, "0.10")],
                ),
            ),
        )
        bag = validate_tariff(tariff)
        self.assertIn("tariff.block.declining", bag.codes())

    def test_a_negative_block_rate_is_a_warning(self) -> None:
        tariff = Tariff(
            "T",
            "Test",
            (TieredCharge("energy", "Energy", [Block.of(None, "-0.10")]),),
        )
        bag = validate_tariff(tariff)
        self.assertIn("tariff.block.negative_rate", bag.codes())

    def test_charge_classes_sort_for_rendering(self) -> None:
        self.assertLess(ChargeClass.FIXED.sort_order, ChargeClass.TAX.sort_order)


if __name__ == "__main__":
    unittest.main()
