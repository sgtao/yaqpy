"""形式レジストリ：登録するだけで、拡張子からの判定・入出力の一覧・GUI の選択肢に現れること。"""

from __future__ import annotations

import unittest

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


class RegistrationTests(unittest.TestCase):
    def test_extension_selects_the_registered_format(self) -> None:
        registry = _demo_registry()
        self.assertEqual(registry.from_filename("a.demo").name, "demo")
        self.assertEqual(registry.from_filename("dir/a.DMO").name, "demo")

    def test_unknown_extension_still_means_yaml(self) -> None:
        self.assertEqual(_demo_registry().from_filename("a.unknown").name, "yaml")

    def test_input_and_output_lists_follow_the_codecs(self) -> None:
        both = _demo_registry()
        self.assertIn("demo", both.input_formats())
        self.assertIn("demo", both.output_formats())
        only_out = _demo_registry(decoder=False)
        self.assertNotIn("demo", only_out.input_formats())
        self.assertIn("demo", only_out.output_formats())

    def test_input_extensions_only_list_readable_formats(self) -> None:
        self.assertIn("demo", _demo_registry().input_extensions())
        self.assertIn("dmo", _demo_registry().input_extensions())
        self.assertNotIn("demo", _demo_registry(decoder=False).input_extensions())

    def test_builtin_registry_is_not_changed_by_a_copy(self) -> None:
        _demo_registry()
        with self.assertRaises(UnknownFormatError):
            builtin_formats().get("demo")

    def test_builtin_input_extensions_keep_the_original_four(self) -> None:
        extensions = builtin_formats().input_extensions()
        for expected in ("yaml", "yml", "json", "toon"):
            self.assertIn(expected, extensions)


class GuiChoicesTests(unittest.TestCase):
    def test_the_gui_derives_its_choices_from_the_registry(self) -> None:
        from yaqpy.gui import _di

        self.assertEqual(_di.open_extensions(), _di.make_service().formats.input_extensions())
        self.assertEqual(_di.input_format_choices()[1:],
                         _di.make_service().formats.input_formats())
        self.assertEqual(_di.output_format_choices()[1:],
                         _di.make_service().formats.output_formats())


if __name__ == "__main__":
    unittest.main()
