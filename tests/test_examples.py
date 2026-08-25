"""The checked-in examples are the ones the generator produces.

CI regenerates them and fails on a diff; this covers the same ground in the
suite so the mismatch is caught before a push rather than after one.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from meterline.io.jsonio import canonical_dumps, canonical_loads
from meterline.session import Session
from meterline.io.files import load_dataset
from meterline.policy.presets import preset_names, preset

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def _generator():
    """Import ``tools/make_examples.py`` without it being a package."""

    spec = importlib.util.spec_from_file_location(
        "make_examples", ROOT / "tools" / "make_examples.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GeneratedExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = _generator()

    def test_riverside_matches_the_generator(self) -> None:
        rendered = canonical_dumps(self.generator.riverside())
        self.assertEqual(
            rendered, (EXAMPLES / "riverside.json").read_text(encoding="utf-8")
        )

    def test_tiny_matches_the_generator(self) -> None:
        rendered = canonical_dumps(self.generator.tiny())
        self.assertEqual(
            rendered, (EXAMPLES / "tiny.json").read_text(encoding="utf-8")
        )

    def test_the_generator_is_itself_deterministic(self) -> None:
        first = canonical_dumps(self.generator.riverside())
        second = canonical_dumps(self.generator.riverside())
        self.assertEqual(first, second)

    def test_the_commercial_reads_agree_with_the_interval_data(self) -> None:
        document = canonical_loads(
            (EXAMPLES / "riverside.json").read_text(encoding="utf-8")
        )
        series = next(
            entry for entry in document["series"] if entry["channel_id"] == "ch-1003"
        )
        reads = [
            entry
            for entry in document["reads"]
            if entry["register_id"] == "rg-1004"
        ]
        from decimal import Decimal

        interval_total = sum(
            (Decimal(value) for value in series["values"] if value is not None),
            Decimal("0"),
        )
        register_total = Decimal(reads[-1]["value"]) - Decimal(reads[0]["value"])
        self.assertLess(abs(interval_total - register_total), Decimal("6"))


class ExampleBehaviourTests(unittest.TestCase):
    def test_riverside_bills_every_service_point(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        invoices = session.rate_all().value
        billed = {invoice.service_point_id for invoice in invoices}
        self.assertEqual(billed, {"sp-100", "sp-200", "sp-300", "sp-400"})

    def test_riverside_rates_without_errors(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        outcome = session.rate_all()
        self.assertFalse(outcome.diagnostics.has_errors)

    def test_the_examples_rate_under_every_preset(self) -> None:
        for name in preset_names():
            for example in ("tiny", "riverside"):
                session = Session.of(
                    load_dataset(EXAMPLES / f"{example}.json"), preset(name)
                )
                outcome = session.rate_all()
                self.assertTrue(outcome.value, f"{name}/{example}")

    def test_the_solar_customer_earns_a_credit(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        invoices = [
            invoice
            for invoice in session.rate_all().value
            if invoice.service_point_id == "sp-200"
        ]
        self.assertTrue(any("nem.export" in invoice.codes() for invoice in invoices))

    def test_the_commercial_customer_is_billed_on_demand(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        invoices = [
            invoice
            for invoice in session.rate_all().value
            if invoice.service_point_id == "sp-300"
        ]
        self.assertTrue(any("gs.demand" in invoice.codes() for invoice in invoices))

    def test_the_exchanged_meter_still_bills_usage(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        invoices = [
            invoice
            for invoice in session.rate_all().value
            if invoice.service_point_id == "sp-400"
        ]
        self.assertTrue(all(invoice.determinant("energy.total") for invoice in invoices))

    def test_the_rate_change_reaches_the_later_bills(self) -> None:
        session = Session.of(load_dataset(EXAMPLES / "riverside.json"))
        invoices = [
            invoice
            for invoice in session.rate_all().value
            if invoice.service_point_id == "sp-100"
        ]
        rates = {
            line.rate
            for invoice in invoices
            for line in invoice.lines
            if line.code == "res.energy.1"
        }
        self.assertGreater(len(rates), 1)


if __name__ == "__main__":
    unittest.main()
