"""GuiState と Options 変換のテスト（GUI 設計書 5-4）。"""

from __future__ import annotations

from yaqpy.gui.state import GuiState, WebLimits, build_options, truncate_for_display


class BuildOptionsTests:
    def test_defaults_are_safe(self) -> None:
        options = build_options(GuiState())
        assert not options.security.allow_env
        assert not options.security.allow_file
        assert not options.security.allow_system
        assert options.limits.timeout_seconds == 10.0
        assert options.input_format == "auto"

    def test_security_switches_are_applied(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        state.settings.allow_file = True
        options = build_options(state)
        assert options.security.allow_env
        assert options.security.allow_file

    def test_system_operator_is_never_allowed(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        assert not build_options(state).security.allow_system

    def test_indent_reaches_every_encoder(self) -> None:
        state = GuiState()
        state.query.indent = 4
        options = build_options(state)
        assert options.indent == 4          # json が見る
        assert options.yaml.indent == 4
        assert options.toon.indent == 4

    def test_indent_zero_keeps_toon_valid(self) -> None:
        state = GuiState()
        state.query.indent = 0
        options = build_options(state)
        assert options.indent == 0
        assert options.toon.indent == 2     # toon は 1 未満を許さない

    def test_max_input_bytes(self) -> None:
        state = GuiState()
        state.settings.max_input_mib = 2
        assert build_options(state).limits.max_input_bytes == 2 * 1024 * 1024


class WebSessionTests:
    """Web 版のセッション（v0.6.0）：危険な演算子は強制無効、上限はサーバーの値が勝つ。"""

    MIB = 1024 * 1024

    def web_state(self, *, max_mib: int = 10, timeout: float = 5.0) -> GuiState:
        return GuiState(web=WebLimits(max_input_bytes=max_mib * self.MIB, timeout_seconds=timeout))

    def test_desktop_is_not_web(self) -> None:
        assert not GuiState().is_web

    def test_env_and_load_are_forced_off_even_if_the_settings_allow_them(self) -> None:
        state = self.web_state()
        state.settings.allow_env = True          # 保存された設定や画面の操作で入っても
        state.settings.allow_file = True
        security = build_options(state).security
        assert not security.allow_env
        assert not security.allow_file
        assert not security.allow_system

    def test_the_server_cap_wins_over_a_larger_setting(self) -> None:
        state = self.web_state(max_mib=10, timeout=5.0)
        state.settings.max_input_mib = 50        # デスクトップの既定のまま
        state.settings.timeout_seconds = 60.0
        limits = build_options(state).limits
        assert limits.max_input_bytes == 10 * self.MIB
        assert limits.timeout_seconds == 5.0
        assert state.max_input_bytes == 10 * self.MIB

    def test_a_smaller_setting_still_applies(self) -> None:
        state = self.web_state(max_mib=10, timeout=5.0)
        state.settings.max_input_mib = 1
        state.settings.timeout_seconds = 2.0
        limits = build_options(state).limits
        assert limits.max_input_bytes == 1 * self.MIB
        assert limits.timeout_seconds == 2.0


class TruncateTests:
    def test_short_text_is_untouched(self) -> None:
        text = "a\nb\n"
        assert truncate_for_display(text, 10) == (text, 0)

    def test_long_text_is_cut(self) -> None:
        text = "".join(f"line{i}\n" for i in range(100))
        shown, omitted = truncate_for_display(text, 10)
        assert omitted == 90
        assert shown.count("\n") == 10
        assert shown.startswith("line0\n")

    def test_zero_means_no_limit(self) -> None:
        text = "a\nb\nc\n"
        assert truncate_for_display(text, 0) == (text, 0)


class DiTests:
    def test_format_choices(self) -> None:
        from yaqpy.gui._di import extension_for, input_format_choices, output_format_choices

        assert "yaml" in input_format_choices()
        for name in ("json", "toon", "xml", "csv", "tsv", "props"):
            assert name in input_format_choices()      # 登録された形式は自動で選べる
        assert "props" in output_format_choices()
        assert extension_for("json") == "json"
        assert extension_for("props") == "properties"
