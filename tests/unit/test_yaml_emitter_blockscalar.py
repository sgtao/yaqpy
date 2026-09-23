"""YAML エミッタのブロックスカラー（``|``）：書いて読み戻しても値が変わらないこと（v0.7.0 の修正）。

v0.3.0 から、次の文字列は読み戻しで値が変わった：先頭が改行、空白（スペース・タブ）だけの行を含む、
行頭がタブ、リストの要素で先頭が改行・空白の複数行。実行ログの「入力・結果を YAML にして記録する」
（v0.7.0）がこれに当たるので、根本から直した。
"""

from __future__ import annotations

import itertools
import json

import pytest

import yaqpy
from yaqpy.options import Options

TO_YAML = Options(input_format="json", output_format="yaml")
TO_JSON = Options(input_format="yaml", output_format="json", indent=0)


def to_yaml(data: object) -> str:
    return yaqpy.evaluate(".", json.dumps(data), options=TO_YAML)


def round_trip(data: object) -> object:
    return json.loads(yaqpy.evaluate(".", to_yaml(data), options=TO_JSON))


SHAPES = {
    "top": lambda s: {"k": s},
    "nested": lambda s: {"a": {"b": {"k": s}}},
    "list": lambda s: {"a": [s, {"k": [s]}]},
    "root_list": lambda s: [s, {"k": s}],
}

PROBLEM_STRINGS = [
    "\na", "\n\na", "\n-", "\n#", "\n:",                       # 先頭が改行
    " a\nb", "  a\n", " \n", "a\n ", "a\n \nb", "a\n\t\nb",     # 先頭の空白・空白だけの行
    "\ta\nb", "a\n\tb", "\t\na",                                # タブ
    "a\n\n", "\n", "\n\n", "a\n\n\nb\n",                        # 空行・末尾の改行
    "a\r\nb", "a\x01\nb", "a\x1b[0m\nb",                       # 制御文字
    "a: b\nc", "- a\n- b", "# c\nd", "---\na", "...\na", "|\na", ">\na",   # YAML の記号
    "日本語\n二行目", " 日本語\n",
]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("value", PROBLEM_STRINGS)
def test_a_multiline_string_survives_a_round_trip(shape: str, value: str) -> None:
    data = SHAPES[shape](value)
    assert round_trip(data) == data


def test_a_small_exhaustive_search_finds_no_mismatch() -> None:
    """記号の少ない全組み合わせ（5 文字まで）。見つかった不具合はここに入れず、上の表に足す。"""
    alphabet = ["a", " ", "\t", "\n", "-"]
    for n in range(1, 6):
        for chars in itertools.product(alphabet, repeat=n):
            value = "".join(chars)
            data = {"top": {"k": value}, "seq": [value]}
            assert round_trip(data) == data, repr(value)


class OutputShapeTests:
    def test_a_list_item_body_is_indented_by_two_from_the_dash_like_go_yq(self) -> None:
        assert to_yaml(["a\nb"]) == "- |-\n  a\n  b\n"

    def test_a_nested_list_item_body_is_indented_by_two_from_its_dash(self) -> None:
        assert to_yaml({"a": ["x\ny"]}) == "a:\n  - |-\n    x\n    y\n"

    def test_a_mapping_value_body_keeps_its_indent(self) -> None:
        assert to_yaml({"a": "x\ny"}) == "a: |-\n  x\n  y\n"

    def test_a_string_with_a_whitespace_only_line_is_double_quoted(self) -> None:
        assert to_yaml({"a": "x\n \ny"}) == 'a: "x\\n \\ny"\n'

    def test_a_string_with_a_leading_newline_uses_an_explicit_indent(self) -> None:
        assert to_yaml({"a": "\nx"}) == "a: |2-\n\n  x\n"

    def test_ordinary_multiline_strings_still_use_the_block_style(self) -> None:
        assert to_yaml({"a": "one\ntwo\n"}) == "a: |\n  one\n  two\n"
