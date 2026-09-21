"""Go (RE2) の正規表現との差を吸収する core/operators/regex.py。"""

from __future__ import annotations

import unittest

from yaqpy.core.operators.regex import (
    RegexError, byte_length, byte_offset, compile_go, expand, find_all, replace_all,
)


def spans(pattern: str, text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in find_all(compile_go(pattern), text)]


class CompileTests(unittest.TestCase):
    def test_dollar_is_the_end_of_the_text_only(self) -> None:
        # Python's $ would also match before the trailing newline
        self.assertIsNone(compile_go("cat$").search("cat\n"))
        self.assertIsNotNone(compile_go("cat$").search("cat"))

    def test_dollar_in_multiline_mode_is_a_line_end(self) -> None:
        self.assertIsNotNone(compile_go("(?m)cat$").search("cat\nfoo"))

    def test_backslash_z(self) -> None:
        self.assertIsNone(compile_go("cat\\z").search("cat\n"))
        self.assertIsNotNone(compile_go("cat\\z").search("cat"))

    def test_escaped_dollar_stays_literal(self) -> None:
        self.assertIsNotNone(compile_go("a\\$b").search("a$b"))
        self.assertIsNotNone(compile_go("[$]").search("$"))

    def test_named_group_with_angle_brackets(self) -> None:
        match = compile_go("(?<year>[0-9]+)-(?P<month>[0-9]+)").search("2001-12")
        assert match is not None
        self.assertEqual(match.group("year"), "2001")
        self.assertEqual(match.group("month"), "12")

    def test_lookahead_is_left_alone_for_python_to_judge(self) -> None:
        # Go has no lookahead; we do not rewrite (?<= / (?<! into named groups
        self.assertIsNotNone(compile_go("(?<=a)b").search("ab"))

    def test_leading_flags(self) -> None:
        self.assertIsNotNone(compile_go("(?i)CAT").search("cat"))
        self.assertIsNotNone(compile_go("(?i)(?s)a.b").search("A\nB"))

    def test_posix_classes(self) -> None:
        self.assertEqual(compile_go("[[:alpha:]]+").search("12abc34").group(), "abc")  # type: ignore[union-attr]
        self.assertEqual(compile_go("[^[:digit:]]+").search("12abc34").group(), "abc")  # type: ignore[union-attr]
        self.assertEqual(compile_go("[[:upper:][:digit:]]+").search("aB1c").group(), "B1")  # type: ignore[union-attr]

    def test_literal_bracket_and_leading_close_bracket_in_a_class(self) -> None:
        self.assertIsNotNone(compile_go("[]a]").search("]"))
        self.assertIsNotNone(compile_go("[[]").search("["))

    def test_quoted_literal(self) -> None:
        self.assertIsNotNone(compile_go("\\Qa.b\\E").search("a.b"))
        self.assertIsNone(compile_go("\\Qa.b\\E").search("axb"))

    def test_refused_constructs(self) -> None:
        for pattern in ("\\pL", "\\p{Greek}", "(?U)a+", "(?x)a b"):
            with self.subTest(pattern=pattern), self.assertRaises(RegexError):
                compile_go(pattern)

    def test_syntax_error(self) -> None:
        with self.assertRaises(RegexError) as raised:
            compile_go("(abc")
        self.assertTrue(str(raised.exception).startswith("error parsing regexp:"))


class FindAllTests(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(spans("a", "banana"), [(1, 2), (3, 4), (5, 6)])

    def test_empty_matches_are_not_reported_right_after_a_match(self) -> None:
        # Go の allMatches のアルゴリズム（regexp/regexp.go）を写したもの。Go 本体では未実行
        self.assertEqual(spans("a*", "baaab"), [(0, 0), (1, 4), (5, 5)])

    def test_empty_pattern_matches_between_characters(self) -> None:
        self.assertEqual(spans("", "ab"), [(0, 0), (1, 1), (2, 2)])

    def test_no_match(self) -> None:
        self.assertEqual(spans("z", "abc"), [])


class ReplaceTests(unittest.TestCase):
    def sub(self, pattern: str, text: str, template: str) -> str:
        return replace_all(compile_go(pattern), text, template)

    def test_numbered_and_named_references(self) -> None:
        self.assertEqual(self.sub("(a)(b)", "ab", "$2$1"), "ba")
        self.assertEqual(self.sub("(?P<x>a)", "a", "[${x}]"), "[a]")
        self.assertEqual(self.sub("(?P<x>a)", "a", "[$x]"), "[a]")

    def test_a_name_is_as_long_as_possible(self) -> None:
        self.assertEqual(self.sub("(a)", "a", "$1x"), "")       # $1x is the (missing) name "1x"
        self.assertEqual(self.sub("(a)", "a", "${1}x"), "ax")

    def test_unknown_and_unmatched_groups_are_empty(self) -> None:
        self.assertEqual(self.sub("(a)|(b)", "a", "<$2>"), "<>")
        self.assertEqual(self.sub("a", "a", "<$9>"), "<>")

    def test_dollar_escapes_and_malformed_references(self) -> None:
        self.assertEqual(self.sub("a", "a", "$$"), "$")
        self.assertEqual(self.sub("a", "a", "cost $"), "cost $")
        self.assertEqual(self.sub("a", "a", "${"), "${")
        self.assertEqual(self.sub("a", "a", "$ x"), "$ x")

    def test_backslashes_are_not_special(self) -> None:
        self.assertEqual(self.sub("a", "a", "\\1"), "\\1")

    def test_empty_matches(self) -> None:
        # Go の replaceAll のアルゴリズム（regexp/regexp.go）を写したもの。Go 本体では未実行
        self.assertEqual(self.sub("a*", "baaab", "X"), "XbXbX")

    def test_expand_on_a_match(self) -> None:
        match = compile_go("(?P<n>[0-9]+)").search("x42")
        assert match is not None
        self.assertEqual(expand("<$n|$1|${n}>", match), "<42|42|42>")


class ByteCountTests(unittest.TestCase):
    def test_ascii_is_identity(self) -> None:
        self.assertEqual((byte_offset("abc", 2), byte_length("abc")), (2, 3))

    def test_counts_utf8_bytes_like_go(self) -> None:
        self.assertEqual(byte_offset("日本語abc", 3), 9)
        self.assertEqual(byte_length("日本語"), 9)


if __name__ == "__main__":
    unittest.main()
