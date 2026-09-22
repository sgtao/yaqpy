"""Content-based format detection (a yaqpy extension): what the sample lines alone can tell."""

from __future__ import annotations

import pytest

from yaqpy.formats.sniff import detect_format


class SignatureTests:
    def test_xml_is_the_leading_angle_bracket(self) -> None:
        assert detect_format("<root><a>1</a></root>") == "xml"
        assert detect_format("  \n <?xml version='1.0'?><a/>") == "xml"

    def test_json_is_a_strict_parse(self) -> None:
        assert detect_format('{"a": 1, "b": [1, 2, 3]}') == "json"
        assert detect_format('["a", "b", 3]') == "json"

    def test_a_yaml_flow_style_that_is_not_strict_json_is_not_claimed_as_json(self) -> None:
        # unquoted keys: valid YAML flow mapping, not valid JSON
        assert detect_format("{a: 1, b: 2}") != "json"

    def test_toml_table_header_is_decisive(self) -> None:
        text = "[server]\nhost = localhost\nport = 8080\n"
        assert detect_format(text) == "toml"

    def test_toml_typed_values_without_a_header(self) -> None:
        text = 'name = "yaqpy"\nversion = "0.4.0"\n'
        assert detect_format(text) == "toml"
        assert detect_format("built = 2026-09-22\n") == "toml"
        assert detect_format("tags = [1, 2, 3]\n") == "toml"

    def test_plain_equals_lines_without_toml_typing_are_properties(self) -> None:
        text = "a.b.c = x\npets[0] = fido\npets[1] = rex\n"
        assert detect_format(text) == "props"

    def test_a_bare_true_false_value_is_not_enough_to_claim_toml(self) -> None:
        # ambiguous on purpose: plain-text "true"/"false" is common in Properties too
        assert detect_format("debug = true\nverbose = false\n") == "props"

    def test_csv_needs_a_repeated_delimiter_count(self) -> None:
        assert detect_format("name,age\nAlice,30\nBob,25\n") == "csv"

    def test_tsv_wins_when_tabs_dominate(self) -> None:
        assert detect_format("name\tage\nAlice\t30\n") == "tsv"

    def test_a_single_line_or_ragged_table_is_not_claimed(self) -> None:
        assert detect_format("just one line, with, commas") is None
        assert detect_format("a,b,c\nd,e\n") is None       # inconsistent field count

    def test_nothing_confident_returns_none(self) -> None:
        assert detect_format("") is None
        assert detect_format("   \n\n  ") is None
        assert detect_format("a: 1\nb: 2\n") is None        # ordinary YAML: no positive signature
        assert detect_format("- a\n- b\n") is None           # a YAML list


class BoundedReadTests:
    def test_only_the_head_matters_for_line_based_signals(self) -> None:
        toml = "name = \"x\"\n" + "\n".join(f"pad{i} = {i}" for i in range(500))
        assert detect_format(toml) == "toml"

    def test_a_huge_json_document_is_still_recognised_by_shape(self) -> None:
        big = '{"a": [' + ",".join(str(i) for i in range(2_000_000)) + "]}"
        assert len(big) > 8 * 1024 * 1024
        assert detect_format(big) == "json"

    def test_comments_are_skipped_when_sampling_toml_and_properties_lines(self) -> None:
        # "#" and "!" both introduce a comment in a Properties file (the actual decoder's rule)
        text = "# a comment\n! another\nkey = 1\n"
        assert detect_format(text) == "props"


class RegistryIntegrationTests:
    def test_guess_prefers_the_extension_over_content(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        # content looks like TOML, but the name says JSON: the extension must still win
        assert formats.guess("data.json", 'name = "x"\n').name == "json"

    def test_guess_falls_back_to_content_then_to_yaml(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        formats = builtin_formats()
        assert formats.guess("", '{"a": 1}').name == "json"
        assert formats.guess("data.unknownext", "a.b = 1\n").name == "props"
        assert formats.guess("<text>", "a: 1\n").name == "yaml"
        assert formats.guess("", "").name == "yaml"

    def test_public_detect_format_matches_the_registry(self) -> None:
        import yaqpy

        assert yaqpy.detect_format('{"a": 1}') == "json"
        assert yaqpy.detect_format("a: 1\n") == "yaml"
        assert yaqpy.detect_format("") == "yaml"


if __name__ == "__main__":
    pytest.main([__file__])
