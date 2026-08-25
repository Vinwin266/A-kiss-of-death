"""The determinism claim, exercised the way the README states it."""

from __future__ import annotations

import unittest
from pathlib import Path

from meterline.audit.fingerprint import dataset_fingerprint
from meterline.io.files import load_dataset
from meterline.io.jsonio import canonical_dumps
from meterline.policy.presets import preset_names, preset
from meterline.report.explain import explain_invoice
from meterline.report.invoice_text import render_invoice
from meterline.session import Session

from tests.support import build_dataset

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def rate(path: Path, profile_name: str | None = None) -> str:
    """Rate a dataset file and render the run canonically."""

    dataset = load_dataset(path)
    session = Session.of(dataset, preset(profile_name) if profile_name else None)
    outcome = session.rate_all()
    return canonical_dumps(
        {
            "fingerprints": session.fingerprints(),
            "bills": [invoice.as_dict() for invoice in outcome.value],
            "diagnostics": outcome.diagnostics.as_list(),
        }
    )


class ReplayTests(unittest.TestCase):
    def test_the_tiny_example_replays_identically(self) -> None:
        first = rate(EXAMPLES / "tiny.json")
        for _ in range(2):
            self.assertEqual(rate(EXAMPLES / "tiny.json"), first)

    def test_the_riverside_example_replays_identically(self) -> None:
        first = rate(EXAMPLES / "riverside.json")
        for _ in range(2):
            self.assertEqual(rate(EXAMPLES / "riverside.json"), first)

    def test_every_preset_replays_identically(self) -> None:
        for name in preset_names():
            first = rate(EXAMPLES / "tiny.json", name)
            self.assertEqual(rate(EXAMPLES / "tiny.json", name), first, name)

    def test_an_in_memory_dataset_replays_identically(self) -> None:
        renders = []
        for _ in range(3):
            session = Session.of(build_dataset(steps=(450, 620, 380)))
            outcome = session.rate_all()
            renders.append(
                canonical_dumps([invoice.as_dict() for invoice in outcome.value])
            )
        self.assertEqual(len(set(renders)), 1)


class StabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = load_dataset(EXAMPLES / "riverside.json")
        self.session = Session.of(self.dataset)
        self.invoices = self.session.rate_all().value

    def test_rendering_a_bill_twice_gives_the_same_text(self) -> None:
        zone = self.dataset.zone_of(self.invoices[0].service_point_id)
        first = render_invoice(self.invoices[0], zone)
        self.assertEqual(render_invoice(self.invoices[0], zone), first)

    def test_explaining_a_bill_twice_gives_the_same_text(self) -> None:
        zone = self.dataset.zone_of(self.invoices[0].service_point_id)
        first = explain_invoice(self.invoices[0], zone)
        self.assertEqual(explain_invoice(self.invoices[0], zone), first)

    def test_bill_identifiers_do_not_depend_on_the_run(self) -> None:
        again = Session.of(load_dataset(EXAMPLES / "riverside.json")).rate_all().value
        self.assertEqual(
            [invoice.bill_id for invoice in self.invoices],
            [invoice.bill_id for invoice in again],
        )

    def test_line_identifiers_are_content_derived(self) -> None:
        again = Session.of(load_dataset(EXAMPLES / "riverside.json")).rate_all().value
        for left, right in zip(self.invoices, again):
            self.assertEqual(
                [line.line_id for line in left.ordered_lines()],
                [line.line_id for line in right.ordered_lines()],
            )

    def test_the_dataset_fingerprint_is_stable(self) -> None:
        again = load_dataset(EXAMPLES / "riverside.json")
        self.assertEqual(dataset_fingerprint(self.dataset), dataset_fingerprint(again))

    def test_no_module_reaches_for_the_clock_or_randomness(self) -> None:
        root = Path(__file__).resolve().parent.parent / "meterline"
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in ("import random", "datetime.now(", "time.time(", "uuid4"):
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        self.assertEqual(offenders, [])


class ProfileDifferenceTests(unittest.TestCase):
    def test_the_presets_do_not_all_agree(self) -> None:
        totals = {name: rate(EXAMPLES / "riverside.json", name) for name in preset_names()}
        self.assertGreater(len(set(totals.values())), 1)

    def test_each_preset_is_internally_consistent(self) -> None:
        for name in preset_names():
            dataset = load_dataset(EXAMPLES / "riverside.json")
            session = Session.of(dataset, preset(name))
            invoices = session.rate_all().value
            for invoice in invoices:
                summed = sum(
                    (line.amount.amount for line in invoice.lines),
                    invoice.total.amount * 0,
                )
                self.assertEqual(invoice.total.amount, summed, f"{name} {invoice.bill_id}")


if __name__ == "__main__":
    unittest.main()
