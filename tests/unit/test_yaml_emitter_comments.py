"""YAML エミッタのコメントの扱い（go-yaml と同じ配置）：
複数行の行コメントの 2 行目以降と、フットコメントの直後の空行。"""

from __future__ import annotations

from yaqpy.core.model.node import Node
from yaqpy.formats.yaml.codec import YamlDecoder, YamlEncoder
from yaqpy.options import Options


def roundtrip(text: str) -> str:
    doc = next(iter(YamlDecoder().decode_documents(text)))
    return YamlEncoder(Options()).encode_to_string(doc)


def mapping(*pairs: tuple[Node, Node]) -> Node:
    node = Node.mapping()
    for key, value in pairs:
        node.add_key_value(key, value)
    return node


def render(node: Node, indent: int = 2) -> str:
    return YamlEncoder(Options(indent=indent)).encode_to_string(node)


class FootCommentSpacingTests:
    def test_blank_line_after_a_foot_comment_is_kept(self) -> None:
        text = "a: 1\n# foot\n\nb: 2\n"
        assert roundtrip(text) == text

    def test_head_comment_of_the_next_key_gets_no_blank_line(self) -> None:
        text = "a: 1\n# head of b\nb: 2\n"
        assert roundtrip(text) == text

    def test_blank_line_inside_a_nested_mapping(self) -> None:
        text = "a:\n  c: 1\n  # foot\n\n  d: 2\nb: 1\n"
        assert roundtrip(text) == text

    def test_no_blank_line_when_the_next_line_is_less_indented(self) -> None:
        text = "a:\n  c: 1\n  # foot\nb: 1\n"
        assert roundtrip(text) == text

    def test_foot_comment_at_the_end_adds_nothing(self) -> None:
        text = "a: 1\nb: 2\n# the end\n"
        assert roundtrip(text) == text

    def test_generated_foot_comment_before_the_next_key(self) -> None:
        first = mapping((Node.string("x"), Node.string("3")))
        key = first.content[0]
        key.foot_comment = "# note"
        first.add_key_value(Node.string("y"), Node.string("4"))
        assert render(first) == 'x: "3"\n# note\n\ny: "4"\n'


class MultilineLineCommentTests:
    def test_following_lines_go_below_at_the_key_indent(self) -> None:
        value = Node.string("3")
        value.line_comment = "# one\n# two \n# three"
        inner = mapping((Node.string("x"), value), (Node.string("y"), Node.string("4")))
        outer = mapping((Node.string("cat"), inner))
        assert render(outer, indent=4) == 'cat:\n    x: "3" # one\n    # two \n    # three\n    y: "4"\n'

    def test_a_single_line_comment_is_unchanged(self) -> None:
        text = "a: 1 # just this\nb: 2\n"
        assert roundtrip(text) == text

    def test_lines_without_a_hash_get_one(self) -> None:
        value = Node.string("v")
        value.line_comment = "# first\nsecond"
        doc = mapping((Node.string("k"), value))
        assert render(doc) == "k: v # first\n# second\n"
