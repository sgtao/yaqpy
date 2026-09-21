"""CSV / TSV の入出力：セルの型の読み取り、引用符、エラー、書き出し。"""

from __future__ import annotations

import csv
import io
import json
import random
import unittest
from typing import Any

import yaqpy
from yaqpy import CsvOptions, FormatError, Options
from yaqpy.cli.main import main
from yaqpy.core.model.node import Kind, Node
from yaqpy.formats.csv_codec import CsvDecoder, format_row, read_records


def read(text: str, fmt: str = "csv", **csv: Any) -> Any:
    options = Options(input_format=fmt, output_format="json", csv=CsvOptions(**csv))
    return json.loads(yaqpy.evaluate(".", text, options=options))


def write(text: str, fmt: str = "csv", **csv: Any) -> str:
    options = Options(input_format="yaml", output_format=fmt, csv=CsvOptions(**csv))
    return yaqpy.evaluate(".", text, options=options)


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ReadTests(unittest.TestCase):
    def test_header_and_rows_become_a_list_of_maps(self) -> None:
        self.assertEqual(read("name,n\nGary,1\nAnn,2\n"),
                         [{"name": "Gary", "n": 1}, {"name": "Ann", "n": 2}])

    def test_cells_are_typed_like_yaml_values(self) -> None:
        row = read("a,b,c,d,e,f\n1,1.5,true,null,,text\n")[0]
        self.assertEqual(row, {"a": 1, "b": 1.5, "c": True, "d": None, "e": None, "f": "text"})

    def test_a_cell_can_hold_yaml(self) -> None:
        row = read("facts,list\n\"cool: true\",\"[1, 2]\"\n")[0]
        self.assertEqual(row, {"facts": {"cool": True}, "list": [1, 2]})

    def test_auto_parse_off_keeps_structures_as_text(self) -> None:
        row = read("n,facts\n1,\"cool: true\"\n", auto_parse=False)[0]
        self.assertEqual(row, {"n": 1, "facts": "cool: true"})

    def test_tsv(self) -> None:
        self.assertEqual(read("a\tb\n1\tx y\n", "tsv"), [{"a": 1, "b": "x y"}])
        self.assertEqual(read("a\tb\n{c: 1}\tx\n", "tsv", tsv_auto_parse=False),
                         [{"a": "{c: 1}", "b": "x"}])

    def test_custom_separator(self) -> None:
        self.assertEqual(read("a;b\n1;2\n", separator=";"), [{"a": 1, "b": 2}])

    def test_quoted_cells(self) -> None:
        text = 'a,b\n"x, y","say ""hi"""\n"line1\nline2",z\n'
        self.assertEqual(read(text), [{"a": "x, y", "b": 'say "hi"'},
                                      {"a": "line1\nline2", "b": "z"}])

    def test_bom_crlf_and_blank_lines(self) -> None:
        self.assertEqual(read("﻿a,b\r\n\r\n1,2\r\n\r\n3,4"), [{"a": 1, "b": 2}, {"a": 3, "b": 4}])

    def test_last_row_may_lack_the_final_newline(self) -> None:
        self.assertEqual(read("a\n1"), [{"a": 1}])
        self.assertEqual(read("a,b\n1,"), [{"a": 1, "b": None}])

    def test_header_only_is_an_empty_list(self) -> None:
        self.assertEqual(read("a,b\n"), [])

    def test_empty_input_has_no_document(self) -> None:
        self.assertEqual(list(CsvDecoder().decode_documents("")), [])
        self.assertEqual(list(CsvDecoder().decode_documents("\n\n")), [])

    def test_a_string_that_looks_like_a_number_stays_a_number(self) -> None:
        self.assertEqual(read("a\n007\n")[0]["a"], 7)      # read as a YAML value, as in the Go yq

    def test_duplicate_headers_are_kept(self) -> None:
        options = Options(input_format="csv", output_format="yaml")
        self.assertEqual(yaqpy.evaluate(".", "a,a\n1,2\n", options=options), "- a: 1\n  a: 2\n")

    def test_comment_only_cell(self) -> None:
        options = Options(input_format="csv", output_format="yaml")
        self.assertEqual(yaqpy.evaluate(".", "v\n#ffff\n", options=options), "- v: #ffff\n")


class ReadErrorTests(unittest.TestCase):
    def check(self, text: str, message: str) -> None:
        with self.assertRaises(FormatError) as ctx:
            read(text)
        self.assertIn(message, str(ctx.exception))

    def test_wrong_number_of_fields(self) -> None:
        self.check("a,b\n1,2\n3\n", "record on line 3: wrong number of fields")

    def test_bare_quote(self) -> None:
        self.check('a\nx"y\n', 'parse error on line 2, column 2: bare " in non-quoted field')

    def test_unterminated_quote(self) -> None:
        self.check('a\n"x\n', 'extraneous or missing " in quoted-field')

    def test_text_after_the_closing_quote(self) -> None:
        self.check('a,b\n"x"y,2\n', 'extraneous or missing " in quoted-field')

    def test_error_names_the_file(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            list(CsvDecoder().decode_documents("a,b\n1\n", filename="x.csv"))
        self.assertTrue(str(ctx.exception).startswith("bad file 'x.csv': "))

    def test_bad_separator(self) -> None:
        with self.assertRaises(FormatError):
            list(read_records("a\n", '"'))
        with self.assertRaises(ValueError):
            CsvOptions(separator="ab")

    def test_input_size_limit(self) -> None:
        from yaqpy import Limits

        options = Options(input_format="csv", limits=Limits(max_input_bytes=5))
        with self.assertRaises(FormatError):
            yaqpy.evaluate(".", "a,b\n1,2222\n", options=options)


class CellTypingTests(unittest.TestCase):
    """The fast path for plain cells must give exactly what the YAML parser gives."""

    CELLS = [
        "", "0", "1", "-1", "+1", "007", "0x1F", "0o17", "1e3", "1_000", ".5", "-.5", "+.5", "1.", "1.5",
        ".inf", "-.inf", ".nan", "true", "True", "TRUE", "false", "yes", "no", "on", "off", "y", "n",
        "null", "Null", "NULL", "~", "-", "--", "---", "...", "+", ".", "a", "abc", "Abc_def", "a-b",
        "a.b", "a b", "a  b", "hello world", "Samantha's Rabbit", "x,y", "a(b)", "a/b", "2001-12-14",
        "2001-12-14t21:59:43.10-05:00", "12:30:45", "1:20", "0b101", "1,000", "a'b", "'a", "a'",
        "a ", " a", "a b ", "true story", "null pointer", "a+b", "a-", "1-2", "3.14.15", "1e", "e1",
        "_a", "a_", "İstanbul", "日本語", "a:b", "a: b", "a #b", "a#b", "- a", "? a", ": a", "[a]", "{a}",
        "&a", "*a", "!a", "|a", ">a", "%a", "@a", "`a", "\"a\"", "'a'",
    ]

    def test_fast_path_matches_the_yaml_parser(self) -> None:
        from yaqpy.formats.yaml.codec import YamlDecoder

        decoder = CsvDecoder(Options())
        for cell in self.CELLS:
            with self.subTest(cell=cell):
                fast = decoder._snippet(cell)
                if cell == "":
                    self.assertEqual((fast.tag, fast.value), ("!!null", ""))
                    continue
                try:
                    docs = list(YamlDecoder(Options()).decode_documents(cell, process_leading=True))
                except FormatError:
                    docs = []
                slow = docs[0] if docs else None
                if slow is not None and slow.tag == "!!str":
                    slow = Node(Kind.SCALAR, tag="!!str", value=cell)      # parseSnippet keeps the text
                if slow is None:
                    self.assertIsNone(fast)
                    continue
                self.assertEqual((fast.kind, fast.tag, fast.value), (slow.kind, slow.tag, slow.value))
                if fast.kind is Kind.SCALAR:
                    self.assertEqual(fast.style, slow.style)


class WriteTests(unittest.TestCase):
    def test_list_of_scalars_is_one_row(self) -> None:
        self.assertEqual(write("[a, b, c]\n"), "a,b,c\n")

    def test_list_of_lists(self) -> None:
        self.assertEqual(write("- [i, like, csv]\n- [because, excel, is, cool]\n"),
                         "i,like,csv\nbecause,excel,is,cool\n")

    def test_list_of_maps_uses_the_first_map_for_the_header(self) -> None:
        text = "- {a: 1, b: x}\n- {b: y}\n- {a: 3, b: z, c: dropped}\n"
        self.assertEqual(write(text), "a,b\n1,x\n,y\n3,z\n")

    def test_tsv(self) -> None:
        self.assertEqual(write("- [a, b]\n- [c d, e]\n", "tsv"), "a\tb\nc d\te\n")

    def test_custom_separator(self) -> None:
        self.assertEqual(write("[a, b]\n", separator=";"), "a;b\n")

    def test_empty_list_writes_nothing(self) -> None:
        self.assertEqual(write("[]\n"), "")

    def test_scalar_is_printed_as_is(self) -> None:
        self.assertEqual(write("hello\n"), "hello\n")

    def test_quoting(self) -> None:
        self.assertEqual(format_row(["a", "b,c", 'say "hi"', "x\ny", " lead", "", "\\."], ","),
                         'a,"b,c","say ""hi""","x\ny"," lead",,"\\."\n')
        self.assertEqual(format_row(["a b", "c\td"], "\t"), 'a b\t"c\td"\n')
        self.assertEqual(format_row(["a,b"], "\t"), "a,b\n")          # only the separator matters

    def test_nested_values_are_refused(self) -> None:
        for text in ("[[1], 2]\n", "- {a: [1]}\n", "[{a: 1}, 2]\n", "[a, [b]]\n"):
            with self.subTest(text=text), self.assertRaises(FormatError):
                write(text)

    def test_a_map_at_the_top_is_refused(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            write("a: 1\n")
        self.assertEqual(str(ctx.exception), "csv encoding only works for arrays, got: !!map")

    def test_round_trip(self) -> None:
        text = 'name,note\nAnn,"a, b"\nBob,"say ""hi"""\nCy,"two\nlines"\nDee,\n'
        options = Options(input_format="csv", output_format="csv")
        self.assertEqual(yaqpy.evaluate(".", text, options=options), text)


class AgreesWithCsvModuleTests(unittest.TestCase):
    """Random tables, written by one side and read by the other (Python's csv module vs ours)."""

    ALPHABET = ["a", "b", "x y", " lead", "trail ", ",", ";", '"', "'", "\n", "\t", "日本", "é", "1", ""]

    def tables(self, seed: int, count: int, columns: tuple[int, int] = (2, 5)) -> list[list[list[str]]]:
        rng = random.Random(seed)
        out = []
        for _ in range(count):
            width = rng.randint(*columns)
            rows = [["".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 4)))
                     for _ in range(width)] for _ in range(rng.randint(1, 6))]
            out.append(rows)
        return out

    def test_our_reader_reads_what_the_csv_module_writes(self) -> None:
        for separator in (",", ";", "\t", "|"):
            for table in self.tables(7, 150):
                with self.subTest(separator=separator, table=table):
                    buffer = io.StringIO(newline="")
                    csv.writer(buffer, delimiter=separator, lineterminator="\n").writerows(table)
                    got = [fields for _, fields in read_records(buffer.getvalue(), separator)]
                    self.assertEqual(got, table)

    def test_the_csv_module_reads_what_our_writer_writes(self) -> None:
        for separator in (",", "\t"):
            for table in self.tables(11, 150):
                with self.subTest(separator=separator, table=table):
                    text = "".join(format_row(row, separator) for row in table)
                    got = list(csv.reader(io.StringIO(text, newline=""), delimiter=separator,
                                          strict=True))
                    self.assertEqual(got, table)

    def test_the_two_writers_agree_apart_from_leading_spaces(self) -> None:
        # Go quotes a field that starts with a space; Python does not. Everything else is the same.
        for table in self.tables(13, 100):
            with self.subTest(table=table):
                buffer = io.StringIO(newline="")
                csv.writer(buffer, lineterminator="\n").writerows(table)
                ours = "".join(format_row(row, ",") for row in table)
                if not any(cell[:1].isspace() for row in table for cell in row):
                    self.assertEqual(ours, buffer.getvalue())

    def test_whole_documents_round_trip_through_the_yaml_view(self) -> None:
        # CSV -> maps -> CSV keeps every cell that is text and does not look like a YAML value
        table = [["name", "note"], ["Ann", 'say "hi", ok'], ["Bob", "two\nlines"], ["Cy", ""]]
        text = "".join(format_row(row, ",") for row in table)
        options = Options(input_format="csv", output_format="csv", csv=CsvOptions(auto_parse=False))
        self.assertEqual(yaqpy.evaluate(".", text, options=options), text)


class CliTests(unittest.TestCase):
    def test_extension_and_alias(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        self.assertEqual(formats.from_filename("a.csv").name, "csv")
        self.assertEqual(formats.from_filename("a.tsv").name, "tsv")
        self.assertEqual(formats.get("c").name, "csv")
        self.assertEqual(formats.get("t").name, "tsv")

    def test_cli(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.csv")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("name;n\nGary;1\n")
            code, out, err = run_cli("--csv-separator", ";", "-o", "json", "-I", "0", ".", path)
            self.assertEqual((code, json.loads(out), err), (0, [{"name": "Gary", "n": 1}], ""))
            code, out, _ = run_cli("--csv-separator", ";", ".[0].n = 5", path)
            self.assertEqual(out, "name;n\nGary;5\n")
            code, out, err = run_cli("--csv-separator", "ab", ".", path)
            self.assertEqual(code, 1)
            self.assertIn("Must be length 1", err)

    def test_tsv_option_is_separate(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.tsv")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("a\tb\n{c: 1}\t2\n")
            code, out, _ = run_cli("--tsv-auto-parse=false", "-o", "json", "-I", "0", ".", path)
            self.assertEqual(json.loads(out), [{"a": "{c: 1}", "b": 2}])
            code, out, _ = run_cli("--csv-auto-parse=false", "-o", "json", "-I", "0", ".", path)
            self.assertEqual(json.loads(out), [{"a": {"c": 1}, "b": 2}])


if __name__ == "__main__":
    unittest.main()
