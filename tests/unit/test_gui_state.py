"""GuiState と Options 変換のテスト（GUI 設計書 5-4）。"""

from __future__ import annotations

import unittest

from yaqpy.gui.state import GuiState, build_options, truncate_for_display


class BuildOptionsTests(unittest.TestCase):
    def test_defaults_are_safe(self) -> None:
        options = build_options(GuiState())
        self.assertFalse(options.security.allow_env)
        self.assertFalse(options.security.allow_file)
        self.assertFalse(options.security.allow_system)
        self.assertEqual(options.limits.timeout_seconds, 10.0)
        self.assertEqual(options.input_format, "auto")

    def test_security_switches_are_applied(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        state.settings.allow_file = True
        options = build_options(state)
        self.assertTrue(options.security.allow_env)
        self.assertTrue(options.security.allow_file)

    def test_system_operator_is_never_allowed(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        self.assertFalse(build_options(state).security.allow_system)

    def test_indent_reaches_every_encoder(self) -> None:
        state = GuiState()
        state.query.indent = 4
        options = build_options(state)
        self.assertEqual(options.indent, 4)          # json が見る
        self.assertEqual(options.yaml.indent, 4)
        self.assertEqual(options.toon.indent, 4)

    def test_indent_zero_keeps_toon_valid(self) -> None:
        state = GuiState()
        state.query.indent = 0
        options = build_options(state)
        self.assertEqual(options.indent, 0)
        self.assertEqual(options.toon.indent, 2)     # toon は 1 未満を許さない

    def test_max_input_bytes(self) -> None:
        state = GuiState()
        state.settings.max_input_mib = 2
        self.assertEqual(build_options(state).limits.max_input_bytes, 2 * 1024 * 1024)


class TruncateTests(unittest.TestCase):
    def test_short_text_is_untouched(self) -> None:
        text = "a\nb\n"
        self.assertEqual(truncate_for_display(text, 10), (text, 0))

    def test_long_text_is_cut(self) -> None:
        text = "".join(f"line{i}\n" for i in range(100))
        shown, omitted = truncate_for_display(text, 10)
        self.assertEqual(omitted, 90)
        self.assertEqual(shown.count("\n"), 10)
        self.assertTrue(shown.startswith("line0\n"))

    def test_zero_means_no_limit(self) -> None:
        text = "a\nb\nc\n"
        self.assertEqual(truncate_for_display(text, 0), (text, 0))


class DiTests(unittest.TestCase):
    def test_format_choices(self) -> None:
        from yaqpy.gui._di import extension_for, input_format_choices, output_format_choices

        self.assertIn("yaml", input_format_choices())
        self.assertNotIn("props", input_format_choices())   # props は入力に使えない
        self.assertIn("props", output_format_choices())
        self.assertEqual(extension_for("json"), "json")
        self.assertEqual(extension_for("props"), "properties")


if __name__ == "__main__":
    unittest.main()
