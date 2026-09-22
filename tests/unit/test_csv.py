"""CSV / TSV の入出力：セルの型の読み取り、引用符、エラー、書き出し。"""

from __future__ import annotations

import csv
import io
import json
import random
from typing import Any

import pytest
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


class ReadTests:
    def test_header_and_rows_become_a_list_of_maps(self) -> None:
        assert read("name,n\nGary,1\nAnn,2\n") == [{"name": "Gary", "n": 1}, {"name": "Ann", "n": 2}]

    def test_cells_are_typed_like_yaml_values(self) -> None:
        row = read("a,b,c,d,e,f\n1,1.5,true,null,,text\n")[0]
        assert row == {"a": 1, "b": 1.5, "c": True, "d": None, "e": None, "f": "text"}

    def test_a_cell_can_hold_yaml(self) -> None:
        row = read("facts,list\n\"cool: true\",\"[1, 2]\"\n")[0]
        assert row == {"facts": {"cool": True}, "list": [1, 2]}

    def test_auto_parse_off_keeps_structures_as_text(self) -> None:
        row = read("n,facts\n1,\"cool: true\"\n", auto_parse=False)[0]
        assert row == {"n": 1, "facts": "cool: true"}

    def test_tsv(self) -> None:
        assert read("a\tb\n1\tx y\n", "tsv") == [{"a": 1, "b": "x y"}]
        assert read("a\tb\n{c: 1}\tx\n", "tsv", tsv_auto_parse=False) == [{"a": "{c: 1}", "b": "x"}]

    def test_custom_separator(self) -> None:
        assert read("a;b\n1;2\n", separator=";") == [{"a": 1, "b": 2}]

    def test_quoted_cells(self) -> None:
        text = 'a,b\n"x, y","say ""hi"""\n"line1\nline2",z\n'
        assert read(text) == [{"a": "x, y", "b": 'say "hi"'},
                            {"a": "line1\nline2", "b": "z"}]

    def test_bom_crlf_and_blank_lines(self) -> None:
        assert read("﻿a,b\r\n\r\n1,2\r\n\r\n3,4") == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    def test_last_row_may_lack_the_final_newline(self) -> None:
        assert read("a\n1") == [{"a": 1}]
        assert read("a,b\n1,") == [{"a": 1, "b": None}]

    def test_header_only_is_an_empty_list(self) -> None:
        assert read("a,b\n") == []

    def test_empty_input_has_no_document(self) -> None:
        assert list(CsvDecoder().decode_documents("")) == []
        assert list(CsvDecoder().decode_documents("\n\n")) == []

    def test_a_string_that_looks_like_a_number_stays_a_number(self) -> None:
        assert read("a\n007\n")[0]["a"] == 7      # read as a YAML value, as in the Go yq

    def test_duplicate_headers_are_kept(self) -> None:
        options = Options(input_format="csv", output_format="yaml")
        assert yaqpy.evaluate(".", "a,a\n1,2\n", options=options) == "- a: 1\n  a: 2\n"

    def test_comment_only_cell(self) -> None:
        options = Options(input_format="csv", output_format="yaml")
        assert yaqpy.evaluate(".", "v\n#ffff\n", options=options) == "- v: #ffff\n"


class ReadErrorTests:
    def check(self, text: str, message: str) -> None:
        with pytest.raises(FormatError) as ctx:
            read(text)
        assert message in str(ctx.value)

    def test_wrong_number_of_fields(self) -> None:
        self.check("a,b\n1,2\n3\n", "record on line 3: wrong number of fields")

    def test_bare_quote(self) -> None:
        self.check('a\nx"y\n', 'parse error on line 2, column 2: bare " in non-quoted field')

    def test_unterminated_quote(self) -> None:
        self.check('a\n"x\n', 'extraneous or missing " in quoted-field')

    def test_text_after_the_closing_quote(self) -> None:
        self.check('a,b\n"x"y,2\n', 'extraneous or missing " in quoted-field')

    def test_error_names_the_file(self) -> None:
        with pytest.raises(FormatError) as ctx:
            list(CsvDecoder().decode_documents("a,b\n1\n", filename="x.csv"))
        assert str(ctx.value).startswith("bad file 'x.csv': ")

    def test_bad_separator(self) -> None:
        with pytest.raises(FormatError):
            list(read_records("a\n", '"'))
        with pytest.raises(ValueError):
            CsvOptions(separator="ab")

    def test_input_size_limit(self) -> None:
        from yaqpy import Limits

        options = Options(input_format="csv", limits=Limits(max_input_bytes=5))
        with pytest.raises(FormatError):
            yaqpy.evaluate(".", "a,b\n1,2222\n", options=options)


class CellTypingTests:
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
            fast = decoder._snippet(cell)
            if cell == "":
                assert (fast.tag, fast.value) == ("!!null", "")
                continue
            try:
                docs = list(YamlDecoder(Options()).decode_documents(cell, process_leading=True))
            except FormatError:
                docs = []
            slow = docs[0] if docs else None
            if slow is not None and slow.tag == "!!str":
                slow = Node(Kind.SCALAR, tag="!!str", value=cell)      # parseSnippet keeps the text
            if slow is None:
                assert fast is None
                continue
            assert (fast.kind, fast.tag, fast.value) == (slow.kind, slow.tag, slow.value)
            if fast.kind is Kind.SCALAR:
                assert fast.style == slow.style


class WriteTests:
    def test_list_of_scalars_is_one_row(self) -> None:
        assert write("[a, b, c]\n") == "a,b,c\n"

    def test_list_of_lists(self) -> None:
        assert write("- [i, like, csv]\n- [because, excel, is, cool]\n") == "i,like,csv\nbecause,excel,is,cool\n"

    def test_list_of_maps_uses_the_first_map_for_the_header(self) -> None:
        text = "- {a: 1, b: x}\n- {b: y}\n- {a: 3, b: z, c: dropped}\n"
        assert write(text) == "a,b\n1,x\n,y\n3,z\n"

    def test_tsv(self) -> None:
        assert write("- [a, b]\n- [c d, e]\n", "tsv") == "a\tb\nc d\te\n"

    def test_custom_separator(self) -> None:
        assert write("[a, b]\n", separator=";") == "a;b\n"

    def test_empty_list_writes_nothing(self) -> None:
        assert write("[]\n") == ""

    def test_scalar_is_printed_as_is(self) -> None:
        assert write("hello\n") == "hello\n"

    def test_quoting(self) -> None:
        assert format_row(["a", "b,c", 'say "hi"', "x\ny", " lead", "", "\\."], ",") == 'a,"b,c","say ""hi""","x\ny"," lead",,"\\."\n'
        assert format_row(["a b", "c\td"], "\t") == 'a b\t"c\td"\n'
        assert format_row(["a,b"], "\t") == "a,b\n"          # only the separator matters

    def test_nested_values_are_refused(self) -> None:
        for text in ("[[1], 2]\n", "- {a: [1]}\n", "[{a: 1}, 2]\n", "[a, [b]]\n"):
            with pytest.raises(FormatError):
                write(text)

    def test_a_map_at_the_top_is_refused(self) -> None:
        with pytest.raises(FormatError) as ctx:
            write("a: 1\n")
        assert str(ctx.value) == "csv encoding only works for arrays, got: !!map"

    def test_round_trip(self) -> None:
        text = 'name,note\nAnn,"a, b"\nBob,"say ""hi"""\nCy,"two\nlines"\nDee,\n'
        options = Options(input_format="csv", output_format="csv")
        assert yaqpy.evaluate(".", text, options=options) == text


class AgreesWithCsvModuleTests:
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
                buffer = io.StringIO(newline="")
                csv.writer(buffer, delimiter=separator, lineterminator="\n").writerows(table)
                got = [fields for _, fields in read_records(buffer.getvalue(), separator)]
                assert got == table

    def test_the_csv_module_reads_what_our_writer_writes(self) -> None:
        for separator in (",", "\t"):
            for table in self.tables(11, 150):
                text = "".join(format_row(row, separator) for row in table)
                got = list(csv.reader(io.StringIO(text, newline=""), delimiter=separator,
                                      strict=True))
                assert got == table

    def test_the_two_writers_agree_apart_from_leading_spaces(self) -> None:
        # Go quotes a field that starts with a space; Python does not. Everything else is the same.
        for table in self.tables(13, 100):
            buffer = io.StringIO(newline="")
            csv.writer(buffer, lineterminator="\n").writerows(table)
            ours = "".join(format_row(row, ",") for row in table)
            if not any(cell[:1].isspace() for row in table for cell in row):
                assert ours == buffer.getvalue()

    def test_whole_documents_round_trip_through_the_yaml_view(self) -> None:
        # CSV -> maps -> CSV keeps every cell that is text and does not look like a YAML value
        table = [["name", "note"], ["Ann", 'say "hi", ok'], ["Bob", "two\nlines"], ["Cy", ""]]
        text = "".join(format_row(row, ",") for row in table)
        options = Options(input_format="csv", output_format="csv", csv=CsvOptions(auto_parse=False))
        assert yaqpy.evaluate(".", text, options=options) == text


class CliTests:
    def test_extension_and_alias(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        assert formats.from_filename("a.csv").name == "csv"
        assert formats.from_filename("a.tsv").name == "tsv"
        assert formats.get("c").name == "csv"
        assert formats.get("t").name == "tsv"

    def test_cli(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.csv")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("name;n\nGary;1\n")
            code, out, err = run_cli("--csv-separator", ";", "-o", "json", "-I", "0", ".", path)
            assert (code, json.loads(out), err) == (0, [{"name": "Gary", "n": 1}], "")
            code, out, _ = run_cli("--csv-separator", ";", ".[0].n = 5", path)
            assert out == "name;n\nGary;5\n"
            code, out, err = run_cli("--csv-separator", "ab", ".", path)
            assert code == 1
            assert "Must be length 1" in err

    def test_tsv_option_is_separate(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.tsv")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("a\tb\n{c: 1}\t2\n")
            code, out, _ = run_cli("--tsv-auto-parse=false", "-o", "json", "-I", "0", ".", path)
            assert json.loads(out) == [{"a": "{c: 1}", "b": 2}]
            code, out, _ = run_cli("--csv-auto-parse=false", "-o", "json", "-I", "0", ".", path)
            assert json.loads(out) == [{"a": {"c": 1}, "b": 2}]
