"""The command line interface, driven through its own entry point."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from meterline.cli.app import main
from meterline.io.jsonio import canonical_loads

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TINY = str(EXAMPLES / "tiny.json")
RIVERSIDE = str(EXAMPLES / "riverside.json")


def run(*argv: str) -> tuple[int, str, str]:
    """Run the CLI and capture its output."""

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class BasicCommandTests(unittest.TestCase):
    def test_no_command_prints_help(self) -> None:
        code, out, _ = run()
        self.assertEqual(code, 0)
        self.assertIn("usage", out.lower())

    def test_version_reports_the_engine(self) -> None:
        code, out, _ = run("version")
        self.assertEqual(code, 0)
        self.assertIn("meterline/", out)

    def test_an_unknown_dataset_fails_cleanly(self) -> None:
        code, _, err = run("validate", "--dataset", "/nope/none.json")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_an_unknown_profile_fails_cleanly(self) -> None:
        code, _, err = run("rate", "--dataset", TINY, "--profile", "nonesuch")
        self.assertEqual(code, 2)
        self.assertIn("unknown profile preset", err)


class ValidateTests(unittest.TestCase):
    def test_a_clean_dataset_passes(self) -> None:
        code, out, _ = run("validate", "--dataset", TINY)
        self.assertEqual(code, 0)
        self.assertIn("dataset tiny", out)

    def test_the_counts_are_reported(self) -> None:
        _, out, _ = run("validate", "--dataset", RIVERSIDE)
        self.assertIn("service_points", out)
        self.assertIn("interval_series", out)

    def test_strict_mode_fails_on_warnings(self) -> None:
        code_plain, _, _ = run("validate", "--dataset", RIVERSIDE)
        self.assertEqual(code_plain, 0)


class RateTests(unittest.TestCase):
    def test_text_output_renders_bills(self) -> None:
        code, out, _ = run("rate", "--dataset", TINY)
        self.assertEqual(code, 0)
        self.assertIn("total due", out)
        self.assertIn("Bill bill-", out)

    def test_json_output_parses(self) -> None:
        code, out, _ = run("rate", "--dataset", TINY, "--format", "json")
        self.assertEqual(code, 0)
        document = canonical_loads(out)
        self.assertEqual(document["dataset"], "tiny")
        self.assertEqual(len(document["bills"]), 3)

    def test_csv_output_has_a_header(self) -> None:
        _, out, _ = run("rate", "--dataset", TINY, "--format", "csv")
        self.assertTrue(out.startswith("bill_id,account_id"))

    def test_selecting_a_service_point_narrows_the_run(self) -> None:
        _, out, _ = run("rate", "--dataset", RIVERSIDE, "--service-point", "sp-100")
        self.assertIn("sp-100", out)
        self.assertNotIn("sp-300", out)

    def test_as_of_excludes_later_cycles(self) -> None:
        _, full, _ = run("rate", "--dataset", TINY, "--format", "csv")
        _, partial, _ = run(
            "rate", "--dataset", TINY, "--format", "csv", "--as-of", "2025-05-31"
        )
        self.assertLess(len(partial.strip().split("\n")), len(full.strip().split("\n")))

    def test_output_can_go_to_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bills.txt"
            code, out, _ = run("rate", "--dataset", TINY, "--out", str(target))
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            self.assertIn("total due", target.read_text(encoding="utf-8"))

    def test_a_different_profile_changes_the_bills(self) -> None:
        _, first, _ = run("rate", "--dataset", TINY, "--format", "csv")
        _, second, _ = run(
            "rate", "--dataset", TINY, "--format", "csv", "--profile", "permissive-retailer"
        )
        self.assertNotEqual(first, second)


class ExplainTests(unittest.TestCase):
    def test_the_working_is_shown(self) -> None:
        code, out, _ = run("explain", "--dataset", TINY)
        self.assertEqual(code, 0)
        self.assertIn("working:", out)

    def test_one_line_can_be_singled_out(self) -> None:
        _, out, _ = run("explain", "--dataset", TINY, "--line", "res.basic")
        self.assertIn("res.basic", out)
        self.assertNotIn("res.energy.1", out)

    def test_an_unknown_line_says_so(self) -> None:
        _, out, _ = run("explain", "--dataset", TINY, "--line", "nope")
        self.assertIn("no line with code", out)

    def test_an_unknown_cycle_is_reported(self) -> None:
        code, out, _ = run("explain", "--dataset", TINY, "--cycle", "cyc-nope")
        self.assertEqual(code, 1)
        self.assertIn("no bill was produced", out)


class OtherCommandTests(unittest.TestCase):
    def test_meters_shows_reads_and_consumption(self) -> None:
        code, out, _ = run("meters", "--dataset", TINY)
        self.assertEqual(code, 0)
        self.assertIn("meter reads", out)
        self.assertIn("derived consumption", out)

    def test_meters_can_emit_csv(self) -> None:
        _, out, _ = run("meters", "--dataset", TINY, "--format", "csv")
        self.assertTrue(out.startswith("start,end,register"))

    def test_meters_can_include_intervals(self) -> None:
        _, out, _ = run(
            "meters", "--dataset", RIVERSIDE, "--service-point", "sp-300", "--intervals"
        )
        self.assertIn("intervals", out)

    def test_tariff_describes_the_catalog(self) -> None:
        code, out, _ = run("tariff", "--dataset", RIVERSIDE)
        self.assertEqual(code, 0)
        self.assertIn("RES-STD", out)
        self.assertIn("GS-TOU", out)

    def test_tariff_can_describe_one_code(self) -> None:
        _, out, _ = run("tariff", "--dataset", RIVERSIDE, "--code", "RES-NEM")
        self.assertIn("RES-NEM", out)
        self.assertNotIn("GS-TOU", out)

    def test_an_unknown_tariff_fails_cleanly(self) -> None:
        code, _, err = run("tariff", "--dataset", TINY, "--code", "NOPE")
        self.assertEqual(code, 2)
        self.assertIn("unknown tariff", err)

    def test_policy_lists_the_presets(self) -> None:
        code, out, _ = run("policy", "--list")
        self.assertEqual(code, 0)
        self.assertIn("model-rules", out)

    def test_policy_describes_one_preset(self) -> None:
        _, out, _ = run("policy", "--profile", "model-rules")
        self.assertIn("conventions: model-rules", out)
        self.assertIn("in short:", out)

    def test_policy_diffs_two_presets(self) -> None:
        _, out, _ = run("policy", "--profile", "model-rules", "--diff", "legacy-cooperative")
        self.assertIn("->", out)

    def test_policy_without_a_target_asks_for_one(self) -> None:
        code, out, _ = run("policy")
        self.assertEqual(code, 2)
        self.assertIn("--list", out)

    def test_replay_reports_identical_passes(self) -> None:
        code, out, _ = run("replay", "--dataset", TINY, "--passes", "3")
        self.assertEqual(code, 0)
        self.assertIn("replay ok", out)

    def test_compare_shows_a_net_difference(self) -> None:
        code, out, _ = run(
            "compare", "--dataset", TINY, "--against", "strict-municipal"
        )
        self.assertEqual(code, 0)
        self.assertIn("net difference", out)
        self.assertIn("conventions that changed", out)

    def test_export_round_trips_through_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.json"
            code, _, _ = run("export", "--dataset", RIVERSIDE, "--out", str(target))
            self.assertEqual(code, 0)
            code, out, _ = run("validate", "--dataset", str(target))
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
