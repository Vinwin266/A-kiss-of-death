"""Reading and writing datasets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meterline.errors import DatasetError, SchemaError
from meterline.io.decode import dataset_from_dict
from meterline.io.encode import dataset_to_dict
from meterline.io.files import load_dataset, read_json, write_json, write_text
from meterline.io.jsonio import canonical_dumps, canonical_loads
from meterline.io.schema import require_keys, take_int, take_list, take_map, take_str

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class CanonicalJsonTests(unittest.TestCase):
    def test_keys_are_sorted(self) -> None:
        rendered = canonical_dumps({"b": 1, "a": 2})
        self.assertLess(rendered.index('"a"'), rendered.index('"b"'))

    def test_output_ends_with_a_newline(self) -> None:
        self.assertTrue(canonical_dumps({"a": 1}).endswith("\n"))

    def test_decimals_render_as_strings(self) -> None:
        from decimal import Decimal

        self.assertIn('"0.1"', canonical_dumps({"a": Decimal("0.1")}))

    def test_the_same_document_renders_identically(self) -> None:
        document = {"b": [3, 1, 2], "a": {"y": 1, "x": 2}}
        self.assertEqual(canonical_dumps(document), canonical_dumps(document))

    def test_malformed_json_reports_where(self) -> None:
        with self.assertRaises(DatasetError) as caught:
            canonical_loads("{not json}")
        self.assertIn("line", caught.exception.context)


class SchemaHelperTests(unittest.TestCase):
    def test_missing_keys_are_listed(self) -> None:
        with self.assertRaises(SchemaError) as caught:
            require_keys({"a": 1}, ["a", "b", "c"], context="thing")
        self.assertIn("b, c", caught.exception.context["missing"])

    def test_a_wrong_type_names_the_path(self) -> None:
        with self.assertRaises(SchemaError) as caught:
            take_str({"a": 1}, "a", context="thing")
        self.assertEqual(caught.exception.context["context"], "thing.a")

    def test_defaults_fill_absent_keys(self) -> None:
        self.assertEqual(take_str({}, "a", default="x"), "x")
        self.assertEqual(take_int({}, "a", default=3), 3)

    def test_booleans_are_not_integers(self) -> None:
        with self.assertRaises(SchemaError):
            take_int({"a": True}, "a")

    def test_lists_and_maps_default_to_empty(self) -> None:
        self.assertEqual(take_list({}, "a"), [])
        self.assertEqual(take_map({}, "a"), {})

    def test_a_list_where_a_map_belongs_is_refused(self) -> None:
        with self.assertRaises(SchemaError):
            take_map({"a": [1]}, "a")


class DatasetDecodeTests(unittest.TestCase):
    def test_a_dataset_must_be_an_object(self) -> None:
        with self.assertRaises(SchemaError):
            dataset_from_dict([])

    def test_the_tiny_example_loads(self) -> None:
        dataset = load_dataset(EXAMPLES / "tiny.json")
        self.assertEqual(dataset.counts()["service_points"], 1)
        self.assertEqual(dataset.counts()["reads"], 4)

    def test_the_riverside_example_loads(self) -> None:
        dataset = load_dataset(EXAMPLES / "riverside.json")
        counts = dataset.counts()
        self.assertEqual(counts["service_points"], 4)
        self.assertGreaterEqual(counts["tariffs"], 3)

    def test_the_examples_have_no_reference_errors(self) -> None:
        for name in ("tiny", "riverside"):
            dataset = load_dataset(EXAMPLES / f"{name}.json")
            self.assertFalse(dataset.check_references().has_errors, name)

    def test_cycles_are_generated_from_the_schedules(self) -> None:
        dataset = load_dataset(EXAMPLES / "tiny.json")
        self.assertEqual(len(dataset.cycles_of("sp-t1")), 3)

    def test_a_missing_file_is_reported_with_its_path(self) -> None:
        with self.assertRaises(DatasetError) as caught:
            load_dataset("/nonexistent/dataset.json")
        self.assertIn("path", caught.exception.context)

    def test_an_unknown_zone_is_refused_at_rating_time(self) -> None:
        dataset = load_dataset(EXAMPLES / "tiny.json")
        point = dataset.service_points["sp-t1"]
        dataset.service_points["sp-t1"] = type(point)(
            point.service_point_id,
            point.account_id,
            point.premise_id,
            "Mars/Olympus",
            point.kind,
        )
        self.assertTrue(dataset.check_references().has_errors)


class RoundTripTests(unittest.TestCase):
    def test_a_dataset_survives_export_and_re_import(self) -> None:
        original = load_dataset(EXAMPLES / "riverside.json")
        rendered = dataset_to_dict(original)
        rebuilt = dataset_from_dict(rendered)
        self.assertEqual(original.counts()["reads"], rebuilt.counts()["reads"])
        self.assertEqual(original.counts()["meters"], rebuilt.counts()["meters"])
        self.assertEqual(
            sorted(original.service_points), sorted(rebuilt.service_points)
        )
        self.assertEqual(original.catalog.codes(), rebuilt.catalog.codes())

    def test_a_time_of_use_tariff_keeps_its_windows(self) -> None:
        original = load_dataset(EXAMPLES / "riverside.json")
        rebuilt = dataset_from_dict(dataset_to_dict(original))
        before = original.catalog.resolve("GS-TOU", original.reads[0].at)
        after = rebuilt.catalog.resolve("GS-TOU", rebuilt.reads[0].at)
        self.assertEqual(before.buckets, after.buckets)
        self.assertEqual(before.seasons.codes, after.seasons.codes)

    def test_a_versioned_tariff_keeps_both_versions(self) -> None:
        original = load_dataset(EXAMPLES / "riverside.json")
        rebuilt = dataset_from_dict(dataset_to_dict(original))
        self.assertEqual(
            len(original.catalog.schedule("RES-STD").versions),
            len(rebuilt.catalog.schedule("RES-STD").versions),
        )

    def test_the_re_import_keeps_the_conventions(self) -> None:
        original = load_dataset(EXAMPLES / "riverside.json")
        rebuilt = dataset_from_dict(dataset_to_dict(original))
        self.assertEqual(original.profile.as_dict(), rebuilt.profile.as_dict())

    def test_exporting_twice_gives_the_same_bytes(self) -> None:
        dataset = load_dataset(EXAMPLES / "tiny.json")
        first = canonical_dumps(dataset_to_dict(dataset))
        second = canonical_dumps(dataset_to_dict(dataset))
        self.assertEqual(first, second)

    def test_writing_and_reading_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "out.json"
            write_json(target, {"a": 1})
            self.assertEqual(read_json(target), {"a": 1})

    def test_write_text_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a" / "b" / "c.txt"
            write_text(target, "hello")
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")


if __name__ == "__main__":
    unittest.main()
