"""TOML の入出力：値の原文の保持、表の種類（インライン／セクション）、書き出し、エラー、-i の拒否。"""

from __future__ import annotations

import io
import json
import math
import tomllib
import unittest
from pathlib import Path
from typing import Any

import yaqpy
from yaqpy import FormatError, Limits, Options, TomlOptions
from yaqpy.cli.main import main
from yaqpy.core.model.node import Kind, Node
from yaqpy.formats.toml_codec import MAX_DEPTH, TomlDecoder, _key_text, _quote


def load(text: str) -> Node:
    documents = list(TomlDecoder().decode_documents(text))
    return documents[0]


def to_python(node: Node) -> Any:
    """A plain Python value for comparing with ``tomllib`` (numbers and dates from their text)."""
    if node.kind is Kind.MAPPING:
        return {k.value: to_python(v) for k, v in node.map_items()}
    if node.kind is Kind.SEQUENCE:
        return [to_python(v) for v in node.content]
    text = node.value
    if node.tag == "!!int":
        return int(text.replace("_", ""), 0) if text[:2] in ("0x", "0o", "0b") else int(text.replace("_", ""))
    if node.tag == "!!float":
        return float(text.replace("_", ""))
    if node.tag == "!!bool":
        return text == "true"
    return text


def normalise(value: Any) -> Any:
    """What ``tomllib`` returns, reduced to the same plain types."""
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if hasattr(value, "isoformat"):
        return "date"
    return value


def flatten_dates(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: flatten_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [flatten_dates(v) for v in value]
    if isinstance(value, str) and len(value) >= 8 and value[4:5] == "-" and value[7:8] == "-" \
            and value[:4].isdigit():
        return "date"
    return value


def convert(text: str, input_format: str = "toml", output_format: str = "json", **toml: Any) -> str:
    options = Options(input_format=input_format, output_format=output_format, indent=2,
                      toml=TomlOptions(**toml))
    return yaqpy.evaluate(".", text, options=options)


def read(text: str) -> Any:
    return json.loads(convert(text, output_format="json"))


def write(text: str, input_format: str = "yaml") -> str:
    return convert(text, input_format, "toml")


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ScalarTests(unittest.TestCase):
    def test_numbers_keep_their_text(self) -> None:
        node = load("a = 0xDEADBEEF\nb = 1_000\nc = +5\nd = 6.626e-34\ne = 0o17\nf = 0b101\ng = inf\n")
        values = {k.value: (v.tag, v.value) for k, v in node.map_items()}
        self.assertEqual(values, {
            "a": ("!!int", "0xDEADBEEF"), "b": ("!!int", "1_000"), "c": ("!!int", "+5"),
            "d": ("!!float", "6.626e-34"), "e": ("!!int", "0o17"), "f": ("!!int", "0b101"),
            "g": ("!!float", "inf")})

    def test_arithmetic_keeps_the_base(self) -> None:
        options = Options(input_format="toml", output_format="toml")
        self.assertEqual(yaqpy.evaluate(".A += 1", "A = 0xDEADBEEF\n", options=options),
                         "A = 0xDEADBEF0\n")

    def test_booleans_and_dates(self) -> None:
        node = load("t = true\nf = false\nd = 1979-05-27T07:32:00-08:00\nl = 1979-05-27\n"
                    "m = 1979-05-27 07:32:00Z\nn = 07:32:00\n")
        self.assertEqual({k.value: (v.tag, v.value) for k, v in node.map_items()}, {
            "t": ("!!bool", "true"), "f": ("!!bool", "false"),
            "d": ("!!timestamp", "1979-05-27T07:32:00-08:00"), "l": ("!!timestamp", "1979-05-27"),
            "m": ("!!timestamp", "1979-05-27 07:32:00Z"), "n": ("!!str", "07:32:00")})

    def test_strings(self) -> None:
        text = ('a = "tab\\there \\u00e9 \\U0001F600 \\"q\\" \\\\"\n'
                "b = 'C:\\path\\n'\n"
                'c = """\nfirst\n  second \\\n   joined"""\n'
                "d = '''\nraw \\n\nlines'''\n"
                'e = """quotes""""\n')
        self.assertEqual(read(text), {
            "a": 'tab\there é 😀 "q" \\', "b": "C:\\path\\n", "c": "first\n  second joined",
            "d": "raw \\n\nlines", "e": 'quotes"'})

    def test_keys(self) -> None:
        self.assertEqual(read('"a b" = 1\n\'c.d\' = 2\nx . y = 3\n"" = 4\n'),
                         {"a b": 1, "c.d": 2, "x": {"y": 3}, "": 4})


class StructureTests(unittest.TestCase):
    def test_tables_and_arrays_of_tables(self) -> None:
        text = ("var = 1\n[owner.contact]\nname = 'Tom'\n[[owner.addresses]]\nstreet = 'a'\n"
                "[[owner.addresses]]\nstreet = 'b'\n[[owner.addresses.tags]]\nt = 1\n")
        self.assertEqual(read(text), {"var": 1, "owner": {
            "contact": {"name": "Tom"},
            "addresses": [{"street": "a"}, {"street": "b", "tags": [{"t": 1}]}]}})

    def test_a_table_may_come_after_a_table_it_contains(self) -> None:
        self.assertEqual(read("[a.b]\nx = 1\n[a]\ny = 2\n"), {"a": {"b": {"x": 1}, "y": 2}})

    def test_dotted_keys(self) -> None:
        self.assertEqual(read("a.b.c = 1\na.b.d = 2\na.e = 3\n"),
                         {"a": {"b": {"c": 1, "d": 2}, "e": 3}})

    def test_arrays_may_be_mixed_span_lines_and_hold_comments(self) -> None:
        text = 'a = [\n  1, # one\n  "two",\n  [3, 4],\n  { five = 5 },\n]\nb = []\n'
        self.assertEqual(read(text), {"a": [1, "two", [3, 4], {"five": 5}], "b": []})

    def test_inline_tables(self) -> None:
        self.assertEqual(read("t = { a = 1, b.c = 2, d = { e = 3 } }\ne = {}\n"),
                         {"t": {"a": 1, "b": {"c": 2}, "d": {"e": 3}}, "e": {}})

    def test_table_kinds_are_marked_for_the_encoder(self) -> None:
        node = load("i = { a = 1 }\n[t]\nx = 1\n[[l]]\ny = 2\n")
        hints = {k.value: v.encode_hint for k, v in node.map_items()}
        self.assertEqual(hints, {"i": "inline", "t": "block", "l": ""})
        self.assertEqual(node.get_map_value("l").content[0].encode_hint, "block")

    def test_empty_tables_are_empty_maps(self) -> None:
        self.assertEqual(read("[a]\n[b]\nk = 1\n[c]\n"), {"a": {}, "b": {"k": 1}, "c": {}})

    def test_empty_document_has_no_output(self) -> None:
        self.assertEqual(list(TomlDecoder().decode_documents("")), [])
        self.assertEqual(list(TomlDecoder().decode_documents("# only a comment\n\n")), [])

    def test_comments_are_skipped(self) -> None:
        self.assertEqual(read("# c\na = 1 # d\n[t] # e\nb = 2\n"), {"a": 1, "t": {"b": 2}})

    def test_bom_and_crlf(self) -> None:
        self.assertEqual(read("﻿a = 1\r\n[t]\r\nb = \"x\"\r\n"), {"a": 1, "t": {"b": "x"}})


class ErrorTests(unittest.TestCase):
    def check(self, text: str, message: str = "") -> None:
        with self.assertRaises(FormatError) as ctx:
            read(text)
        self.assertIn(message, str(ctx.exception))

    def test_unterminated_string_names_the_line(self) -> None:
        self.check('A = "hello', "unterminated basic string (line 1, column 5)")
        self.check("A = 'x\nB = 1", "unterminated literal string")
        self.check('A = """x', "unterminated multi-line basic string")

    def test_duplicates_and_redefinitions(self) -> None:
        for text in ("a = 1\na = 2\n", "[a]\n[a]\n", "a = 1\n[a]\n", "a.b = 1\n[a]\n",
                     "[a.b]\n[a]\n[a]\n", "a = {x = 1}\n[a]\ny = 2\n", "a = {x = 1}\na.y = 2\n",
                     "[[a]]\n[a]\n", "a = [1]\n[[a]]\n"):
            with self.subTest(text=text), self.assertRaises(FormatError):
                read(text)

    def test_invalid_values(self) -> None:
        for text in ("a = \n", "a = 01\n", "a = 1__0\n", "a = 1.\n", "a = .5\n", "a = tru\n",
                     "a = 1 2\n", "a = [1 2]\n", "a = {b = 1,}\n", "a = {b = 1\n}\n", 'a = "\\q"\n',
                     'a = "\\uD800"\n', 'a = "x\ny"\n', "a = 'x\ty\x01'\n", "a = 2024-13-45x\n",
                     "= 1\n", "a b = 1\n", "[a\n", "[[a]\n", "a = 1 b = 2\n"):
            with self.subTest(text=text), self.assertRaises(FormatError):
                read(text)

    def test_error_names_the_file(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            list(TomlDecoder().decode_documents("a =\n", filename="x.toml"))
        self.assertTrue(str(ctx.exception).startswith("bad file 'x.toml': "))

    def test_nesting_limits(self) -> None:
        with self.assertRaises(FormatError):
            read("a = " + "[" * (MAX_DEPTH + 1) + "]" * (MAX_DEPTH + 1) + "\n")
        with self.assertRaises(FormatError):
            read("[" + ".".join(["a"] * (MAX_DEPTH + 1)) + "]\n")
        with self.assertRaises(FormatError):
            read("a = " + "[" * 100_000 + "\n")
        self.assertIsNotNone(read("a = " + "[" * MAX_DEPTH + "]" * MAX_DEPTH + "\n"))

    def test_input_size_limit(self) -> None:
        options = Options(input_format="toml", limits=Limits(max_input_bytes=5))
        with self.assertRaises(FormatError):
            yaqpy.evaluate(".", "a = 1234567\n", options=options)


class AgreesWithTomlibTests(unittest.TestCase):
    """The parser and Python's tomllib must read the same data."""

    def corpus(self) -> list[str]:
        root = Path(__file__).resolve().parent.parent / "golden" / "formats" / "toml.json"
        golden = [s["input"] for s in json.loads(root.read_text(encoding="utf-8"))
                  if s["scenario_type"] in ("decode", "roundtrip") and "sample.yml" not in s["input"]]
        extra = [
            'a = 1\nb = "two"\n[t]\nc = [1, 2.5, "x", true]\nd = { e = 1, f = [1, 2] }\n',
            "[[a]]\nx = 1\n[a.b]\ny = 2\n[[a]]\nx = 3\n",
            'k = """\nline1\nline2\\\n  still line2"""\ns = \'\'\'raw\\n\'\'\'\n',
            "x.y.z = 1\nx.y.w = 2\n[q]\nr.s = 3\n",
            "big = 9_223_372_036_854_775_807\nneg = -0\nh = 0xdead_beef\nf = 1e2\ng = -1.5E-3\n",
            '"quoted key" = 1\n\'literal key\' = 2\n[ "a" . \'b\' . c ]\nd = 1\n',
            "a = [\n  [1, 2],\n  [\"x\"],\n]\nb = [ { c = 1 }, { c = 2 } ]\n",
        ]
        return [t for t in golden + extra if t.strip()]

    def test_same_values(self) -> None:
        checked = 0
        for text in self.corpus():
            try:
                expected = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue                      # the Go tests hold a few documents Python rejects
            with self.subTest(text=text[:60]):
                actual = to_python(load(text))
                self.assertEqual(flatten_dates(normalise_floats(actual)),
                                 flatten_dates(normalise_floats(normalise(expected))))
            checked += 1
        self.assertGreater(checked, 30)


def normalise_floats(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalise_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalise_floats(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value


class WriteTests(unittest.TestCase):
    def test_root_values_come_before_tables(self) -> None:
        self.assertEqual(write("t:\n  x: 1\na: 2\nb: [1, 2]\n"), 'a = 2\nb = [1, 2]\n\n[t]\nx = 1\n')

    def test_nested_tables(self) -> None:
        self.assertEqual(write("a:\n  b:\n    c: val\n"), '[a.b]\nc = "val"\n')
        self.assertEqual(write("a:\n  hello: foo\n  nested:\n    key: val\n"),
                         '[a]\nhello = "foo"\n\n[a.nested]\nkey = "val"\n')

    def test_arrays_of_tables(self) -> None:
        text = "fruits:\n  - name: apple\n    varieties:\n      - name: red\n  - name: banana\n"
        self.assertEqual(write(text), '[[fruits]]\nname = "apple"\n[[fruits.varieties]]\nname = "red"\n'
                                      '[[fruits]]\nname = "banana"\n')

    def test_arrays_and_scalars_in_arrays(self) -> None:
        self.assertEqual(write("a: [x, 1, true, [1, 2], {k: v}]\n"),
                         'a = ["x", 1, true, [1, 2], { k = "v" }]\n')

    def test_strings_are_quoted_and_valid_toml(self) -> None:
        data = {"s": "tab\there \"q\" \\ line\nbreak \x07 é 日本 \U0001F600 \u2028"}
        text = convert(json.dumps(data), "json", "toml")
        self.assertEqual(tomllib.loads(text), data)

    def test_keys_are_quoted_when_needed(self) -> None:
        text = write('"a b": 1\n"c.d": 2\nplain-key_1: 3\n"日本": 4\n')
        self.assertEqual(text, '"a b" = 1\n"c.d" = 2\nplain-key_1 = 3\n"日本" = 4\n')
        self.assertEqual(_key_text("é"), '"é"')
        self.assertEqual(_quote("a\x00b"), '"a\\u0000b"')

    def test_null_is_skipped_at_the_top_and_written_empty_in_arrays(self) -> None:
        self.assertEqual(write("a: 1\nb: null\nc: [x, null]\n"), 'a = 1\nc = ["x", ""]\n')

    def test_yaml_flow_maps_become_tables_not_inline_tables(self) -> None:
        self.assertEqual(write("arg: {hello: foo}\n"), '[arg]\nhello = "foo"\n')

    def test_timestamps_are_not_quoted(self) -> None:
        self.assertEqual(write("d: 1979-05-27T07:32:00Z\n"), "d = 1979-05-27T07:32:00Z\n")

    def test_comments_from_yaml_are_written(self) -> None:
        self.assertEqual(write("# top\na: 1 # one\n# about t\nt:\n  b: 2\n"),
                         "# top\na = 1  # one\n\n# about t\n[t]\nb = 2\n")

    def test_top_level_scalar_and_non_mapping(self) -> None:
        self.assertEqual(write("hello\n"), "hello\n")
        with self.assertRaises(FormatError):
            write("[1, 2]\n")

    def test_output_is_always_valid_toml(self) -> None:
        for text in ("a: {b: {c: [1, {d: 2}]}}\ne: [[1], [2, 3]]\nf:\n  - x: 1\n  - x: 2\n",
                     "x: 1\ny:\n  z:\n    - a: 1\n      b: {c: 2}\n"):
            with self.subTest(text=text):
                self.assertEqual(normalise(tomllib.loads(write(text))), read_yaml(text))

    def test_deep_data_is_refused(self) -> None:
        depth = MAX_DEPTH + 5
        text = '{"a":' * depth + "1" + "}" * depth
        with self.assertRaises(FormatError) as ctx:
            convert(text, "json", "toml")
        self.assertIn("too deep", str(ctx.exception))


def read_yaml(text: str) -> Any:
    return json.loads(yaqpy.evaluate(".", text, options=Options(output_format="json")))


class RoundTripTests(unittest.TestCase):
    SAMPLES = (
        'A = "hello"\nB = 12\n',
        'name = { first = "Tom", last = "Preston-Werner" }\n',
        '[owner.contact]\nname = "Tom"\nage = 36\n',
        '[[fruits]]\nname = "apple"\n[[fruits.varieties]]\nname = "red delicious"\n',
        'A = ["hello", ["world", "again"]]\nB = 12\n',
        '[features]\nmy-other-feature = []\nmy-feature = ["my-other-feature"]\n',
        'var = "x"\n\n[owner.contact]\nname = "Tom Preston-Werner"\nage = 36\n',
        '[project]\nname = "p"\nauthors = [{ name = "Author", email = "a@example.com" }]\n'
        'license = { file = "LICENSE" }\n',
        'host = { "http://sealos.hub:5000" = { capabilities = ["pull", "push"], skip_verify = true } }\n',
        '["/tmp/blah"]\nvalue = "hello"\n',
        '[servers."http://localhost:8080"]\nip = "127.0.0.1"\n',
        '[dependencies]\n',
        'A = 0xDEADBEEF\nB = 6.626e-34\nC = 1979-05-27T07:32:00-08:00\n',
    )

    def test_toml_comes_back_unchanged(self) -> None:
        for text in self.SAMPLES:
            with self.subTest(text=text):
                self.assertEqual(convert(text, "toml", "toml"), text)

    def test_an_edit_changes_only_that_value(self) -> None:
        options = Options(input_format="toml", output_format="toml")
        text = '[project]\nname = "p"\nversion = "0.5.1"\nlicense = { file = "LICENSE" }\n'
        self.assertEqual(yaqpy.evaluate('.project.version = "0.5.2"', text, options=options),
                         text.replace("0.5.1", "0.5.2"))


class CliTests(unittest.TestCase):
    def test_extension_and_registry(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        self.assertEqual(formats.from_filename("pyproject.toml").name, "toml")
        self.assertIn("toml", formats.input_formats())
        self.assertIn("toml", formats.output_formats())
        self.assertIn("toml", formats.input_extensions())

    def test_cli_reads_and_writes(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pyproject.toml")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write('# c\n[project]\nname = "p"\nversion = "1"\n')
            code, out, err = run_cli(".project.name", path)
            self.assertEqual((code, out, err), (0, "p\n", ""))
            code, out, _ = run_cli("-o", "yaml", ".", path)
            self.assertEqual(out, "project:\n  name: p\n  version: \"1\"\n")
            code, out, _ = run_cli('.project.version = "2"', path)
            self.assertEqual(out, '[project]\nname = "p"\nversion = "2"\n')

    def test_in_place_update_is_refused_unless_allowed(self) -> None:
        import os
        import tempfile

        original = '# keep this comment\n[project]\nversion = "1"\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.toml")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(original)
            code, out, err = run_cli("-i", '.project.version = "2"', path)
            self.assertEqual(code, 1)
            self.assertIn("--toml-allow-lossy", err)
            with open(path, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), original)              # untouched
            code, _, err = run_cli("-i", "--toml-allow-lossy", '.project.version = "2"', path)
            self.assertEqual((code, err), (0, ""))
            with open(path, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), '[project]\nversion = "2"\n')

    def test_in_place_update_of_other_formats_is_not_affected(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.yaml")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("# c\na: 1\n")
            code, _, _ = run_cli("-i", ".a = 2", path)
            self.assertEqual(code, 0)
            with open(path, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), "# c\na: 2\n")


if __name__ == "__main__":
    unittest.main()
