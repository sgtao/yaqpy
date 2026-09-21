"""文字列の演算子（join・split・sub・match・capture・test・trim・大小文字・to_string・to_number・補間）。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaqpy
from yaqpy import EvaluationError, Options
from yaqpy.cli.main import main


def run(expression: str, text: str = "", **options: Any) -> Any:
    opts = Options(output_format="json", indent=0, **options)
    out = yaqpy.evaluate(expression, text, options=opts)
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    return lines[0] if len(lines) == 1 else lines


def fails(expression: str, text: str = "") -> str:
    with unittest.TestCase().assertRaises(EvaluationError) as raised:
        run(expression, text)
    return str(raised.exception)


class JoinSplitTests(unittest.TestCase):
    def test_join(self) -> None:
        self.assertEqual(run('join(",")', "[a, b, c]"), "a,b,c")

    def test_join_takes_null_as_empty_and_keeps_other_scalars(self) -> None:
        self.assertEqual(run('join("-")', "[a, null, 3, true]"), "a--3-true")

    def test_join_only_arrays(self) -> None:
        self.assertEqual(fails('join(",")', "a: 1"),
                         "cannot join with !!map, can only join arrays of scalars")

    def test_split(self) -> None:
        self.assertEqual(run('split(", ")', "a, b, c"), ["a", "b", "c"])
        self.assertEqual(run('split(",")', "a,,b,"), ["a", "", "b", ""])

    def test_split_on_an_empty_separator_gives_characters(self) -> None:
        self.assertEqual(run('split("")', "héllo"), ["h", "é", "l", "l", "o"])

    def test_split_of_an_empty_string_is_an_empty_array(self) -> None:
        self.assertEqual(run('split(",")', '""'), [])

    def test_split_skips_null_and_refuses_other_types(self) -> None:
        self.assertEqual(yaqpy.evaluate('split(",")', "null"), "")
        self.assertEqual(fails('split(",")', "3"), "cannot split !!int, can only split strings")


class RegexOperatorTests(unittest.TestCase):
    def test_sub_with_groups(self) -> None:
        self.assertEqual(run('sub("(a)(b)", "$2$1")', "abab"), "baba")
        self.assertEqual(run('sub("(?P<w>[a-z]+)", "<${w}>")', "abc 1"), "<abc> 1")

    def test_sub_is_global(self) -> None:
        self.assertEqual(run('sub("a", "x")', "banana"), "bxnxnx")

    def test_sub_case_insensitive_flag(self) -> None:
        self.assertEqual(run('sub("(?i)DOG", "cat")', "Dog dog"), "cat cat")

    def test_sub_replacement_is_evaluated_against_the_node(self) -> None:
        self.assertEqual(run('. as $r | .a |= sub("x", $r.b)', "{a: axa, b: Z}"),
                         {"a": "aZa", "b": "Z"})
        # the argument sees the node being changed, not the document
        self.assertEqual(run('.a |= sub("x", .b)', "{a: axa, b: Z}"), {"a": "aa", "b": "Z"})

    def test_sub_refuses_non_strings(self) -> None:
        self.assertIn("cannot substitute with !!int", fails('sub("1", "2")', "1"))

    def test_bad_regex_is_an_evaluation_error(self) -> None:
        self.assertTrue(fails('sub("(a", "x")', "abc").startswith("error parsing regexp:"))
        self.assertIn("not supported", fails('test("\\\\pL")', "abc"))

    def test_match_reports_offsets_and_captures(self) -> None:
        out = run('match("(?P<n>[0-9]+)")', "ab 42")
        self.assertEqual(out, {"string": "42", "offset": 3, "length": 2,
                               "captures": [{"string": "42", "offset": 3, "length": 2, "name": "n"}]})

    def test_match_offsets_are_utf8_bytes_like_go(self) -> None:
        out = run('match("b")', "日本b")
        self.assertEqual((out["offset"], out["length"]), (6, 1))

    def test_match_global_and_no_match(self) -> None:
        self.assertEqual([m["offset"] for m in run('[match("a"; "g")]', "banana")], [1, 3, 5])
        self.assertEqual(yaqpy.evaluate('match("z")', "abc"), "")

    def test_match_unmatched_group_is_null_with_offset_minus_one(self) -> None:
        out = run('match("a(x)?b")', "ab")
        self.assertEqual(out["captures"], [{"string": None, "offset": -1, "length": 0}])

    def test_match_params(self) -> None:
        self.assertIn("'i' is not a valid option", fails('match("a"; "i")', "a"))
        self.assertIn("unrecognised match params 'z'", fails('match("a"; "gz")', "a"))

    def test_a_comma_is_not_a_params_separator(self) -> None:
        # like Go: only the first argument counts, so this is not a global match
        self.assertEqual(len(run('[match("a", "g")]', "banana")), 1)

    def test_capture(self) -> None:
        self.assertEqual(run('capture("(?P<a>[a-z]+)-(?P<n>[0-9]+)")', "cat-42"),
                         {"a": "cat", "n": "42"})
        self.assertEqual(run('capture("(?P<a>x)?b")', "b"), {"a": None})

    def test_test_anchors_at_the_end_of_the_text(self) -> None:
        self.assertIs(run('test("cat$")', "cat"), True)
        # a YAML block scalar ends with a newline; Go's $ does not match before it
        self.assertIs(run('test("cat$")', "|\n  cat\n"), False)

    def test_test_refuses_non_strings(self) -> None:
        self.assertIn("cannot match with !!int", fails('test("1")', "1"))


class TrimCaseTests(unittest.TestCase):
    def test_trim(self) -> None:
        self.assertEqual(run("trim", '"  a b \\t\\n"'), "a b")

    def test_trim_uses_go_whitespace(self) -> None:
        self.assertEqual(run("trim", '"\u3000x\u00a0"'), "x")
        self.assertEqual(run("trim", '"\\u001cx"'), "\x1cx")     # not whitespace for Go

    def test_trim_refuses_non_strings(self) -> None:
        self.assertEqual(fails("trim", "3"), "cannot trim !!int, can only operate on strings. ")

    def test_case(self) -> None:
        self.assertEqual(run("upcase", "abc Def"), "ABC DEF")
        self.assertEqual(run("downcase", "ABC Def"), "abc def")

    def test_case_maps_each_character_on_its_own(self) -> None:
        self.assertEqual(run("upcase", "straße"), "STRAßE")     # Python's str.upper gives STRASSE

    def test_case_refuses_non_strings(self) -> None:
        self.assertEqual(fails("upcase", "3"),
                         "cannot change case with !!int, can only operate on strings. ")


class ToStringNumberTests(unittest.TestCase):
    def test_to_string(self) -> None:
        self.assertEqual(run("to_string", "12"), "12")
        self.assertEqual(run("to_string", "true"), "true")
        self.assertEqual(run("to_string", "a"), "a")
        self.assertEqual(run("to_string", "b: 1\nc: 2"), "b: 1\nc: 2")

    def test_to_string_quotes_non_strings_in_yaml(self) -> None:
        self.assertEqual(yaqpy.evaluate("to_string", "12", options=Options(unwrap_scalar=False)),
                         '"12"\n')

    def test_to_number(self) -> None:
        self.assertEqual(run("[.[] | to_number]", '["3", "3.5", "-1e3", "0x1F", "+7", "1_000"]'),
                         [3, 3.5, -1000.0, 31, 7, 1000])

    def test_to_number_tags(self) -> None:
        out = yaqpy.evaluate(".[] | to_number | tag", '["3", "3.5", "1e3"]')
        self.assertEqual(out.split(), ["!!int", "!!float", "!!float"])

    def test_int64_overflow_becomes_a_float(self) -> None:
        self.assertEqual(yaqpy.evaluate("to_number | tag", '"99999999999999999999"').strip(), "!!float")

    def test_special_floats(self) -> None:
        self.assertEqual(yaqpy.evaluate("to_number | tag", '"NaN"').strip(), "!!float")
        self.assertEqual(yaqpy.evaluate("to_number | tag", '"-Inf"').strip(), "!!float")
        self.assertIn("cannot convert node value [+nan]", fails("to_number", '"+nan"'))

    def test_not_numbers(self) -> None:
        for text in ('"abc"', '" 1"', '"1 "', '"1_0.5"', '"0x"', '""'):
            with self.subTest(text=text):
                self.assertIn("cannot convert node value", fails("to_number", text))

    def test_containers_are_refused(self) -> None:
        self.assertIn("cannot convert node at path", fails("to_number", "[1]"))


class InterpolationTests(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(run('"I like \\(.a) and \\(.b)"', "{a: cats, b: dogs}"),
                         "I like cats and dogs")

    def test_expressions_and_nested_parentheses(self) -> None:
        self.assertEqual(run('"n=\\(.a | length)"', "a: [1, 2, 3]"), "n=3")
        self.assertEqual(run('"n=\\((.a | length) + 1)"', "a: [1, 2, 3]"), "n=4")
        self.assertEqual(run('"\\( (.a) )"', "a: hi"), "hi")

    def test_an_escaped_backslash_is_kept(self) -> None:
        self.assertEqual(run('"Hi \\\\(.a)"', "a: x"), "Hi \\(.a)")

    def test_a_map_is_written_as_yaml(self) -> None:
        self.assertEqual(run('"got \\(.a)"', "a:\n  b: 1"), "got b: 1")

    def test_an_empty_result_is_an_empty_string(self) -> None:
        self.assertEqual(run('"[\\(.zzz | select(. != null))]"', "a: 1"), "[]")

    def test_unclosed_is_left_alone(self) -> None:
        self.assertEqual(run('"a \\(.a"', "a: 1"), "a \\(.a")

    def test_it_can_be_turned_off(self) -> None:
        self.assertEqual(run('"a \\(.a)"', "a: 1", string_interpolation=False), "a \\(.a)")

    def test_cli_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "in.yaml"
            path.write_text("a: 1\n", encoding="utf-8", newline="\n")
            for flag, want in (("--string-interpolation=false", "a \\(.a)\n"),
                               ("--string-interpolation", "a 1\n")):
                with self.subTest(flag=flag):
                    out = io.StringIO()
                    code = main([flag, '"a \\(.a)"', str(path)], stdout=out, stderr=io.StringIO())
                    self.assertEqual((code, out.getvalue()), (0, want))


if __name__ == "__main__":
    unittest.main()
