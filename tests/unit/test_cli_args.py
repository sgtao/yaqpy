"""resolve_invocation: how -p/-o "auto" resolves, and where it is deliberately left unresolved.

An extension that names a format always decides here, with no file read (unchanged, pure). When it
does not, "auto" is passed through instead of defaulting to yaml eagerly: the service resolves it
once it can read the content (tests/unit/test_format_autodetect.py covers that half).
"""

from __future__ import annotations

import pytest
from yaqpy.cli.args import resolve_invocation
from yaqpy.cli.parser import parse_args


def invoke(*argv: str, files: dict[str, str] | None = None, stdin_is_pipe: bool = False):
    files = files or {}
    ns = parse_args(list(argv))
    return resolve_invocation(ns, stdin_is_pipe=stdin_is_pipe, file_exists=lambda p: p in files,
                              read_file=lambda p: files[p])


class KnownExtensionTests:
    """Unchanged: the extension alone decides, exactly as before this feature existed."""

    def test_resolves_immediately_from_the_extension(self) -> None:
        inv = invoke(".", "a.json", files={"a.json": '{"a": 1}'})
        assert (inv.request.input_format, inv.request.output_format) == ("json", "json")
        # output is resolved too (mirrors input), so unwrap is already the json default - not deferred
        assert inv.request.unwrap_scalar is False

    def test_an_explicit_dash_p_also_needs_no_content(self) -> None:
        inv = invoke("-p", "toml", ".", "a.unknownext", files={"a.unknownext": "k = 1"})
        assert inv.request.input_format == "toml"


class UnresolvedExtensionTests:
    """No extension, an unknown one, or stdin with neither: "auto" passes through untouched."""

    def test_no_extension_stays_auto(self) -> None:
        inv = invoke(".", "a", files={"a": "irrelevant, never read here"})
        assert (inv.request.input_format, inv.request.output_format) == ("auto", "auto")

    def test_an_unrecognised_extension_stays_auto(self) -> None:
        inv = invoke(".", "a.log", files={"a.log": "irrelevant"})
        assert inv.request.input_format == "auto"

    def test_stdin_with_no_name_stays_auto(self) -> None:
        inv = invoke(".", stdin_is_pipe=True)
        assert inv.request.inputs[0].name == "-"
        assert inv.request.input_format == "auto"

    def test_unwrap_scalar_is_left_for_the_service_too(self) -> None:
        inv = invoke(".", "a", files={"a": "x"})
        assert inv.request.unwrap_scalar is None

    def test_an_explicit_unwrap_flag_still_wins_even_when_unresolved(self) -> None:
        inv = invoke("-r=false", ".", "a", files={"a": "x"})
        assert inv.request.unwrap_scalar is False

    def test_no_content_is_read_here_not_even_a_peek(self) -> None:
        def boom(path: str) -> str:
            raise AssertionError(f"resolve_invocation must not read {path!r}")

        inv = resolve_invocation(parse_args([".", "a"]), stdin_is_pipe=False,
                                 file_exists=lambda p: True, read_file=boom)
        assert inv.request.input_format == "auto"


class OutputDefaultWarningTests:
    """Go compatibility quirk, unaffected: an explicit -p with auto -o still defaults to yaml."""

    def test_warns_when_the_guessed_format_is_not_yaml(self) -> None:
        inv = invoke("-p", "json", ".", "a.json", files={"a.json": "{}"})
        assert inv.request.output_format == "yaml"
        assert any("yaqpy default output is now 'auto'" in w for w in inv.warnings)

    def test_no_warning_when_the_extension_cannot_be_guessed_either(self) -> None:
        inv = invoke("-p", "json", ".", "a.unknownext", files={"a.unknownext": "{}"})
        assert inv.request.output_format == "yaml"
        assert inv.warnings == ()


class BadFormatNameTests:
    def test_a_bad_dash_p_value_raises_before_evaluate(self) -> None:
        with pytest.raises(Exception, match="unknown format 'bogus'"):
            invoke("-p", "bogus", ".", "a", files={"a": "x"})

    def test_a_bad_dash_o_value_raises_before_evaluate(self) -> None:
        with pytest.raises(Exception, match="unknown format 'bogus'"):
            invoke("-o", "bogus", ".", "a.json", files={"a.json": "{}"})


if __name__ == "__main__":
    pytest.main([__file__])
