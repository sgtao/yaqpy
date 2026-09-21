"""XML の入出力：変換規則、Go 版 yq と同じ寛容な読み方、安全性（実体を展開しない・深さ・サイズ）。"""

from __future__ import annotations

import io
import json
import time
import unittest
from typing import Any

import yaqpy
from yaqpy import FormatError, Limits, Options, XmlOptions
from yaqpy.cli.main import main
from yaqpy.formats import xml_tokens as xt
from yaqpy.formats.xml_codec import MAX_DEPTH


def xml_to_python(text: str, **xml: Any) -> Any:
    options = Options(input_format="xml", output_format="json", xml=XmlOptions(**xml))
    return json.loads(yaqpy.evaluate(".", text, options=options))


def xml_to_xml(text: str, *, indent: int = 2, **xml: Any) -> str:
    options = Options(input_format="xml", output_format="xml", indent=indent,
                      xml=XmlOptions(indent=indent, **xml))
    return yaqpy.evaluate(".", text, options=options)


def yaml_to_xml(text: str, *, indent: int = 2, **xml: Any) -> str:
    options = Options(input_format="yaml", output_format="xml", indent=indent,
                      xml=XmlOptions(indent=indent, **xml))
    return yaqpy.evaluate(".", text, options=options)


def run_cli(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ConversionTests(unittest.TestCase):
    def test_elements_attributes_and_text(self) -> None:
        self.assertEqual(xml_to_python('<cat legs="4"><says>meow</says></cat>'),
                         {"cat": {"+@legs": "4", "says": "meow"}})

    def test_text_next_to_attributes_goes_to_content(self) -> None:
        self.assertEqual(xml_to_python('<cat legs="4">meow</cat>'),
                         {"cat": {"+content": "meow", "+@legs": "4"}})

    def test_repeated_elements_become_a_list(self) -> None:
        self.assertEqual(xml_to_python("<zoo><a>1</a><a>2</a><b>3</b></zoo>"),
                         {"zoo": {"a": ["1", "2"], "b": "3"}})

    def test_values_are_strings(self) -> None:
        self.assertEqual(xml_to_python("<a><n>4</n><t>true</t></a>"),
                         {"a": {"n": "4", "t": "true"}})

    def test_empty_elements_are_null(self) -> None:
        self.assertEqual(xml_to_python("<a><b/><c></c></a>"), {"a": {"b": None, "c": None}})

    def test_text_is_trimmed_and_split_by_children(self) -> None:
        self.assertEqual(xml_to_python("<r>  one <a>x</a> two </r>"),
                         {"r": {"+content": ["one", "two"], "a": "x"}})

    def test_processing_instruction_and_directive_keys(self) -> None:
        data = xml_to_python('<?xml version="1.0"?><!DOCTYPE r SYSTEM "r.dtd"><r>1</r>')
        self.assertEqual(data, {"+p_xml": 'version="1.0"', "+directive": 'DOCTYPE r SYSTEM "r.dtd"',
                                "r": "1"})

    def test_attribute_prefix_and_content_name_options(self) -> None:
        data = xml_to_python('<a x="1">t</a>', attribute_prefix="@", content_name="#text")
        self.assertEqual(data, {"a": {"#text": "t", "@x": "1"}})

    def test_skip_flags(self) -> None:
        text = '<?xml version="1.0"?><!DOCTYPE r><r/>'
        self.assertEqual(xml_to_python(text, skip_proc_inst=True, skip_directives=True), {"r": None})

    def test_empty_input_is_null(self) -> None:
        self.assertIsNone(xml_to_python(""))
        self.assertIsNone(xml_to_python("  \n"))

    def test_unicode_names_and_text(self) -> None:
        self.assertEqual(xml_to_python("<名前>日本語</名前>"), {"名前": "日本語"})

    def test_bom_and_crlf(self) -> None:
        self.assertEqual(xml_to_python("﻿<a>x\r\ny</a>"), {"a": "x\ny"})


class TextEscapingTests(unittest.TestCase):
    def test_predefined_entities_and_character_references(self) -> None:
        self.assertEqual(xml_to_python("<a>&lt;&gt;&amp;&apos;&quot;&#65;&#x42;</a>"),
                         {"a": "<>&'\"AB"})

    def test_cdata_is_taken_literally(self) -> None:
        self.assertEqual(xml_to_python("<a><![CDATA[<b> & &lt;]]></a>"), {"a": "<b> & &lt;"})

    def test_unknown_entities_stay_text(self) -> None:
        self.assertEqual(xml_to_python("<a>&nbsp;&copy; &</a>"), {"a": "&nbsp;&copy; &"})

    def test_strict_mode_rejects_unknown_entities(self) -> None:
        with self.assertRaises(FormatError):
            xml_to_python("<a>&nbsp;</a>", strict_mode=True)
        with self.assertRaises(FormatError):
            xml_to_python("<a>a & b</a>", strict_mode=True)

    def test_attribute_values(self) -> None:
        self.assertEqual(xml_to_python("<a x='1 &amp; 2' y=\"a'b\"/>"),
                         {"a": {"+@x": "1 & 2", "+@y": "a'b"}})

    def test_unquoted_attribute_is_accepted_unless_strict(self) -> None:
        self.assertEqual(xml_to_python("<a x=1/>"), {"a": {"+@x": "1"}})
        with self.assertRaises(FormatError):
            xml_to_python("<a x=1/>", strict_mode=True)

    def test_illegal_character_is_an_error(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            xml_to_python("<a>&#0;</a>")
        self.assertIn("illegal character code U+0000", str(ctx.exception))


class LenientReadingTests(unittest.TestCase):
    """Go's decoder (RawToken, non-strict) accepts what a validating parser would reject."""

    def test_stray_end_tags_are_ignored(self) -> None:
        self.assertEqual(xml_to_python('<?xml version="1.0"?></b></a>'), {"+p_xml": 'version="1.0"'})

    def test_unclosed_elements_are_dropped(self) -> None:
        self.assertEqual(xml_to_python("<a><b>x"), None)

    def test_mismatched_end_tag_is_not_an_error(self) -> None:
        self.assertEqual(xml_to_python("<a><b>x</c></a>"), {"a": {"b": "x"}})

    def test_text_outside_the_root_at_the_start_is_an_error(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            xml_to_python("value<root>value</root>")
        self.assertEqual(str(ctx.exception),
                         "invalid XML: Encountered chardata [value] outside of XML node")

    def test_error_names_the_file(self) -> None:
        options = Options(input_format="xml")
        from yaqpy.formats.xml_codec import XmlDecoder

        with self.assertRaises(FormatError) as ctx:
            list(XmlDecoder(options).decode_documents("value<a/>", filename="x.xml"))
        self.assertTrue(str(ctx.exception).startswith("bad file 'x.xml': "))

    def test_syntax_errors_carry_the_line(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            xml_to_python("<a>\n<b\n")
        self.assertIn("XML syntax error on line", str(ctx.exception))
        self.assertIn("unexpected EOF", str(ctx.exception))

    def test_bad_names_and_comments_are_errors(self) -> None:
        for bad in ("<1a/>", "< a/>", "<a><!-- x -- y --></a>", "<a><!- x --></a>", "<a b='<'/>"):
            with self.subTest(bad=bad), self.assertRaises(FormatError):
                xml_to_python(bad)

    def test_unsupported_xml_version(self) -> None:
        with self.assertRaises(FormatError):
            xml_to_python('<?xml version="2.0"?><a/>')


class NamespaceTests(unittest.TestCase):
    TEXT = ('<map xmlns="urn:m" xmlns:x="urn:x" x:a="1"><item>v</item><x:item>w</x:item></map>')

    def test_prefixes_are_kept_as_written(self) -> None:
        self.assertEqual(xml_to_python(self.TEXT), {"map": {
            "+@xmlns": "urn:m", "+@xmlns:x": "urn:x", "+@x:a": "1", "item": "v", "x:item": "w"}})

    def test_drop_namespaces_when_keep_namespace_is_off(self) -> None:
        self.assertEqual(xml_to_python(self.TEXT, keep_namespace=False), {"map": {
            "+@xmlns": "urn:m", "+@x": "urn:x", "+@a": "1", "item": ["v", "w"]}})

    def test_translation_with_raw_token_off(self) -> None:
        self.assertEqual(xml_to_python(self.TEXT, raw_token=False), {"urn:m:map": {
            "+@xmlns": "urn:m", "+@xmlns:x": "urn:x", "+@urn:x:a": "1",
            "urn:m:item": "v", "urn:x:item": "w"}})

    def test_end_tags_are_matched_when_raw_token_is_off(self) -> None:
        with self.assertRaises(FormatError):
            xml_to_python("<a></b>", raw_token=False, strict_mode=True)
        with self.assertRaises(FormatError):
            xml_to_python("</a>", raw_token=False)
        with self.assertRaises(FormatError):
            xml_to_python("<a>", raw_token=False)


class DirectiveTests(unittest.TestCase):
    def test_directive_keeps_nested_declarations_and_drops_inner_comments(self) -> None:
        text = '<!DOCTYPE r [<!ENTITY a "x"><!-- c --><!ENTITY b "y>z">]><r/>'
        self.assertEqual(xml_to_python(text)["+directive"],
                         'DOCTYPE r [<!ENTITY a "x"> <!ENTITY b "y>z">]')

    def test_valid_directive_check(self) -> None:
        self.assertTrue(xt.is_valid_directive('DOCTYPE a [<!ENTITY b "c">]'))
        self.assertTrue(xt.is_valid_directive("DOCTYPE a"))
        self.assertFalse(xt.is_valid_directive("DOCTYPE a>"))
        self.assertFalse(xt.is_valid_directive("DOCTYPE a [<!ENTITY b"))
        self.assertFalse(xt.is_valid_directive('DOCTYPE "a'))


class CommentTests(unittest.TestCase):
    def test_comments_become_yaml_comments(self) -> None:
        options = Options(input_format="xml", output_format="yaml")
        out = yaqpy.evaluate(".", "<!-- head --><a><b>1</b><!-- tail --></a>", options=options)
        self.assertEqual(out, '# head\na:\n  b: "1"\n  # tail\n')

    def test_comments_survive_a_round_trip(self) -> None:
        text = "<!-- before -->\n<a><b>1</b><!-- after b --></a>\n"
        again = xml_to_xml(text)
        self.assertIn("<!-- before -->", again)
        self.assertIn("<!-- after b -->", again)
        self.assertEqual(xml_to_xml(again), again)


class EncodeTests(unittest.TestCase):
    def test_simple_map(self) -> None:
        self.assertEqual(yaml_to_xml("cat: purrs\n"), "<cat>purrs</cat>\n")

    def test_nested_map_is_indented(self) -> None:
        self.assertEqual(yaml_to_xml("a:\n  b: 1\n  c: 2\n"), "<a>\n  <b>1</b>\n  <c>2</c>\n</a>\n")

    def test_indent_option(self) -> None:
        self.assertEqual(yaml_to_xml("a:\n  b: 1\n", indent=4), "<a>\n    <b>1</b>\n</a>\n")
        self.assertEqual(yaml_to_xml("a:\n  b: 1\n", indent=0), "<a><b>1</b></a>\n")

    def test_list_repeats_the_element(self) -> None:
        self.assertEqual(yaml_to_xml("a:\n  b: [1, 2]\n"),
                         "<a>\n  <b>1</b>\n  <b>2</b>\n</a>\n")

    def test_attributes_and_content(self) -> None:
        self.assertEqual(yaml_to_xml('a:\n  +@x: "1"\n  +content: hi\n'), '<a x="1">hi</a>\n')

    def test_escaping_of_text(self) -> None:
        self.assertEqual(yaml_to_xml('a: "<&>\\"\'\\t"\n'), "<a>&lt;&amp;&gt;&#34;&#39;&#x9;</a>\n")

    def test_escaping_of_attribute_values(self) -> None:
        out = yaml_to_xml('a:\n  +@x: "1\\n\\"2\\" & <3>"\n')
        self.assertEqual(out, '<a x="1&#xA;&#34;2&#34; &amp; &lt;3&gt;"></a>\n')

    def test_scalar_at_the_top(self) -> None:
        self.assertEqual(yaml_to_xml("hello\n"), "hello")

    def test_sequence_at_the_top_is_refused(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            yaml_to_xml("[a, b]\n")
        self.assertEqual(str(ctx.exception),
                         "cannot encode !!seq to XML - only maps can be encoded")

    def test_attribute_must_be_a_scalar(self) -> None:
        with self.assertRaises(FormatError):
            yaml_to_xml("a:\n  +@x: [1]\n")

    def test_names_that_would_break_the_markup_are_refused(self) -> None:
        for bad in ('"a b": 1', '"a<b": 1', '"a>b": 1', '"a=b": 1'):
            with self.subTest(bad=bad), self.assertRaises(FormatError):
                yaml_to_xml(bad + "\n")

    def test_comment_containing_the_end_marker_is_refused(self) -> None:
        with self.assertRaises(FormatError):
            yaml_to_xml("a: 1 # x --> y\n")

    def test_prefix_options_apply_to_output(self) -> None:
        out = yaml_to_xml('a:\n  "@x": "1"\n  "#text": hi\n', attribute_prefix="@",
                          content_name="#text")
        self.assertEqual(out, '<a x="1">hi</a>\n')

    def test_processing_instruction_target_must_be_a_name(self) -> None:
        with self.assertRaises(FormatError):
            yaml_to_xml('"+p_a b": x\nr: 1\n')

    def test_directive_must_be_balanced(self) -> None:
        with self.assertRaises(FormatError):
            yaml_to_xml('+directive: "DOCTYPE a>"\nr: 1\n')


class RoundTripTests(unittest.TestCase):
    SAMPLES = (
        '<?xml version="1.0"?>\n<root a="1">\n  <item>x</item>\n  <item>y</item>\n</root>\n',
        "<a><b><c>deep</c></b></a>\n",
        '<x:r xmlns:x="urn:x"><x:k>v</x:k></x:r>\n',
        '<r><!-- c --><a>1</a></r>\n',
        '<?xml version="1.0"?>\n<!DOCTYPE r SYSTEM "r.dtd">\n<r>&custom;</r>\n',
    )

    def test_output_is_stable_after_the_first_pass(self) -> None:
        for text in self.SAMPLES:
            with self.subTest(text=text):
                first = xml_to_xml(text)
                self.assertEqual(xml_to_xml(first), first)

    def test_data_is_kept(self) -> None:
        for text in self.SAMPLES:
            with self.subTest(text=text):
                self.assertEqual(xml_to_python(xml_to_xml(text)), xml_to_python(text))

    def test_declared_entities_are_kept_as_text_not_expanded(self) -> None:
        out = xml_to_xml('<!DOCTYPE r [<!ENTITY e "boom">]><r>&e;</r>')
        self.assertIn("&amp;e;", out)
        self.assertNotIn("boom</r>", out)


class MixedContentTests(unittest.TestCase):
    """Text between child elements is grouped by the conversion; the words must not get lost."""

    def test_text_around_children_survives_a_round_trip(self) -> None:
        out = xml_to_xml("<a>Hello <b>bold</b> world <i>it</i> end</a>")
        self.assertIn("Hello world end", out)
        self.assertIn("<b>bold</b>", out)
        self.assertIn("<i>it</i>", out)

    def test_it_is_stable_after_the_first_pass(self) -> None:
        first = xml_to_xml("<a>x <b>1</b> y</a>")
        self.assertEqual(xml_to_xml(first), first)

    def test_text_pieces_without_children_come_back_as_repeated_elements(self) -> None:
        # a list of texts under one name is written as one element per text (as the Go yq does)
        out = xml_to_xml("<a>one<!-- c -->two</a>")
        self.assertIn(">one<", out)
        self.assertIn(">two<", out)

    def test_content_that_is_not_text_is_refused(self) -> None:
        with self.assertRaises(FormatError):
            yaml_to_xml("a:\n  +content:\n    k: v\n")
        with self.assertRaises(FormatError):
            yaml_to_xml("a:\n  +content: [[1], 2]\n")


class SafetyTests(unittest.TestCase):
    def test_billion_laughs_is_not_expanded(self) -> None:
        entities = "".join(
            f'<!ENTITY l{i} "' + f"&l{i - 1};" * 10 + '">' for i in range(1, 10))
        text = f'<!DOCTYPE z [<!ENTITY l0 "lol">{entities}]><z>&l9;</z>'
        started = time.monotonic()
        self.assertEqual(xml_to_python(text)["z"], "&l9;")
        self.assertLess(time.monotonic() - started, 2)

    def test_external_entities_are_not_read(self) -> None:
        text = '<!DOCTYPE f [<!ENTITY x SYSTEM "file:///etc/passwd">]><f>&x;</f>'
        self.assertEqual(xml_to_python(text)["f"], "&x;")

    def test_parameter_entities_are_not_expanded(self) -> None:
        text = '<!DOCTYPE f [<!ENTITY % p "x"> %p;]><f>1</f>'
        self.assertEqual(xml_to_python(text)["f"], "1")

    def test_too_deep_input_is_refused(self) -> None:
        with self.assertRaises(FormatError) as ctx:
            xml_to_python("<a>" * 100_000)
        self.assertIn("too deep", str(ctx.exception))

    def test_the_depth_limit_is_exact(self) -> None:
        ok = "<a>" * MAX_DEPTH + "x" + "</a>" * MAX_DEPTH
        self.assertIsNotNone(xml_to_python(ok))
        self.assertEqual(xml_to_xml(ok).count("<a>"), MAX_DEPTH)      # and it can be written again
        with self.assertRaises(FormatError):
            xml_to_python("<a>" * (MAX_DEPTH + 1) + "x" + "</a>" * (MAX_DEPTH + 1))

    def test_deep_data_is_refused_on_output(self) -> None:
        deep: Any = "x"
        for _ in range(MAX_DEPTH + 5):
            deep = {"a": deep}
        with self.assertRaises(FormatError):
            options = Options(output_format="xml")
            yaqpy.dump([yaqpy.load(json.dumps(deep), format="json")[0]], format="xml",
                       options=options)

    def test_depth_limit_follows_limits_when_smaller(self) -> None:
        options = Options(input_format="xml", limits=Limits(max_depth=3))
        with self.assertRaises(FormatError):
            yaqpy.evaluate(".", "<a><b><c><d>x</d></c></b></a>", options=options)

    def test_input_size_limit(self) -> None:
        options = Options(input_format="xml", limits=Limits(max_input_bytes=10))
        with self.assertRaises(FormatError):
            yaqpy.evaluate(".", "<a>" + "x" * 50 + "</a>", options=options)

    def test_many_siblings_are_fast(self) -> None:
        text = "<r>" + "".join(f"<k{i}>1</k{i}>" for i in range(20_000)) + "</r>"
        started = time.monotonic()
        self.assertEqual(len(xml_to_python(text)["r"]), 20_000)
        self.assertLess(time.monotonic() - started, 20)


class CliTests(unittest.TestCase):
    def test_extension_selects_xml(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        self.assertEqual(formats.from_filename("a.xml").name, "xml")
        self.assertIn("xml", formats.input_formats())
        self.assertIn("xml", formats.output_formats())
        self.assertIn("xml", formats.input_extensions())

    def test_cli_reads_and_writes_xml(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.xml")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write('<cat legs="4"><says>meow</says></cat>\n')
            code, out, err = run_cli(".cat.says", path)
            self.assertEqual((code, out, err), (0, "meow", ""))      # a scalar has no line end (as in Go)
            code, out, _ = run_cli("-o", "json", ".", path)
            self.assertEqual(json.loads(out), {"cat": {"+@legs": "4", "says": "meow"}})
            code, out, _ = run_cli("-p", "xml", "-o", "xml", "--xml-attribute-prefix", "+@",
                                   ".cat.+@legs = \"5\"", path)
            self.assertEqual(out, '<cat legs="5">\n  <says>meow</says>\n</cat>\n')

    def test_cli_error_message(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("value<a/>")
            code, _, err = run_cli(".", path)
            self.assertEqual(code, 1)
            self.assertIn("bad file", err)
            self.assertIn("outside of XML node", err)


if __name__ == "__main__":
    unittest.main()
