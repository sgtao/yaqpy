"""XML / CSV / TSV / TOML の設定（Options）と、Go 版と同じ名前の CLI フラグのテスト。"""

from __future__ import annotations

import pytest
from yaqpy.cli.args import InvocationError, resolve_invocation
from yaqpy.cli.parser import ArgumentError, parse_args, parse_separator
from yaqpy.options import CsvOptions, Options, TomlOptions, XmlOptions


def options_for(*argv: str) -> Options:
    ns = parse_args(list(argv))
    invocation = resolve_invocation(ns, stdin_is_pipe=False, file_exists=lambda _: False,
                                    read_file=lambda _: "")
    return invocation.request.options


class DefaultTests:
    def test_xml_defaults_follow_the_go_version(self) -> None:
        xml = XmlOptions()
        assert xml.attribute_prefix == "+@"
        assert xml.content_name == "+content"
        assert xml.proc_inst_prefix == "+p_"
        assert xml.directive_name == "+directive"
        assert xml.keep_namespace
        assert xml.raw_token
        assert not xml.strict_mode
        assert not xml.skip_proc_inst
        assert not xml.skip_directives

    def test_csv_and_toml_defaults(self) -> None:
        csv = CsvOptions()
        assert csv.separator == ","
        assert csv.auto_parse
        assert csv.tsv_auto_parse
        assert not TomlOptions().allow_lossy

    def test_options_carry_the_new_groups(self) -> None:
        options = Options()
        assert options.xml == XmlOptions()
        assert options.csv == CsvOptions()
        assert options.toml == TomlOptions()

    def test_csv_separator_must_be_one_character(self) -> None:
        with pytest.raises(ValueError):
            CsvOptions(separator="ab")


class FlagTests:
    def test_flags_default_to_the_option_defaults(self) -> None:
        options = options_for("-n", ".a")
        assert options.xml == XmlOptions()
        assert options.csv == CsvOptions()
        assert options.toml == TomlOptions()

    def test_xml_flags(self) -> None:
        options = options_for(
            "-n", "--xml-attribute-prefix", "@", "--xml-content-name", "#text",
            "--xml-proc-inst-prefix=+pi_", "--xml-directive-name", "+dir",
            "--xml-strict-mode", "--xml-keep-namespace=false", "--xml-raw-token=false",
            "--xml-skip-proc-inst", "--xml-skip-directives", ".a")
        assert options.xml == XmlOptions(
        indent=2, attribute_prefix="@", content_name="#text", proc_inst_prefix="+pi_",
        directive_name="+dir", strict_mode=True, keep_namespace=False, raw_token=False,
        skip_proc_inst=True, skip_directives=True)

    def test_xml_indent_follows_the_indent_flag(self) -> None:
        assert options_for("-n", "-I", "4", ".a").xml.indent == 4

    def test_csv_and_tsv_flags(self) -> None:
        options = options_for("-n", "--csv-separator", ";", "--csv-auto-parse=false",
                              "--tsv-auto-parse=false", ".a")
        assert options.csv == CsvOptions(separator=";", auto_parse=False,
                                       tsv_auto_parse=False)

    def test_bare_boolean_flag_does_not_swallow_the_expression(self) -> None:
        ns = parse_args(["--csv-auto-parse", ".a", "-n"])
        assert ns.csv_auto_parse
        assert ns.args == [".a"]

    def test_toml_allow_lossy(self) -> None:
        assert options_for("-n", "--toml-allow-lossy", ".a").toml.allow_lossy

    def test_separator_escapes(self) -> None:
        assert parse_separator("\\t") == "\t"
        assert parse_separator("|") == "|"

    def test_separator_of_the_wrong_length_is_rejected(self) -> None:
        with pytest.raises(ArgumentError):
            parse_args(["-n", "--csv-separator", "ab", ".a"])
        with pytest.raises(ArgumentError):
            parse_args(["-n", "--csv-separator", "", ".a"])

    def test_invocation_error_type_is_unchanged(self) -> None:
        # a sanity check that the new flags did not disturb the existing validation
        ns = parse_args(["-i", ".a"])
        with pytest.raises(InvocationError):
            resolve_invocation(ns, stdin_is_pipe=False, file_exists=lambda _: False,
                               read_file=lambda _: "")
