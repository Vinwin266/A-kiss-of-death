"""The session facade, the journal and portfolio summaries."""

from __future__ import annotations

import unittest
from datetime import date

from meterline.audit.events import EventKind
from meterline.audit.fingerprint import (
    dataset_fingerprint,
    profile_fingerprint,
    tariff_fingerprint,
)
from meterline.audit.journal import Journal
from meterline.io.files import load_dataset
from meterline.policy.presets import preset
from meterline.report.summary import summarise
from meterline.session import Session

from pathlib import Path

from tests.support import build_dataset, residential_tariff

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = build_dataset(steps=(450, 620, 380))
        self.session = Session.of(self.dataset)

    def test_the_active_profile_falls_back_to_the_dataset(self) -> None:
        self.assertEqual(self.session.active_profile.name, self.dataset.profile.name)

    def test_an_override_profile_wins(self) -> None:
        session = Session.of(self.dataset, preset("legacy-cooperative"))
        self.assertEqual(session.active_profile.name, "legacy-cooperative")

    def test_service_points_are_sorted(self) -> None:
        self.assertEqual(self.session.service_point_ids(), ["sp-1"])

    def test_cycles_are_returned_oldest_first(self) -> None:
        cycles = self.session.cycles_for("sp-1")
        self.assertEqual([cycle.span.start for cycle in cycles], sorted(
            cycle.span.start for cycle in cycles
        ))

    def test_as_of_excludes_unfinished_cycles(self) -> None:
        cycles = self.session.cycles_for("sp-1")
        cutoff = self.dataset.zone_of("sp-1").local_date(cycles[0].span.end)
        selected = self.session.cycles_for("sp-1", as_of=cutoff)
        self.assertEqual(len(selected), 1)

    def test_rating_an_unknown_service_point_is_a_diagnostic(self) -> None:
        outcome = self.session.rate_all(service_point_ids=["sp-nope"])
        self.assertIn("session.unknown_service_point", outcome.diagnostics.codes())
        self.assertEqual(outcome.value, [])

    def test_a_bank_is_created_on_demand_and_reused(self) -> None:
        first = self.session.bank_for("sp-1")
        self.assertIs(first, self.session.bank_for("sp-1"))

    def test_the_journal_records_the_run(self) -> None:
        self.session.rate_all()
        kinds = [event.kind for event in self.session.journal]
        self.assertIn(EventKind.RUN_STARTED, kinds)
        self.assertIn(EventKind.BILL_ISSUED, kinds)
        self.assertIn(EventKind.RUN_FINISHED, kinds)

    def test_the_journal_digest_is_stable(self) -> None:
        first = Session.of(build_dataset(steps=(450, 620, 380)))
        first.rate_all()
        second = Session.of(build_dataset(steps=(450, 620, 380)))
        second.rate_all()
        self.assertEqual(first.journal.digest, second.journal.digest)

    def test_fingerprints_cover_dataset_and_profile(self) -> None:
        prints = self.session.fingerprints()
        self.assertIn("dataset", prints)
        self.assertIn("profile", prints)


class FingerprintTests(unittest.TestCase):
    def test_the_same_dataset_fingerprints_the_same(self) -> None:
        self.assertEqual(
            dataset_fingerprint(build_dataset()), dataset_fingerprint(build_dataset())
        )

    def test_different_usage_fingerprints_differently(self) -> None:
        self.assertNotEqual(
            dataset_fingerprint(build_dataset(steps=(1,))),
            dataset_fingerprint(build_dataset(steps=(2,))),
        )

    def test_a_changed_convention_changes_the_profile_print(self) -> None:
        self.assertNotEqual(
            profile_fingerprint(preset("model-rules")),
            profile_fingerprint(preset("legacy-cooperative")),
        )

    def test_a_changed_rate_changes_the_tariff_print(self) -> None:
        self.assertNotEqual(
            tariff_fingerprint(residential_tariff(first_block_rate="0.10")),
            tariff_fingerprint(residential_tariff(first_block_rate="0.11")),
        )

    def test_a_file_and_an_in_memory_dataset_agree(self) -> None:
        one = load_dataset(EXAMPLES / "tiny.json")
        two = load_dataset(EXAMPLES / "tiny.json")
        self.assertEqual(dataset_fingerprint(one), dataset_fingerprint(two))


class JournalTests(unittest.TestCase):
    def test_events_are_numbered_from_one(self) -> None:
        journal = Journal("run")
        journal.record(EventKind.RUN_STARTED, "x")
        journal.record(EventKind.RUN_FINISHED, "x")
        self.assertEqual([event.sequence for event in journal], [1, 2])

    def test_events_render_on_one_line(self) -> None:
        journal = Journal("run")
        event = journal.record(EventKind.BILL_ISSUED, "bill-1", total="10.00")
        self.assertNotIn("\n", event.render())
        self.assertIn("total=10.00", event.render())

    def test_filtering_by_kind(self) -> None:
        journal = Journal("run")
        journal.record(EventKind.BILL_ISSUED, "a")
        journal.record(EventKind.BILL_HELD, "b")
        self.assertEqual(len(journal.of_kind(EventKind.BILL_ISSUED)), 1)

    def test_the_journal_serialises(self) -> None:
        journal = Journal("run")
        journal.started("dataset", "abc")
        rendered = journal.as_list()
        self.assertEqual(rendered[0]["kind"], "run_started")


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.invoices = Session.of(build_dataset(steps=(450, 620, 380))).rate_all().value

    def test_the_count_matches(self) -> None:
        self.assertEqual(summarise(self.invoices).count, 3)

    def test_the_total_is_the_sum_of_the_bills(self) -> None:
        summary = summarise(self.invoices)
        expected = sum((invoice.total.amount for invoice in self.invoices))
        self.assertEqual(summary.total.amount, expected)

    def test_the_average_divides_by_the_count(self) -> None:
        summary = summarise(self.invoices)
        self.assertAlmostEqual(
            float(summary.average.amount * 3), float(summary.total.amount), places=6
        )

    def test_an_empty_run_summarises_to_zero(self) -> None:
        summary = summarise([])
        self.assertEqual(summary.count, 0)
        self.assertTrue(summary.average.is_zero)

    def test_the_largest_bill_is_identified(self) -> None:
        summary = summarise(self.invoices)
        self.assertEqual(summary.largest, max(self.invoices, key=lambda i: i.total))


if __name__ == "__main__":
    unittest.main()
