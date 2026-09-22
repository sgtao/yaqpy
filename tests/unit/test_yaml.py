"""In-house YAML parser / emitter tests (design doc 9-3)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from yaqpy.core.model import Kind, Style, to_python
from yaqpy.errors import YamlSyntaxError
from yaqpy.formats.yaml.codec import YamlDecoder, YamlEncoder, preprocess_leading_content
from yaqpy.formats.yaml.parser import parse_documents
from yaqpy.options import Options, YamlOptions

TEST_SETS = Path(__file__).resolve().parents[3] / "23_testSets"


def round_trip(text: str, **yaml_opts: object) -> str:
    options = Options(yaml=YamlOptions(**yaml_opts)) if yaml_opts else Options()
    decoder = YamlDecoder(options)
    encoder = YamlEncoder(options, unwrap_scalar=True)
    out = io.StringIO()
    for i, doc in enumerate(decoder.decode_documents(text)):
        if i > 0:
            encoder.print_document_separator(out)
        encoder.print_leading_content(out, doc.leading_content)
        encoder.encode(out, doc)
    return out.getvalue()


def load(text: str):
    return [to_python(d) for d in parse_documents(text)]


class ParserTests:
    def test_block_structures(self) -> None:
        text = "a:\n  b: 1\n  c:\n    - x\n    - y: 2\n      z: 3\n    - - nested\nd: []\ne: {}\n"
        assert load(text) == [{"a": {"b": 1, "c": ["x", {"y": 2, "z": 3}, ["nested"]]},
                            "d": [], "e": {}}]

    def test_flow_structures(self) -> None:
        text = 'a: {x: 1, y: [1, {z: 2}], "j":3, w: }\nb: [a, "b", c: d]\n'
        assert load(text) == [{"a": {"x": 1, "y": [1, {"z": 2}], "j": 3, "w": None},
                            "b": ["a", "b", {"c": "d"}]}]

    def test_multi_line_flow(self) -> None:
        text = "a: [\n  1,\n  2, # comment\n  3\n]\n"
        assert load(text) == [{"a": [1, 2, 3]}]

    def test_scalar_styles(self) -> None:
        text = ('plain: multi\n  line\nsq: \'it\'\'s\'\ndq: "tab\\tnl\\n\\u00e9"\n'
                'lit: |\n  a\n   b\n\nfold: >-\n  x\n  y\n\n  z\nkeep: |+\n  k\n\nnext: 1\n')
        data = load(text)[0]
        assert data["plain"] == "multi line"
        assert data["sq"] == "it's"
        assert data["dq"] == "tab\tnl\n\u00e9"
        assert data["lit"] == "a\n b\n"
        assert data["fold"] == "x y\nz"
        assert data["keep"] == "k\n\n"
        assert data["next"] == 1

    def test_tags_and_types(self) -> None:
        docs = parse_documents("a: !!str 123\nb: 0x1F\nc: 2001-12-14\nd: !custom [1]\ne: ~\n")
        root = docs[0]
        values = {k.value: v for k, v in root.map_items()}
        assert values["a"].tag == "!!str"
        assert values["a"].style & Style.TAGGED
        assert values["b"].tag == "!!int"
        assert values["b"].value == "0x1F"
        assert values["c"].tag == "!!timestamp"
        assert values["d"].tag == "!custom"
        assert values["e"].tag == "!!null"

    def test_anchors_aliases_and_merge(self) -> None:
        text = "base: &b\n  x: 1\nother:\n  <<: *b\n  y: 2\nref: *b\n"
        docs = parse_documents(text)
        root = docs[0]
        ref = root.get_map_value("ref")
        assert ref.kind == Kind.ALIAS
        assert ref.resolve_alias().get_map_value("x").value == "1"
        merge_key = root.get_map_value("other").content[0]
        assert merge_key.tag == "!!merge"

    def test_multi_document(self) -> None:
        docs = parse_documents("a: 1\n---\nb: 2\n---\nplain\n...\n")
        assert [to_python(d) for d in docs] == [{"a": 1}, {"b": 2}, "plain"]

    def test_comments(self) -> None:
        text = "# head\na: 1 # line\nb:\n  # under b\n  - x\nc: 2\n# foot\n"
        docs = parse_documents(text)
        root = docs[0]
        assert root.head_comment == "# head"
        assert root.get_map_value("a").line_comment == "# line"
        assert root.get_map_value("b").content[0].head_comment == "# under b"
        assert root.foot_comment == "# foot"

    def test_errors_have_positions(self) -> None:
        with pytest.raises(YamlSyntaxError) as ctx:
            parse_documents("a: [1, 2\n")
        assert ctx.value.line >= 1
        with pytest.raises(YamlSyntaxError):
            parse_documents("a: 'unterminated\n")
        with pytest.raises(YamlSyntaxError):
            parse_documents("a: *missing\n")
        with pytest.raises(YamlSyntaxError):
            parse_documents("a:\n\tb: 1\n")

    def test_leading_content_preprocessing(self) -> None:
        leading, rest = preprocess_leading_content("# c\n\n---\na: 1\n")
        assert leading == "# c\n\n$yqDocSeparator$\n"
        assert rest == "a: 1\n"
        leading, rest = preprocess_leading_content("--- cat\n")
        assert (leading, rest) == ("$yqDocSeparator$\n", "cat\n")


class RoundTripTests:
    IDENTICAL = [
        "a: hello # things\n", "a: [1, 2]\n", "a: !horse [a]\n", "---\r\ncat\r\n",
        "%YAML 1.1\n---\ncat\n", "null\n", "~\n", "0o30\n", "[null]\n", "a: null\n", "3.1\n",
        "a: &remember mike\n---\nb: *remember\n", "a:\n  b: things\n",
        "hello: # hello-world-comment\n  message: world\n",
        "name:\n  # under-name-comment\n  - first-array-child\n",
        "a: cat # comment\nb: dog # leave this\n", "f: foo\n# single\na:\n  b: cat\n",
        "a:\n  - b: 1\n    c: 2\n  - - x\n    - y\n", "a: |\n  line1\n  line2\n",
        "a: \"q\\\"uote\"\nb: 'sin''gle'\n", "a: {x: 1, y: [1, {z: 2}]}\n",
        "key with spaces: 1\n\"quoted key\": 2\n'k': 3\n", "- 1\n- 2\n",
        "a: 2001-12-14\nb: true\nc: 0x1F\nd: 1.50\ne: .inf\n", "empty:\nlist: []\nmap: {}\n",
        "test:\n# this comment will be removed\n", "a: |+\n  keep\n\nb: 1\n",
        "a: |2\n   indented\nb: 1\n", "- a: 1\n  b: 2\n- c\n", "x: &a {b: 1}\ny: *a\n",
        "a:\n  - x\n  # comment after\nb: 1\n", "stringNumber: !!str 2026\n",
        "a: \"123\"\nb: \"true\"\nc: \"\"\n",
    ]

    def test_identical_round_trips(self) -> None:
        for text in self.IDENTICAL:
            assert round_trip(text) == text

    def test_go_style_normalisations(self) -> None:
        assert round_trip("a: [1,2]\n") == "a: [1, 2]\n"
        assert round_trip("--- cat\n") == "---\ncat\n"
        assert round_trip("# hello") == "# hello\n"
        assert round_trip("a:\n- 1\n- 2\n") == "a:\n  - 1\n  - 2\n"
        assert round_trip("a:\n- 1\n", compact_sequence_indent=True) == "a:\n- 1\n"

    def test_indent_option(self) -> None:
        options = Options(indent=4)
        encoder = YamlEncoder(options, unwrap_scalar=True)
        doc = next(YamlDecoder(options).decode_documents("a:\n  b:\n    - 1\n"))
        assert encoder.encode_to_string(doc) == "a:\n    b:\n        - 1\n"

    @pytest.mark.skipif(not TEST_SETS.exists(), reason="23_testSets not available")
    @pytest.mark.parametrize("path", sorted(TEST_SETS.glob("1*.yml")))
    def test_test_sets_parse_and_round_trip_semantically(self, path) -> None:
        text = path.read_text(encoding="utf-8")
        before = [to_python(d) for d in YamlDecoder().decode_documents(text)]
        after_text = round_trip(text)
        after = [to_python(d) for d in YamlDecoder().decode_documents(after_text)]
        assert before == after
