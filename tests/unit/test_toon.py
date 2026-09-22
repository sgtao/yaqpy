"""TOON codec tests (spec v4.1). Encoder tests here; decoder tests are added with
the input-format support."""

from __future__ import annotations


import pytest
import yaqpy
from yaqpy import Options, ToonOptions
from yaqpy.core.model import to_python
from yaqpy.formats.toon_codec import (
    ToonDecoder, ToonError, canonical_number, encode_key, encode_string,
)

TOON = Options(output_format="toon")


def toon(yaml_text: str, expression: str = ".", **toon_opts: object) -> str:
    options = Options(output_format="toon", toon=ToonOptions(**toon_opts)) if toon_opts else TOON
    return yaqpy.evaluate(expression, yaml_text, options=options)


class ScalarRules:
    @pytest.mark.parametrize("text", ("", " x", "x ", "true", "false", "null", "1", "1.5", "1e3", "+1", "a,b", "a:b",
                 'a"b', "a\\b", "[x]", "{x}", "-x", "-", "#x", "#", "line\nbreak", "tab\tx"))
    def test_strings_that_must_be_quoted(self, text) -> None:
        assert encode_string(text, ",").startswith('"'), text

    def test_strings_left_plain(self) -> None:
        for text in ("Alice", "hello world", "a.b", "日本語", "x-y", "a|b"):
            assert encode_string(text, ",") == text
        # only the active delimiter forces quotes
        assert encode_string("a,b", "\t") == "a,b"
        assert encode_string("a\tb", "\t") == '"a\\tb"'
        assert encode_string("a|b", "|") == '"a|b"'

    def test_escapes(self) -> None:
        assert encode_string('q"\\\n\r\t\x01', ",") == '"q\\"\\\\\\n\\r\\t\\u0001"'

    def test_keys(self) -> None:
        assert encode_key("a_b.c1") == "a_b.c1"
        assert encode_key("my-key") == '"my-key"'
        assert encode_key("1abc") == '"1abc"'
        assert encode_key("日本") == '"日本"'

    def test_canonical_numbers(self) -> None:
        assert canonical_number(1.5) == "1.5"
        assert canonical_number(1.50) == "1.5"
        assert canonical_number(6.0) == "6"
        assert canonical_number(-0.0) == "0"
        assert canonical_number(1e17) == "100000000000000000"
        assert canonical_number(1e21) == "1e+21"
        assert canonical_number(1e-7) == "1e-7"
        assert canonical_number(0.000015) == "0.000015"
        assert canonical_number(2 ** 60) == "1152921504606846976"


class EncoderTests:
    def test_flat_and_nested_objects(self) -> None:
        out = toon("name: Alice\nage: 30\nnested:\n  x: 1\n  y: [1, 2]\nempty: []\nobj: {}\n")
        assert out == "name: Alice\nage: 30\nnested:\n  x: 1\n  y[2]: 1,2\nempty: []\nobj:\n"

    def test_inline_primitive_array(self) -> None:
        assert toon('tags: [admin, "a,b", "", 3, true, null]\n') == 'tags[6]: admin,"a,b","",3,true,null\n'

    def test_tabular_array(self) -> None:
        out = toon("items:\n  - sku: A1\n    qty: 2\n    price: 9.99\n  - sku: B2\n    qty: 1\n    price: 14.5\n")
        assert out == "items[2]{sku,qty,price}:\n  A1,2,9.99\n  B2,1,14.5\n"

    def test_tabular_with_nested_uniform_column(self) -> None:
        out = toon("orders:\n  - id: 1\n    customer: {name: Ada, country: DK}\n"
                   "  - id: 2\n    customer: {name: Bob, country: UK}\n")
        assert out == "orders[2]{id,customer{name,country}}:\n  1,Ada,DK\n  2,Bob,UK\n"

    def test_list_array_for_mixed_items(self) -> None:
        out = toon("mixed: [1, two, {a: 1}, [1, 2], null, true]\n")
        assert out == "mixed[6]:\n  - 1\n  - two\n  - a: 1\n  - [2]: 1,2\n  - null\n  - true\n"

    def test_list_array_objects_with_different_keys(self) -> None:
        out = toon("list:\n  - a: 1\n    b: 2\n  - a: 3\n")
        assert out == "list[2]:\n  - a: 1\n    b: 2\n  - a: 3\n"

    def test_tabular_header_on_hyphen_line(self) -> None:
        out = toon("deep:\n  - n: 1\n    t: [{x: 1}, {x: 2}]\n")
        assert out == "deep[1]:\n  - n: 1\n    t[2]{x}:\n      1\n      2\n"

    def test_keyed_tabular_object(self) -> None:
        text = "users:\n  alice: {age: 30, city: Berlin}\n  bob: {age: 25, city: Oslo}\n"
        assert toon(text) == "users[2:]{age,city}:\n  alice: 30,Berlin\n  bob: 25,Oslo\n"
        assert toon(text, keyed_tabular=False) == "users:\n  alice:\n    age: 30\n    city: Berlin\n  bob:\n    age: 25\n    city: Oslo\n"

    def test_root_forms(self) -> None:
        assert toon("[r, o, o, t]\n") == "[4]: r,o,o,t\n"
        assert toon("[]\n") == "[]\n"
        assert toon("scalar\n") == "scalar\n"
        assert toon('"123"\n') == '"123"\n'
        assert toon("42\n") == "42\n"
        assert toon("null\n") == "null\n"
        assert toon("{}\n") == ""
        assert toon("- a: 1\n  b: 2\n- a: 3\n  b: 4\n") == "[2]{a,b}:\n  1,2\n  3,4\n"

    def test_numbers_keep_yaml_meaning(self) -> None:
        assert toon("f: [1.50, 0x1F, 1_000, 1e21, -0.0]\n") == "f[5]: 1.5,31,1000,1e+21,0\n"

    def test_delimiters(self) -> None:
        text = 'items: [{a: 1, b: "x,y"}, {a: 2, b: y}]\n'
        assert toon(text, delimiter="\t") == "items[2\t]{a\tb}:\n  1\tx,y\n  2\ty\n"
        assert toon(text, delimiter="|") == "items[2|]{a|b}:\n  1|x,y\n  2|y\n"
        assert toon("tags: [a, b]\n", delimiter="|") == "tags[2|]: a|b\n"

    def test_indent_option(self) -> None:
        assert toon("a:\n  b:\n    - x: 1\n    - y: 2\n", indent=4) == "a:\n    b[2]:\n        - x: 1\n        - y: 2\n"

    def test_comments_are_dropped(self) -> None:
        out = toon("# head\na: 1 # line\n# foot\n")
        assert out == "a: 1\n"

    def test_aliases_are_exploded(self) -> None:
        assert toon("base: &b {v: 1}\nother: *b\nlist: [*b]\n") == "base:\n  v: 1\nother:\n  v: 1\nlist[1]{v}:\n  1\n"

    def test_multiple_results_and_documents_are_blank_line_separated(self) -> None:
        assert toon("items: [{a: 1}, {a: 2}]\n", ".items[]") == "a: 1\n\na: 2\n"
        assert toon("a: 1\n---\nb: 2\n") == "a: 1\n\nb: 2\n"

    def test_unwrap_scalar_flag(self) -> None:
        options = Options(output_format="toon", unwrap_scalar=True)
        assert yaqpy.evaluate(".a", 'a: "123"\n', options=options) == "123\n"
        assert yaqpy.evaluate(".a", 'a: "123"\n', options=TOON) == '"123"\n'

    def test_invalid_options(self) -> None:
        with pytest.raises(ValueError):
            ToonOptions(delimiter=";")
        with pytest.raises(ValueError):
            ToonOptions(indent=0)


class DecoderTests:
    def decode(self, text: str, **toon_opts: object):
        options = Options(toon=ToonOptions(**toon_opts)) if toon_opts else Options()
        docs = list(ToonDecoder(options).decode_documents(text))
        return [to_python(d) for d in docs]

    def test_objects_and_inline_arrays(self) -> None:
        text = "name: Alice\nage: 30\ntags[2]: a,b\nempty: []\nobj:\nnested:\n  x: 1\n  y[2]: 1,2\n"
        assert self.decode(text) == [{"name": "Alice", "age": 30, "tags": ["a", "b"],
                                    "empty": [], "obj": {}, "nested": {"x": 1, "y": [1, 2]}}]

    def test_tabular_and_nested_field_groups(self) -> None:
        assert self.decode("items[2]{sku,qty,price}:\n  A1,2,9.99\n  B2,1,14.5\n") == [{"items": [{"sku": "A1", "qty": 2, "price": 9.99},
                           {"sku": "B2", "qty": 1, "price": 14.5}]}]
        assert self.decode("objs[2]{a,b{c}}:\n  1,2\n  3,4\n") == [{"objs": [{"a": 1, "b": {"c": 2}}, {"a": 3, "b": {"c": 4}}]}]

    def test_list_arrays(self) -> None:
        text = "mixed[6]:\n  - 1\n  - two\n  - a: 1\n  - [2]: 1,2\n  - null\n  - true\n"
        assert self.decode(text) == [{"mixed": [1, "two", {"a": 1}, [1, 2], None, True]}]
        assert self.decode("list[2]:\n  - a: 1\n    b: 2\n  - a: 3\nafter: 1\n") == [{"list": [{"a": 1, "b": 2}, {"a": 3}], "after": 1}]
        assert self.decode("deep[1]:\n  - n: 1\n    t[2]{x}:\n      1\n      2\n") == [{"deep": [{"n": 1, "t": [{"x": 1}, {"x": 2}]}]}]
        assert self.decode("nested[1]:\n  - inner[2]:\n      - 1\n      - 2\n") == [{"nested": [{"inner": [1, 2]}]}]

    def test_keyed_tabular_object(self) -> None:
        assert self.decode("users[2:]{age,city}:\n  alice: 30,Berlin\n  bob: 25,Oslo\n") == [{"users": {"alice": {"age": 30, "city": "Berlin"},
                           "bob": {"age": 25, "city": "Oslo"}}}]
        assert self.decode("[2:]{v}:\n  a: 1\n  b: 1\n") == [{"a": {"v": 1}, "b": {"v": 1}}]

    def test_quoted_strings_and_escapes(self) -> None:
        text = 's[9]: ""," x","1","true","a,b","a:b","-x","a\\"b","line\\nbreak"\n'
        assert self.decode(text) == [{"s": ["", " x", "1", "true", "a,b", "a:b", "-x", 'a"b', "line\nbreak"]}]
        assert self.decode('"my-key": 1\nk.v: 2\n"1abc": 3\n') == [{"my-key": 1, "k.v": 2, "1abc": 3}]
        assert self.decode('u: "\\u00e9\\t"\n') == [{"u": "\u00e9\t"}]

    def test_root_forms(self) -> None:
        assert self.decode("[4]: r,o,o,t\n") == [["r", "o", "o", "t"]]
        assert self.decode("[]\n") == [[]]
        assert self.decode("scalar\n") == ["scalar"]
        assert self.decode('"123"\n') == ["123"]
        assert self.decode("42\n") == [42]
        assert self.decode("null\n") == [None]
        assert self.decode("") == []
        assert self.decode("# only a comment\n") == []
        assert self.decode("[2]{a,b}:\n  1,2\n  3,4\n") == [[{"a": 1, "b": 2}, {"a": 3, "b": 4}]]

    def test_delimiters_and_comments(self) -> None:
        assert self.decode("items[2\t]{a\tb}:\n  1\tx,y\n  2\ty\n") == [{"items": [{"a": 1, "b": "x,y"}, {"a": 2, "b": "y"}]}]
        assert self.decode("tags[2|]: a|b\n") == [{"tags": ["a", "b"]}]
        assert self.decode("# c\na: 1\n\n  # indented comment\nb: 2\n") == [{"a": 1, "b": 2}]

    def test_legacy_header_forms_are_accepted(self) -> None:
        assert self.decode("legacy[0]:\nold[2,]{a,b}:\n  1,2\n  3,4\nhash[#2]: x,y\n") == [{"legacy": [], "old": [{"a": 1, "b": 2}, {"a": 3, "b": 4}], "hash": ["x", "y"]}]

    def test_numbers_keep_their_text(self) -> None:
        docs = list(ToonDecoder(Options()).decode_documents("f[3]: 1.50,1e+21,007\n"))
        values = docs[0].get_map_value("f").content
        assert [(v.tag, v.value) for v in values] == [("!!float", "1.50"), ("!!float", "1e+21"), ("!!str", "007")]

    @pytest.mark.parametrize("text", ("wrong[3]: a,b\n", "items[1]{a,b}:\n  1\n", "x: 1\nx: 2\n", "a:\n   b: 1\n",
                 "  a: 1\n", 'a: "unterminated\n', "a:\n\tb: 1\n", "items[2]{}:\n",
                 "items[1]:\n  - 1\n  - 2\n"))
    def test_strict_errors(self, text) -> None:
        with pytest.raises(ToonError):
            self.decode(text)

    def test_non_strict_tolerates_counts(self) -> None:
        assert self.decode("wrong[3]: a,b\n", strict=False) == [{"wrong": ["a", "b"]}]
        assert self.decode("x: 1\nx: 2\n", strict=False) == [{"x": 2}]

    def test_error_reports_line(self) -> None:
        with pytest.raises(ToonError) as ctx:
            self.decode("a: 1\nb[2]: x\n")
        assert ctx.value.line == 2


class RoundTripTests:
    YAML_INPUTS = [
        "name: Alice\nage: 30\ntags: [a, b]\nempty: []\nobj: {}\nnested:\n  x: 1\n  y: [1, 2]\n",
        "items:\n  - sku: A1\n    qty: 2\n    price: 9.99\n  - sku: B2\n    qty: 1\n    price: 14.5\n",
        "mixed: [1, two, {a: 1}, [1, 2], null, true]\n",
        "orders:\n  - id: 1\n    customer: {name: Ada, country: DK}\n  - id: 2\n    customer: {name: Bob, country: UK}\n",
        "users:\n  alice: {age: 30, city: Berlin}\n  bob: {age: 25, city: Oslo}\n",
        's: ["", " x", "1", "true", "a,b", "a:b", "-x", "#x", 日本語, "a\\"b"]\n',
        '"my-key": 1\nk.v: 2\n1abc: 3\n',
        "f: [1.5, 1e21, 1e-7, 100000000000000000000, -0.0, 0x1F]\n",
        "[r, o, o, t]\n", "scalar\n", '"123"\n', "42\n", "null\n", "[]\n",
        "list:\n  - a: 1\n    b: 2\n  - a: 3\n",
        "deep:\n  - n: 1\n    t: [{x: 1}, {x: 2}]\n",
        "k: 2001-12-14\nt: \"12:30\"\n",
    ]

    def test_yaml_to_toon_to_yaml_keeps_the_data(self) -> None:
        from yaqpy.formats.yaml.codec import YamlDecoder

        for text in self.YAML_INPUTS:
            before = [to_python(d) for d in YamlDecoder(Options()).decode_documents(text)]
            toon_text = yaqpy.evaluate(".", text, options=TOON)
            after = [to_python(d) for d in ToonDecoder(Options()).decode_documents(toon_text)]
            # -0.0 and 0x1F are canonicalised on purpose
            if "f:" in text:
                before = [{"f": [1.5, 1e21, 1e-7, 100000000000000000000, 0, 31]}]
            assert after == before
            # and back to TOON: the encoder output is stable
            assert yaqpy.evaluate(".", toon_text, options=Options(input_format="toon", output_format="toon")) == toon_text

    @pytest.mark.parametrize("delimiter", (",", "\t", "|"))
    def test_delimiter_round_trip(self, delimiter) -> None:
        options = Options(output_format="toon", toon=ToonOptions(delimiter=delimiter))
        toon_text = yaqpy.evaluate(".", 'items: [{a: 1, b: "x,y|z"}, {a: 2, b: "q\\tw"}]\n', options=options)
        back = [to_python(d) for d in ToonDecoder(Options()).decode_documents(toon_text)]
        assert back == [{"items": [{"a": 1, "b": "x,y|z"}, {"a": 2, "b": "q\tw"}]}]


class CrossCheckWithPythonToon:
    """Optional: compare simple structures with the third-party python-toon package."""

    @pytest.fixture(scope="class")
    def toon(self):
        return pytest.importorskip("toon", reason="python-toon is not installed")

    def test_decoder_agrees_with_python_toon(self, toon) -> None:
        texts = [
            "name: Alice\nage: 30\ntags[2]: a,b\nnested:\n  x: 1\n  y[2]: 1,2\n",
            "items[2]{sku,qty,price}:\n  A1,2,9.99\n  B2,1,14.5\n",
            "list[2]:\n  - a: 1\n    b: 2\n  - a: 3\n",
            '"my-key": 1\nk.v: 2\n"1abc": 3\n',
            "[4]: r,o,o,t\n", "scalar\n", "42\n", "null\n",
        ]
        for text in texts:
            reference = toon.decode(text)
            ours = [to_python(d) for d in ToonDecoder(Options()).decode_documents(text)]
            assert ours == [reference]

    def test_simple_structures_match(self, toon) -> None:
        cases = [
            {"name": "Alice", "age": 30, "tags": ["a", "b"], "nested": {"x": 1, "y": [1, 2]}},
            {"items": [{"sku": "A1", "qty": 2, "price": 9.99}, {"sku": "B2", "qty": 1, "price": 14.5}]},
            {"list": [{"a": 1, "b": 2}, {"a": 3}]},
            {"my-key": 1, "k.v": 2, "1abc": 3},
            {"s": ["", " x", "1", "true", "a,b", "a:b", "-x", 'a"b', "日本語"]},
            ["r", "o", "o", "t"],
            "scalar", 42, None,
        ]
        from yaqpy.core.model import from_python
        from yaqpy.formats.toon_codec import ToonEncoder

        for data in cases:
            reference = toon.encode(data)
            # python-toon 0.1.x still writes the pre-4.1 `[N,]{...}` header form
            reference = reference.replace("[2,]", "[2]")
            ours = ToonEncoder(TOON).encode_to_string(from_python(data))
            assert ours == reference
