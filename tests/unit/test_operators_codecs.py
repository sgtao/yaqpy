"""encode / decode 演算子（to_json・@yaml・@csv・from_xml・@base64・@uri・@sh ほか）。"""

from __future__ import annotations

import json
import unittest
from typing import Any

import yaqpy
from yaqpy import EvaluationError, Options
from yaqpy.core.operators.codecs import decode_base64, decode_uri


def run(expression: str, text: str = "", **options: Any) -> Any:
    out = yaqpy.evaluate(expression, text, options=Options(output_format="json", indent=0, **options))
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    return lines[0] if len(lines) == 1 else lines


def fails(expression: str, text: str = "") -> str:
    with unittest.TestCase().assertRaises(EvaluationError) as raised:
        run(expression, text)
    return str(raised.exception)


class EncodeTests(unittest.TestCase):
    def test_json_indent(self) -> None:
        self.assertEqual(run(".a | to_json", "a: {b: 1}"), '{\n  "b": 1\n}\n')
        self.assertEqual(run(".a | to_json(0)", "a: {b: 1}"), '{"b":1}')
        self.assertEqual(run(".a | @json", "a: {b: 1}"), '{"b":1}')
        self.assertEqual(run(".a | to_json(4)", "a: {b: 1}"), '{\n    "b": 1\n}\n')

    def test_a_scalar_is_encoded_with_its_quotes_in_json(self) -> None:
        self.assertEqual(run(".a | @json", "a: hi"), '"hi"')

    def test_yaml_and_props(self) -> None:
        self.assertEqual(run(".a | to_yaml", "a:\n  b: 1"), "b: 1\n")
        self.assertEqual(run(".a | @props", "a:\n  b: 1"), "b = 1\n")

    def test_csv_and_tsv_have_no_trailing_newline(self) -> None:
        self.assertEqual(run("@csv", "[[a, b], [c, d]]"), "a,b\nc,d")
        self.assertEqual(run("@tsv", "[[a, b], [c, d]]"), "a\tb\nc\td")

    def test_xml(self) -> None:
        self.assertEqual(run(".a | @xml", "a: {x: 1}").strip(), "<x>1</x>")

    def test_aliases_are_expanded_for_json_without_touching_the_input(self) -> None:
        text = "a: &x {b: 1}\nc: *x"
        self.assertEqual(run(".c | @json", text), '{"b":1}')
        # encoding must not expand the alias in the document itself
        self.assertEqual(yaqpy.evaluate("(.c | @json) as $j | .", text), text + "\n")

    def test_unknown_operators_are_syntax_errors_not_crashes(self) -> None:
        with self.assertRaises(Exception):
            run("to_nonsense", "a: 1")


class RoundTripTests(unittest.TestCase):
    def test_a_decoded_string_without_a_newline_is_encoded_without_one(self) -> None:
        out = yaqpy.evaluate('.a |= (from_yaml | .foo = "cat" | to_yaml)', "a: 'foo: bar'")
        self.assertEqual(out, "a: 'foo: cat'\n")

    def test_a_block_string_keeps_its_newline(self) -> None:
        out = yaqpy.evaluate('.a |= (from_yaml | .foo = "cat" | to_yaml)', "a: |\n  foo: bar\n")
        self.assertEqual(out, "a: |\n  foo: cat\n")

    def test_decoding_an_empty_string_gives_null(self) -> None:
        self.assertIsNone(run('"" | from_yaml'))
        self.assertIsNone(run('"" | @csvd'))

    def test_decoding_keeps_the_path(self) -> None:
        self.assertEqual(run(".a | from_json | path | .[0]", 'a: \'{"x": 1}\''), "a")

    def test_decoded_roots_keep_their_document(self) -> None:
        out = yaqpy.evaluate("@base64d", "YQ==\n---\nYg==\n")
        self.assertEqual(out, "a\n---\nb\n")

    def test_decode_errors_are_reported(self) -> None:
        with self.assertRaises(Exception):
            run('"{" | from_json', "")


class Base64Tests(unittest.TestCase):
    def test_encode_and_decode(self) -> None:
        self.assertEqual(run("@base64", "a special string"), "YSBzcGVjaWFsIHN0cmluZw==")
        self.assertEqual(run("@base64d", "YSBzcGVjaWFsIHN0cmluZw=="), "a special string")

    def test_missing_padding_is_added(self) -> None:
        self.assertEqual(decode_base64("Y2F0cw"), "cats")

    def test_surrounding_whitespace_and_line_breaks_are_ignored(self) -> None:
        self.assertEqual(decode_base64("  Y2F0\ncw==\n"), "cats")

    def test_utf8(self) -> None:
        self.assertEqual(run("@base64 | @base64d", "日本語"), "日本語")

    def test_empty(self) -> None:
        self.assertEqual(decode_base64(""), "")

    def test_illegal_data(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            decode_base64("ab!d")
        self.assertEqual(str(raised.exception), "illegal base64 data at input byte 2")

    def test_only_strings_are_encoded(self) -> None:
        self.assertEqual(fails("@base64", "3"), "cannot encode !!int as base64, can only operate on strings")


class UriTests(unittest.TestCase):
    def test_encode(self) -> None:
        self.assertEqual(run("@uri", "this has & special () characters *"),
                         "this+has+%26+special+%28%29+characters+%2A")
        self.assertEqual(run("@uri", "a-b_c.d~e"), "a-b_c.d~e")
        self.assertEqual(run("@uri", "日"), "%E6%97%A5")

    def test_decode(self) -> None:
        self.assertEqual(decode_uri("a+b%20c%E6%97%A5"), "a b c日")

    def test_bad_escapes(self) -> None:
        for text, shown in (("%zz", "%zz"), ("100%", "%"), ("a%4", "%4")):
            with self.subTest(text=text), self.assertRaises(EvaluationError) as raised:
                decode_uri(text)
            self.assertEqual(str(raised.exception), f'invalid URL escape "{shown}"')

    def test_only_strings_are_encoded(self) -> None:
        self.assertIn("cannot encode !!int as URI", fails("@uri", "3"))


class ShTests(unittest.TestCase):
    def test_safe_text_is_left_alone(self) -> None:
        self.assertEqual(run("@sh", "abc/def-1.2_3@x%y+z=w:v,u"), "abc/def-1.2_3@x%y+z=w:v,u")

    def test_unsafe_text_is_quoted(self) -> None:
        self.assertEqual(run("@sh", "a b"), "a' b'")
        self.assertEqual(run("@sh", "it's"), "it\\'s")

    def test_quotes_and_spaces_mix(self) -> None:
        self.assertEqual(run("@sh", "strings with spaces and a 'quote'"),
                         "strings' with spaces and a '\\'quote\\'")

    def test_only_strings(self) -> None:
        self.assertIn("cannot encode !!bool as URI", fails("@sh", "true"))


if __name__ == "__main__":
    unittest.main()
