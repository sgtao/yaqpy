"""properties の入出力：読み取り（区切り・コメント・継続行・エスケープ・キーの階層）と、書き出しの補足。"""

from __future__ import annotations

import io
import json
import unittest
from typing import Any

import yaqpy
from yaqpy import FormatError, Options, PropertiesOptions
from yaqpy.cli.main import main
from yaqpy.formats.props_codec import (
    MAX_ARRAY_INDEX, MAX_PATH_DEPTH, PropertiesDecoder, parse_key, parse_properties,
)


def read(text: str, **props: Any) -> Any:
    options = Options(input_format="props", output_format="json", props=PropertiesOptions(**props))
    return json.loads(yaqpy.evaluate(".", text, options=options))


def to_yaml(text: str, **props: Any) -> str:
    options = Options(input_format="props", output_format="yaml", props=PropertiesOptions(**props))
    return yaqpy.evaluate(".", text, options=options)


def to_props(text: str, *, unwrap: bool | None = None, **props: Any) -> str:
    options = Options(input_format="yaml", output_format="props", unwrap_scalar=unwrap,
                      props=PropertiesOptions(**props))
    return yaqpy.evaluate(".", text, options=options)


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def pairs(self, text: str) -> list[tuple[str, str]]:
        return [(k, v) for k, v, _ in parse_properties(text)]

    def test_separators(self) -> None:
        text = "a=1\nb = 2\nc: 3\nd : 4\ne 5\nf\t6\n"
        self.assertEqual(self.pairs(text), [("a", "1"), ("b", "2"), ("c", "3"), ("d", "4"),
                                            ("e", "5"), ("f", "6")])

    def test_value_keeps_everything_after_the_separator(self) -> None:
        self.assertEqual(self.pairs("a =  x = y:z  \n"), [("a", "x = y:z  ")])

    def test_key_without_value(self) -> None:
        self.assertEqual(self.pairs("a\nb=\nc:\n"), [("a", ""), ("b", ""), ("c", "")])

    def test_blank_lines_and_line_endings(self) -> None:
        self.assertEqual(self.pairs("\n\na=1\r\n\r\nb=2\rc=3"), [("a", "1"), ("b", "2"), ("c", "3")])

    def test_line_continuation(self) -> None:
        text = "a = one \\\n    two \\\n  three\nb = 2\nc = end\\\n"
        self.assertEqual(self.pairs(text), [("a", "one two three"), ("b", "2"), ("c", "end")])

    def test_an_escaped_backslash_does_not_continue(self) -> None:
        self.assertEqual(self.pairs("a = x\\\\\nb = y\n"), [("a", "x\\"), ("b", "y")])

    def test_escapes_in_values_and_keys(self) -> None:
        text = "a = tab\\there\\nnew \\u00e9 \\q\nk\\ ey\\:x = 1\n"
        self.assertEqual(self.pairs(text), [("a", "tab\there\nnew é q"), ("k ey:x", "1")])

    def test_invalid_unicode_escape(self) -> None:
        with self.assertRaises(FormatError):
            parse_properties("a = \\u00zz\n")

    def test_later_definition_replaces_the_value_but_keeps_the_position(self) -> None:
        self.assertEqual(self.pairs("a=1\nb=2\na=3\n"), [("a", "3"), ("b", "2")])

    def test_comments_belong_to_the_next_property(self) -> None:
        entries = parse_properties("# one\n! two\n\na = 1\n# lonely\n")
        self.assertEqual(entries, [("a", "1", ["one", "two"])])

    def test_key_paths(self) -> None:
        self.assertEqual(parse_key("a.b.0.c", array_brackets=False), ["a", "b", 0, "c"])
        self.assertEqual(parse_key("a.b[0][1].c", array_brackets=True), ["a", "b", 0, 1, "c"])
        self.assertEqual(parse_key("a.b[0]", array_brackets=False), ["a", "b[0]"])
        self.assertEqual(parse_key("a.b[x]", array_brackets=True), ["a", "b[x]"])
        self.assertEqual(parse_key("a.-1.+2", array_brackets=False), ["a", "-1", 2])


class DecodeTests(unittest.TestCase):
    def test_nested_maps_and_lists(self) -> None:
        text = "a.b = 1\na.c = 2\nd.0 = x\nd.1.k = y\n"
        self.assertEqual(read(text), {"a": {"b": "1", "c": "2"}, "d": ["x", {"k": "y"}]})

    def test_values_stay_strings(self) -> None:
        self.assertEqual(read("n = 10\nb = true\n"), {"n": "10", "b": "true"})

    def test_gaps_in_a_list_are_null(self) -> None:
        self.assertEqual(read("a.2 = x\n"), {"a": [None, None, "x"]})

    def test_number_under_an_existing_map_is_a_key(self) -> None:
        self.assertEqual(read("a.x = 1\na.5 = 2\n"), {"a": {"x": "1", "5": "2"}})

    def test_array_brackets(self) -> None:
        text = "u.c[0].n = a\nu.c[1].n = b\n"
        self.assertEqual(read(text, use_array_brackets=True), {"u": {"c": [{"n": "a"}, {"n": "b"}]}})
        self.assertEqual(read("u.c[0] = a\n"), {"u": {"c[0]": "a"}})

    def test_placeholders_are_not_expanded(self) -> None:
        self.assertEqual(read("a = ${b} and $HOME\nb = x\n"), {"a": "${b} and $HOME", "b": "x"})

    def test_a_later_scalar_replaces_a_map(self) -> None:
        self.assertEqual(read("a.b = 1\na = 2\n"), {"a": "2"})

    def test_empty_and_blank_input(self) -> None:
        self.assertEqual(list(PropertiesDecoder().decode_documents("")), [])
        self.assertEqual(read("\n  \n"), {})

    def test_bom(self) -> None:
        self.assertEqual(read("﻿a = 1\n"), {"a": "1"})

    def test_comments_become_key_comments(self) -> None:
        text = "# about a\n# more\na.x = 1\n\n# about y\na.y = 2\n"
        self.assertEqual(to_yaml(text),
                         "a:\n  # about a\n  # more\n  x: \"1\"\n  # about y\n  y: \"2\"\n")

    def test_comments_on_list_items(self) -> None:
        self.assertEqual(to_yaml("l.0 = a\n# note\nl.1 = b\n"),
                         'l:\n  - "a"\n  # note\n  - "b"\n'.replace('"a"', "a").replace('"b"', "b"))

    def test_key_conflicts_are_errors(self) -> None:
        for text in ("a = 1\na.b = 2\n", "l.0 = x\nl.name = y\n", "l.0 = x\nl.0.k = y\n"):
            with self.subTest(text=text), self.assertRaises(FormatError):
                read(text)

    def test_limits(self) -> None:
        with self.assertRaises(FormatError):
            read(f"a.{MAX_ARRAY_INDEX + 1} = x\n")
        self.assertEqual(len(read(f"a.{MAX_ARRAY_INDEX} = x\n")["a"]), MAX_ARRAY_INDEX + 1)
        with self.assertRaises(FormatError):
            read(".".join(["a"] * (MAX_PATH_DEPTH + 1)) + " = x\n")

    def test_error_names_the_file(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            list(PropertiesDecoder().decode_documents("a = 1\na.b = 2\n", filename="x.properties"))
        self.assertTrue(str(ctx.exception).startswith("bad file 'x.properties': properties: cannot set"))

    def test_input_size_limit(self) -> None:
        from yaqpy import Limits

        options = Options(input_format="props", limits=Limits(max_input_bytes=5))
        with self.assertRaises(FormatError):
            yaqpy.evaluate(".", "a = 12345678\n", options=options)


class WriteTests(unittest.TestCase):
    def test_flat_keys_and_list_indexes(self) -> None:
        self.assertEqual(to_props("a:\n  b: 1\n  c: [x, y]\n"), "a.b = 1\na.c.0 = x\na.c.1 = y\n")

    def test_comment_blocks_are_set_apart(self) -> None:
        text = "a: 1 # about a\nb: 2\nc: 3 # about c\nd: 4 # about d\n"
        self.assertEqual(to_props(text), "# about a\na = 1\nb = 2\n\n# about c\nc = 3\n\n# about d\nd = 4\n")

    def test_the_first_comment_block_has_no_blank_line_before_it(self) -> None:
        self.assertEqual(to_props("a: 1 # first\n"), "# first\na = 1\n")

    def test_values_with_a_space_are_quoted_when_not_unwrapped(self) -> None:
        self.assertEqual(to_props("a: two words\nb: one\n", unwrap=False), 'a = "two words"\nb = one\n')
        self.assertEqual(to_props("a: two words\n"), "a = two words\n")

    def test_quoting_escapes(self) -> None:
        # the value is  say "hi" \ x  -> quoted as "say \"hi\" \\ x" -> each backslash doubled again
        self.assertEqual(to_props('a: "say \\"hi\\" \\\\ x"\n', unwrap=False),
                         r'a = "say \\"hi\\" \\\\ x"' + "\n")

    def test_round_trip(self) -> None:
        text = ("# server\nserver.host = example.com\nserver.ports.0 = 80\nserver.ports.1 = 443\n\n"
                "# owner\nowner.name = Ann Lee\n")
        options = Options(input_format="props", output_format="props")
        self.assertEqual(yaqpy.evaluate(".", text, options=options), text)

    def test_special_characters_survive_a_round_trip(self) -> None:
        options = Options(input_format="props", output_format="json")
        source = Options(input_format="json", output_format="props")
        data = {"k ey:1": "tab\there", "line": "a\nb", "path": "C:\\temp", "uni": "é日本"}
        text = yaqpy.evaluate(".", json.dumps(data), options=source)
        self.assertEqual(json.loads(yaqpy.evaluate(".", text, options=options)),
                         {"k ey:1": "tab\there", "line": "a\nb", "path": "C:\\temp", "uni": "é日本"})


class CliTests(unittest.TestCase):
    def test_extension_and_input_formats(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        self.assertEqual(formats.from_filename("app.properties").name, "props")
        self.assertIn("props", formats.input_formats())
        self.assertIn("properties", formats.input_extensions())

    def test_cli_reads_a_properties_file(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "app.properties")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("# db\ndb.host = localhost\ndb.port = 5432\n")
            code, out, err = run_cli("-o", "yaml", ".", path)
            self.assertEqual((code, out, err), (0, "db:\n  # db\n  host: localhost\n  port: \"5432\"\n", ""))
            code, out, _ = run_cli(".db.port", path)
            self.assertEqual(out, "5432\n")
            code, out, _ = run_cli('.db.port = "6543"', path)
            self.assertEqual(out, "# db\ndb.host = localhost\ndb.port = 6543\n")


if __name__ == "__main__":
    unittest.main()
