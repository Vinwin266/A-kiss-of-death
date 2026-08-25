"""Diagnostics, outcomes and deterministic identifiers."""

from __future__ import annotations

import unittest

from meterline.core.diagnostics import Diagnostic, DiagnosticBag, Severity
from meterline.core.ids import digest_of, sequence_id, short_digest, stable_id
from meterline.core.outcome import Outcome


class SeverityTests(unittest.TestCase):
    def test_severities_are_ordered(self) -> None:
        self.assertLess(Severity.INFO, Severity.WARNING)
        self.assertLess(Severity.WARNING, Severity.ERROR)

    def test_worst_of_an_empty_bag_is_info(self) -> None:
        self.assertIs(DiagnosticBag().worst, Severity.INFO)


class DiagnosticBagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bag = DiagnosticBag()
        self.bag.emit("b.code", "second", Severity.WARNING, "sp-1", detail=2)
        self.bag.emit("a.code", "first", Severity.ERROR, "sp-1")
        self.bag.emit("c.code", "third", Severity.INFO)

    def test_insertion_order_is_preserved(self) -> None:
        self.assertEqual([item.code for item in self.bag], ["b.code", "a.code", "c.code"])

    def test_sorted_items_put_the_worst_first(self) -> None:
        self.assertEqual(
            [item.code for item in self.bag.sorted_items()],
            ["a.code", "b.code", "c.code"],
        )

    def test_has_errors_reflects_severity(self) -> None:
        self.assertTrue(self.bag.has_errors)
        self.assertEqual(len(self.bag.warnings), 1)

    def test_at_least_filters_by_rank(self) -> None:
        self.assertEqual(len(self.bag.at_least(Severity.WARNING)), 2)

    def test_context_is_stringified_and_sorted(self) -> None:
        diagnostic = Diagnostic.make("x", "y", Severity.INFO, "s", b=2, a=1)
        self.assertEqual(diagnostic.context, (("a", "1"), ("b", "2")))

    def test_merge_absorbs_another_bag(self) -> None:
        other = DiagnosticBag()
        other.emit("d.code", "fourth")
        self.bag.merge(other)
        self.assertIn("d.code", self.bag.codes())

    def test_render_is_one_line(self) -> None:
        rendered = self.bag.items[0].render()
        self.assertNotIn("\n", rendered)
        self.assertIn("b.code", rendered)


class OutcomeTests(unittest.TestCase):
    def test_ok_has_no_diagnostics(self) -> None:
        outcome = Outcome.ok(42)
        self.assertTrue(outcome.is_ok)
        self.assertEqual(outcome.unwrap(), 42)

    def test_absorb_carries_diagnostics_across(self) -> None:
        first: Outcome[int] = Outcome.ok(1)
        second: Outcome[int] = Outcome.ok(2)
        second.diagnostics.emit("e", "problem", Severity.ERROR)
        first.absorb(second)
        self.assertFalse(first.is_ok)

    def test_map_keeps_the_diagnostics(self) -> None:
        outcome: Outcome[int] = Outcome.ok(2)
        outcome.diagnostics.emit("n", "note")
        mapped = outcome.map(lambda value: value * 3)
        self.assertEqual(mapped.value, 6)
        self.assertEqual(len(mapped.diagnostics), 1)


class IdentifierTests(unittest.TestCase):
    def test_the_same_inputs_give_the_same_id(self) -> None:
        self.assertEqual(stable_id("x", 1, "a"), stable_id("x", 1, "a"))

    def test_different_inputs_give_different_ids(self) -> None:
        self.assertNotEqual(stable_id("x", 1, "a"), stable_id("x", 1, "b"))

    def test_nested_structures_are_normalised_stably(self) -> None:
        self.assertEqual(
            digest_of({"a": 1, "b": [1, 2]}), digest_of({"b": [1, 2], "a": 1})
        )

    def test_none_and_the_string_none_do_not_collide(self) -> None:
        self.assertNotEqual(digest_of(None), digest_of("none"))

    def test_short_digest_length_is_respected(self) -> None:
        self.assertEqual(len(short_digest("x", length=8)), 8)

    def test_sequence_ids_are_zero_padded(self) -> None:
        self.assertEqual(sequence_id("li", 7), "li-0007")


if __name__ == "__main__":
    unittest.main()
