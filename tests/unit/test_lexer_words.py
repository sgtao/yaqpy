"""Every plain word a lexer rule accepts must be read as that rule - never as the beginning of another one.

Found while writing the self-description: the ``as`` rule took the first two letters of
``ascii_downcase``. The regex alternation takes the first rule that matches, not the longest, so a
keyword that is a prefix of another name has to say that it must end there.
"""

from __future__ import annotations

import unittest

from yaqpy.app.selfdoc import _spellings
from yaqpy.core.lang.lex_rules import DEFAULT_RULES, DEFAULT_RULESET


class LexerWordTests(unittest.TestCase):
    def test_each_spelling_is_read_as_its_own_rule_and_in_full(self) -> None:
        checked = 0
        for rule in DEFAULT_RULES:
            for word in _spellings(rule.pattern):
                checked += 1
                with self.subTest(word=word, rule=rule.name):
                    found = DEFAULT_RULESET.match(word, 0)
                    self.assertIsNotNone(found)
                    matched_rule, match = found
                    self.assertEqual((matched_rule.name, match.end()), (rule.name, len(word)))
        self.assertGreater(checked, 100)      # the table really was walked

    def test_as_and_ref_still_bind_variables_however_they_are_spaced(self) -> None:
        import yaqpy

        self.assertEqual(yaqpy.query(". as $x | $x.a", {"a": 1}), [1])
        self.assertEqual(yaqpy.query(".a as$x|$x", {"a": 2}), [2])
        self.assertEqual(yaqpy.query(".a as $x | .b as $y | $x + $y", {"a": 1, "b": 2}), [3])

    def test_the_ascii_case_operators_work(self) -> None:
        import yaqpy

        self.assertEqual(yaqpy.query("ascii_downcase", "ABC"), ["abc"])
        self.assertEqual(yaqpy.query("ascii_upcase", "abc"), ["ABC"])


if __name__ == "__main__":
    unittest.main()
