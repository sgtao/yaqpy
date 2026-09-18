"""TOON codec tests (spec v4.1). Encoder tests here; decoder tests are added with
the input-format support."""

from __future__ import annotations

import unittest

import pyyq
from pyyq import Options, ToonOptions
from pyyq.formats.toon_codec import canonical_number, encode_key, encode_string

TOON = Options(output_format="toon")


def toon(yaml_text: str, expression: str = ".", **toon_opts: object) -> str:
    options = Options(output_format="toon", toon=ToonOptions(**toon_opts)) if toon_opts else TOON
    return pyyq.evaluate(expression, yaml_text, options=options)


class ScalarRules(unittest.TestCase):
    def test_strings_that_must_be_quoted(self) -> None:
        for text in ("", " x", "x ", "true", "false", "null", "1", "1.5", "1e3", "+1", "a,b", "a:b",
                     'a"b', "a\\b", "[x]", "{x}", "-x", "-", "#x", "#", "line\nbreak", "tab\tx"):
            with self.subTest(text=text):
                self.assertTrue(encode_string(text, ",").startswith('"'), text)

    def test_strings_left_plain(self) -> None:
        for text in ("Alice", "hello world", "a.b", "日本語", "x-y", "a|b"):
            with self.subTest(text=text):
                self.assertEqual(encode_string(text, ","), text)
        # only the active delimiter forces quotes
        self.assertEqual(encode_string("a,b", "\t"), "a,b")
        self.assertEqual(encode_string("a\tb", "\t"), '"a\\tb"')
        self.assertEqual(encode_string("a|b", "|"), '"a|b"')

    def test_escapes(self) -> None:
        self.assertEqual(encode_string('q"\\\n\r\t\x01', ","), '"q\\"\\\\\\n\\r\\t\\u0001"')

    def test_keys(self) -> None:
        self.assertEqual(encode_key("a_b.c1"), "a_b.c1")
        self.assertEqual(encode_key("my-key"), '"my-key"')
        self.assertEqual(encode_key("1abc"), '"1abc"')
        self.assertEqual(encode_key("日本"), '"日本"')

    def test_canonical_numbers(self) -> None:
        self.assertEqual(canonical_number(1.5), "1.5")
        self.assertEqual(canonical_number(1.50), "1.5")
        self.assertEqual(canonical_number(6.0), "6")
        self.assertEqual(canonical_number(-0.0), "0")
        self.assertEqual(canonical_number(1e17), "100000000000000000")
        self.assertEqual(canonical_number(1e21), "1e+21")
        self.assertEqual(canonical_number(1e-7), "1e-7")
        self.assertEqual(canonical_number(0.000015), "0.000015")
        self.assertEqual(canonical_number(2 ** 60), "1152921504606846976")


class EncoderTests(unittest.TestCase):
    def test_flat_and_nested_objects(self) -> None:
        out = toon("name: Alice\nage: 30\nnested:\n  x: 1\n  y: [1, 2]\nempty: []\nobj: {}\n")
        self.assertEqual(out, "name: Alice\nage: 30\nnested:\n  x: 1\n  y[2]: 1,2\nempty: []\nobj:\n")

    def test_inline_primitive_array(self) -> None:
        self.assertEqual(toon('tags: [admin, "a,b", "", 3, true, null]\n'),
                         'tags[6]: admin,"a,b","",3,true,null\n')

    def test_tabular_array(self) -> None:
        out = toon("items:\n  - sku: A1\n    qty: 2\n    price: 9.99\n  - sku: B2\n    qty: 1\n    price: 14.5\n")
        self.assertEqual(out, "items[2]{sku,qty,price}:\n  A1,2,9.99\n  B2,1,14.5\n")

    def test_tabular_with_nested_uniform_column(self) -> None:
        out = toon("orders:\n  - id: 1\n    customer: {name: Ada, country: DK}\n"
                   "  - id: 2\n    customer: {name: Bob, country: UK}\n")
        self.assertEqual(out, "orders[2]{id,customer{name,country}}:\n  1,Ada,DK\n  2,Bob,UK\n")

    def test_list_array_for_mixed_items(self) -> None:
        out = toon("mixed: [1, two, {a: 1}, [1, 2], null, true]\n")
        self.assertEqual(out, "mixed[6]:\n  - 1\n  - two\n  - a: 1\n  - [2]: 1,2\n  - null\n  - true\n")

    def test_list_array_objects_with_different_keys(self) -> None:
        out = toon("list:\n  - a: 1\n    b: 2\n  - a: 3\n")
        self.assertEqual(out, "list[2]:\n  - a: 1\n    b: 2\n  - a: 3\n")

    def test_tabular_header_on_hyphen_line(self) -> None:
        out = toon("deep:\n  - n: 1\n    t: [{x: 1}, {x: 2}]\n")
        self.assertEqual(out, "deep[1]:\n  - n: 1\n    t[2]{x}:\n      1\n      2\n")

    def test_keyed_tabular_object(self) -> None:
        text = "users:\n  alice: {age: 30, city: Berlin}\n  bob: {age: 25, city: Oslo}\n"
        self.assertEqual(toon(text), "users[2:]{age,city}:\n  alice: 30,Berlin\n  bob: 25,Oslo\n")
        self.assertEqual(toon(text, keyed_tabular=False),
                         "users:\n  alice:\n    age: 30\n    city: Berlin\n  bob:\n    age: 25\n    city: Oslo\n")

    def test_root_forms(self) -> None:
        self.assertEqual(toon("[r, o, o, t]\n"), "[4]: r,o,o,t\n")
        self.assertEqual(toon("[]\n"), "[]\n")
        self.assertEqual(toon("scalar\n"), "scalar\n")
        self.assertEqual(toon('"123"\n'), '"123"\n')
        self.assertEqual(toon("42\n"), "42\n")
        self.assertEqual(toon("null\n"), "null\n")
        self.assertEqual(toon("{}\n"), "")
        self.assertEqual(toon("- a: 1\n  b: 2\n- a: 3\n  b: 4\n"), "[2]{a,b}:\n  1,2\n  3,4\n")

    def test_numbers_keep_yaml_meaning(self) -> None:
        self.assertEqual(toon("f: [1.50, 0x1F, 1_000, 1e21, -0.0]\n"), "f[5]: 1.5,31,1000,1e+21,0\n")

    def test_delimiters(self) -> None:
        text = 'items: [{a: 1, b: "x,y"}, {a: 2, b: y}]\n'
        self.assertEqual(toon(text, delimiter="\t"), "items[2\t]{a\tb}:\n  1\tx,y\n  2\ty\n")
        self.assertEqual(toon(text, delimiter="|"), "items[2|]{a|b}:\n  1|x,y\n  2|y\n")
        self.assertEqual(toon("tags: [a, b]\n", delimiter="|"), "tags[2|]: a|b\n")

    def test_indent_option(self) -> None:
        self.assertEqual(toon("a:\n  b:\n    - x: 1\n    - y: 2\n", indent=4),
                         "a:\n    b[2]:\n        - x: 1\n        - y: 2\n")

    def test_comments_are_dropped(self) -> None:
        out = toon("# head\na: 1 # line\n# foot\n")
        self.assertEqual(out, "a: 1\n")

    def test_aliases_are_exploded(self) -> None:
        self.assertEqual(toon("base: &b {v: 1}\nother: *b\nlist: [*b]\n"),
                         "base:\n  v: 1\nother:\n  v: 1\nlist[1]{v}:\n  1\n")

    def test_multiple_results_and_documents_are_blank_line_separated(self) -> None:
        self.assertEqual(toon("items: [{a: 1}, {a: 2}]\n", ".items[]"), "a: 1\n\na: 2\n")
        self.assertEqual(toon("a: 1\n---\nb: 2\n"), "a: 1\n\nb: 2\n")

    def test_unwrap_scalar_flag(self) -> None:
        options = Options(output_format="toon", unwrap_scalar=True)
        self.assertEqual(pyyq.evaluate(".a", 'a: "123"\n', options=options), "123\n")
        self.assertEqual(pyyq.evaluate(".a", 'a: "123"\n', options=TOON), '"123"\n')

    def test_invalid_options(self) -> None:
        with self.assertRaises(ValueError):
            ToonOptions(delimiter=";")
        with self.assertRaises(ValueError):
            ToonOptions(indent=0)


class CrossCheckWithPythonToon(unittest.TestCase):
    """Optional: compare simple structures with the third-party python-toon package."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import toon  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - dev dependency is optional
            raise unittest.SkipTest("python-toon is not installed")
        cls.toon = toon

    def test_simple_structures_match(self) -> None:
        cases = [
            {"name": "Alice", "age": 30, "tags": ["a", "b"], "nested": {"x": 1, "y": [1, 2]}},
            {"items": [{"sku": "A1", "qty": 2, "price": 9.99}, {"sku": "B2", "qty": 1, "price": 14.5}]},
            {"list": [{"a": 1, "b": 2}, {"a": 3}]},
            {"my-key": 1, "k.v": 2, "1abc": 3},
            {"s": ["", " x", "1", "true", "a,b", "a:b", "-x", 'a"b', "日本語"]},
            ["r", "o", "o", "t"],
            "scalar", 42, None,
        ]
        from pyyq.core.model import from_python
        from pyyq.formats.toon_codec import ToonEncoder

        for data in cases:
            with self.subTest(data=data):
                reference = self.toon.encode(data)
                # python-toon 0.1.x still writes the pre-4.1 `[N,]{...}` header form
                reference = reference.replace("[2,]", "[2]")
                ours = ToonEncoder(TOON).encode_to_string(from_python(data))
                self.assertEqual(ours, reference)


if __name__ == "__main__":
    unittest.main()
