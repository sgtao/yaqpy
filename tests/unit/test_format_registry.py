"""形式レジストリ：登録するだけで、拡張子からの判定・入出力の一覧・GUI の選択肢に現れること。"""

from __future__ import annotations

import pytest
from yaqpy.errors import UnknownFormatError
from yaqpy.formats.registry import FormatRegistry, FormatSpec, builtin_formats


def _demo_registry(*, decoder: bool = True, encoder: bool = True) -> FormatRegistry:
    registry = builtin_formats().copy()
    registry.register(FormatSpec(
        "demo", ("dm",), (".demo", ".dmo"),
        decoder_factory=(lambda o: object()) if decoder else None,
        encoder_factory=(lambda o, u: object()) if encoder else None,
    ))
    return registry


class RegistrationTests:
    def test_extension_selects_the_registered_format(self) -> None:
        registry = _demo_registry()
        assert registry.from_filename("a.demo").name == "demo"
        assert registry.from_filename("dir/a.DMO").name == "demo"

    def test_unknown_extension_still_means_yaml(self) -> None:
        assert _demo_registry().from_filename("a.unknown").name == "yaml"

    def test_input_and_output_lists_follow_the_codecs(self) -> None:
        both = _demo_registry()
        assert "demo" in both.input_formats()
        assert "demo" in both.output_formats()
        only_out = _demo_registry(decoder=False)
        assert "demo" not in only_out.input_formats()
        assert "demo" in only_out.output_formats()

    def test_input_extensions_only_list_readable_formats(self) -> None:
        assert "demo" in _demo_registry().input_extensions()
        assert "dmo" in _demo_registry().input_extensions()
        assert "demo" not in _demo_registry(decoder=False).input_extensions()

    def test_builtin_registry_is_not_changed_by_a_copy(self) -> None:
        _demo_registry()
        with pytest.raises(UnknownFormatError):
            builtin_formats().get("demo")

    def test_builtin_input_extensions_keep_the_original_four(self) -> None:
        extensions = builtin_formats().input_extensions()
        for expected in ("yaml", "yml", "json", "toon"):
            assert expected in extensions


class GuiChoicesTests:
    def test_the_gui_derives_its_choices_from_the_registry(self) -> None:
        from yaqpy.gui import _di

        assert _di.open_extensions() == _di.make_service().formats.input_extensions()
        assert _di.input_format_choices()[1:] == _di.make_service().formats.input_formats()
        assert _di.output_format_choices()[1:] == _di.make_service().formats.output_formats()
