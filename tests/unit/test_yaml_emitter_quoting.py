"""YAML エミッタの引用符の選び方（go-yaml と同じ）：
プレーンにできる → そのまま／別の型に読まれる → "..."／それ以外でプレーンにできない → '...'。"""

from __future__ import annotations

import unittest

from yaqpy.core.model.node import Kind, Node
from yaqpy.formats.yaml.emitter import YamlEmitter


def scalar_text(value: str, tag: str = "!!str") -> str:
    return YamlEmitter()._scalar_text(Node(Kind.SCALAR, tag=tag, value=value), 0, in_flow=False)


class QuotingTests(unittest.TestCase):
    def test_plain_when_possible(self) -> None:
        for value in ("hello", "it's", "yes", "a b", "https://example.com/x"):
            with self.subTest(value=value):
                self.assertEqual(scalar_text(value), value)

    def test_double_quotes_when_it_would_be_read_as_another_type(self) -> None:
        for value in ("4", "true", "null", "~", "1.5", "0x1F", ""):
            with self.subTest(value=value):
                self.assertEqual(scalar_text(value), f'"{value}"')

    def test_single_quotes_when_plain_is_not_possible(self) -> None:
        for value in ("#ffff", "cool: true", "- x", "[a]", "@x", "&a", "*a", "!t", "%x", "a #b",
                      " lead", "trail "):
            with self.subTest(value=value):
                self.assertEqual(scalar_text(value), "'" + value + "'")

    def test_single_quotes_are_doubled(self) -> None:
        self.assertEqual(scalar_text("'q'"), "'''q'''")

    def test_double_quotes_for_control_characters(self) -> None:
        self.assertEqual(scalar_text("x\ty"), '"x\\ty"')
        self.assertEqual(scalar_text("x\ry"), '"x\\ry"')

    def test_the_tag_still_decides_for_non_strings(self) -> None:
        self.assertEqual(scalar_text("4", "!!int"), "4")
        self.assertEqual(scalar_text("true", "!!bool"), "true")


if __name__ == "__main__":
    unittest.main()
