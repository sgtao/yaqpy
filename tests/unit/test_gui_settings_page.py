"""設定画面のテスト（言語の選択。改修計画 5-4 節 U4）。"""

from __future__ import annotations

from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from yaqpy.gui.state import GuiState


def make_page(*, on_persist=None):
    from yaqpy.gui.pages.settings_page import SettingsPage

    state = GuiState()
    page = SettingsPage(page=mock.MagicMock(), state=state,
                        on_changed=mock.MagicMock(), on_persist=on_persist or mock.MagicMock())
    return page, state


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class LanguageSettingTests:
    def test_defaults_to_japanese(self) -> None:
        _page, state = make_page()
        assert state.settings.language == "ja"

    def test_selecting_english_updates_the_state(self) -> None:
        page, state = make_page()
        event = mock.MagicMock()
        event.control.value = "en"
        page._on_language(event)
        assert state.settings.language == "en"

    def test_selecting_a_language_persists_it(self) -> None:
        on_persist = mock.MagicMock()
        page, _state = make_page(on_persist=on_persist)
        event = mock.MagicMock()
        event.control.value = "en"
        page._on_language(event)
        on_persist.assert_called_once()

    def test_an_empty_selection_keeps_the_current_language(self) -> None:
        page, state = make_page()
        event = mock.MagicMock()
        event.control.value = None
        page._on_language(event)
        assert state.settings.language == "ja"

    def test_the_dropdown_offers_both_languages(self) -> None:
        page, _state = make_page()
        keys = {opt.key for opt in page._language.options}
        assert keys == {"ja", "en"}
