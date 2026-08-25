"""Rendering: bills, explanations, meter data and CSV."""

from __future__ import annotations

import unittest

from meterline.core.diagnostics import DiagnosticBag, Severity
from meterline.core.tables import Column, Table, render_table
from meterline.core.text import (
    align,
    bullet,
    columns,
    dedent_block,
    ellipsis,
    format_decimal,
    heading,
    indent,
    plural,
    titlecase,
    wrap,
)
from meterline.meterdata.derive import derive_consumption
from meterline.report.csvout import lines_to_csv, meterdata_to_csv, summary_to_csv, to_csv
from meterline.report.diagnostics_text import render_diagnostics, summary_line
from meterline.report.explain import explain_invoice, explain_line
from meterline.report.invoice_text import (
    class_breakdown,
    render_invoice,
    render_invoice_compact,
    taxes_table,
)
from meterline.report.meterdata_text import render_consumption, render_reads, render_series
from meterline.session import Session

from tests.support import attach_channel, build_dataset, flat_series, zone


class TextHelperTests(unittest.TestCase):
    def test_alignment(self) -> None:
        self.assertEqual(align("ab", 5), "ab   ")
        self.assertEqual(align("ab", 5, "right"), "   ab")
        self.assertEqual(align("ab", 6, "center"), "  ab  ")

    def test_truncation_marks_the_cut(self) -> None:
        self.assertTrue(ellipsis("abcdefgh", 4).endswith("…"))
        self.assertEqual(ellipsis("abc", 10), "abc")
        self.assertEqual(ellipsis("abc", 0), "")

    def test_wrapping_does_not_break_words(self) -> None:
        lines = wrap("one two three four five", 9)
        self.assertTrue(all(len(line) <= 9 for line in lines))
        self.assertEqual(" ".join(lines), "one two three four five")

    def test_wrapping_nothing_gives_nothing(self) -> None:
        self.assertEqual(wrap("   "), [])

    def test_indent_leaves_blank_lines_alone(self) -> None:
        self.assertEqual(indent("a\n\nb", 2), "  a\n\n  b")

    def test_dedent_removes_the_common_prefix(self) -> None:
        self.assertEqual(dedent_block("    a\n      b"), "a\n  b")

    def test_plurals(self) -> None:
        self.assertEqual(plural(1, "day"), "1 day")
        self.assertEqual(plural(2, "day"), "2 days")

    def test_titlecase_expands_underscores(self) -> None:
        self.assertEqual(titlecase("peak_summer"), "Peak Summer")

    def test_decimal_formatting_is_fixed_width(self) -> None:
        self.assertEqual(format_decimal("1.005", 2), "1.01")

    def test_bullets_and_columns(self) -> None:
        self.assertIn("- a", bullet(["a", "b"]))
        self.assertEqual(columns([["a", "bb"], ["ccc", "d"]])[0], "a    bb")

    def test_headings_underline_the_title(self) -> None:
        self.assertEqual(heading("Bill"), "Bill\n====")


class TableTests(unittest.TestCase):
    def test_columns_size_to_their_widest_cell(self) -> None:
        table = Table((Column("a", "a"), Column("b", "b")))
        table.add(a="xxxx", b="y")
        rendered = table.render()
        self.assertIn("xxxx", rendered[-1])

    def test_a_fixed_width_column_truncates(self) -> None:
        table = Table((Column("a", "a", width=3),))
        table.add(a="abcdef")
        self.assertEqual(table.render()[-1].strip(), "ab…")

    def test_an_empty_table_still_has_a_header(self) -> None:
        table = Table((Column("a", "header"),))
        self.assertTrue(table.is_empty)
        self.assertIn("header", table.to_text())

    def test_a_title_is_rendered_first(self) -> None:
        table = Table((Column("a", "a"),), title="things")
        self.assertEqual(table.render()[0], "things")

    def test_the_helper_renders_in_one_call(self) -> None:
        rendered = render_table([Column("a", "A")], [{"a": "1"}])
        self.assertIn("A", rendered)


class InvoiceRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = build_dataset(steps=(450, 620, 380), jurisdiction="")
        self.session = Session.of(self.dataset)
        self.invoices = self.session.rate_all().value
        self.zone = zone()

    def test_a_bill_renders_its_header_and_total(self) -> None:
        rendered = render_invoice(self.invoices[0], self.zone)
        self.assertIn("service point   sp-1", rendered)
        self.assertIn("total due", rendered)

    def test_every_line_appears(self) -> None:
        rendered = render_invoice(self.invoices[0], self.zone)
        for line in self.invoices[0].ordered_lines():
            self.assertIn(line.code, rendered)

    def test_the_compact_form_is_one_line(self) -> None:
        self.assertNotIn("\n", render_invoice_compact(self.invoices[0]))

    def test_rendering_is_stable(self) -> None:
        first = render_invoice(self.invoices[0], self.zone)
        second = render_invoice(self.invoices[0], self.zone)
        self.assertEqual(first, second)

    def test_the_class_breakdown_covers_the_classes_present(self) -> None:
        table = class_breakdown(self.invoices[0])
        self.assertEqual(len(table.rows), len(self.invoices[0].by_class()))

    def test_a_bill_with_no_tax_has_an_empty_tax_table(self) -> None:
        self.assertTrue(taxes_table(self.invoices[0]).is_empty)


class ExplainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.invoice = Session.of(build_dataset(steps=(700,))).rate_all().value[0]

    def test_every_line_is_explained(self) -> None:
        rendered = explain_invoice(self.invoice, zone())
        for line in self.invoice.ordered_lines():
            self.assertIn(line.code, rendered)

    def test_the_working_is_shown(self) -> None:
        line = self.invoice.line("energy.1")
        rendered = explain_line(line)
        self.assertIn("working:", rendered)
        self.assertIn("block rate", rendered)

    def test_determinants_are_listed(self) -> None:
        rendered = explain_invoice(self.invoice, zone())
        self.assertIn("energy.total", rendered)

    def test_the_explanation_ends_with_the_total(self) -> None:
        rendered = explain_invoice(self.invoice, zone()).strip()
        self.assertTrue(rendered.endswith(self.invoice.currency))


class MeterDataRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = build_dataset(steps=(450, 620, 380))
        self.zone = zone()
        cycles = self.dataset.cycles_of("sp-1")
        self.span = type(cycles[0].span)(cycles[0].span.start, cycles[-1].span.end)
        register = self.dataset.meters["mt-1"].registers[0]
        reads = self.dataset.reads_around("mt-1", "rg-1", self.span)
        self.reads = reads
        self.records = derive_consumption(
            register, reads, self.span, self.dataset.profile
        ).value

    def test_reads_render_in_local_time(self) -> None:
        rendered = render_reads(self.reads, self.zone)
        self.assertIn("local time", rendered)
        self.assertIn("rg-1", rendered)

    def test_consumption_renders_a_daily_rate(self) -> None:
        rendered = render_consumption(self.records, self.zone)
        self.assertIn("per day", rendered)

    def test_a_series_renders_its_head_and_total(self) -> None:
        series = flat_series("ch-1", self.span.start, 48)
        attach_channel(self.dataset, series)
        rendered = render_series(series, self.zone, limit=5)
        self.assertIn("further intervals", rendered)
        self.assertIn("total:", rendered)


class CsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.invoices = Session.of(build_dataset(steps=(450,))).rate_all().value

    def test_fields_with_commas_are_quoted(self) -> None:
        rendered = to_csv(["a"], [["x,y"]])
        self.assertIn('"x,y"', rendered)

    def test_quotes_are_doubled(self) -> None:
        rendered = to_csv(["a"], [['say "hi"']])
        self.assertIn('""hi""', rendered)

    def test_line_endings_are_unix(self) -> None:
        rendered = lines_to_csv(self.invoices[0])
        self.assertNotIn("\r", rendered)
        self.assertTrue(rendered.endswith("\n"))

    def test_a_row_per_line_item_plus_a_header(self) -> None:
        rendered = lines_to_csv(self.invoices[0])
        self.assertEqual(
            len(rendered.strip().split("\n")), len(self.invoices[0].lines) + 1
        )

    def test_the_summary_has_a_row_per_bill(self) -> None:
        rendered = summary_to_csv(self.invoices)
        self.assertEqual(len(rendered.strip().split("\n")), len(self.invoices) + 1)

    def test_meter_data_csv_renders_local_times(self) -> None:
        dataset = build_dataset(steps=(450,))
        register = dataset.meters["mt-1"].registers[0]
        cycle = dataset.cycles_of("sp-1")[0]
        records = derive_consumption(
            register,
            dataset.reads_around("mt-1", "rg-1", cycle.span),
            cycle.span,
            dataset.profile,
        ).value
        rendered = meterdata_to_csv(records, zone())
        self.assertIn("start,end,register", rendered)


class DiagnosticRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bag = DiagnosticBag()
        self.bag.emit("a.code", "something", Severity.WARNING, "sp-1", detail="x")

    def test_an_empty_bag_says_so(self) -> None:
        self.assertEqual(render_diagnostics(DiagnosticBag()), "no diagnostics")

    def test_the_table_form_lists_the_code(self) -> None:
        self.assertIn("a.code", render_diagnostics(self.bag))

    def test_the_detailed_form_shows_the_context(self) -> None:
        rendered = render_diagnostics(self.bag, detail=True)
        self.assertIn("detail: x", rendered)

    def test_filtering_by_severity(self) -> None:
        self.assertEqual(
            render_diagnostics(self.bag, minimum=Severity.ERROR), "no diagnostics"
        )

    def test_the_summary_line_counts_by_severity(self) -> None:
        self.assertEqual(summary_line(self.bag), "1 warning")
        self.assertEqual(summary_line(DiagnosticBag()), "no diagnostics")


if __name__ == "__main__":
    unittest.main()
