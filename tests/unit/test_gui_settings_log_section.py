"""設定画面の「実行ログ」の節（v0.7.0。デスクトップ版のみ）。"""

from __future__ import annotations

from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from yaqpy.gui import run_log, texts
from yaqpy.gui.state import GuiState, WebLimits


def make_page(*, web: bool = False, picker=None):
    from yaqpy.gui.pages.settings_page import SettingsPage

    state = GuiState(web=WebLimits(max_input_bytes=1024 * 1024, timeout_seconds=5.0) if web
                     else None)
    on_persist = mock.MagicMock()
    page = SettingsPage(page=mock.MagicMock(), state=state, on_changed=mock.MagicMock(),
                        on_persist=on_persist, picker=picker)
    return page, state, on_persist


def event(value):
    e = mock.MagicMock()
    e.control.value = value
    return e


def texts_in(control) -> list[str]:
    found: list[str] = []

    def walk(c) -> None:
        for attr in ("value", "content", "label"):
            v = getattr(c, attr, None)
            if isinstance(v, str):
                found.append(v)
        for child in getattr(c, "controls", None) or []:
            walk(child)
        inner = getattr(c, "content", None)
        if inner is not None and not isinstance(inner, str):
            walk(inner)

    walk(control)
    return found


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class LogSectionTests:
    def test_the_section_shows_the_current_values(self) -> None:
        page, state, _ = make_page()
        assert page._log_enabled.value is True
        assert page._log_dir.value == ""
        assert page._log_dir.helper == texts.SET_LOG_DIR_HINT.format(
            path=run_log.default_log_dir())
        assert (page._log_max_files.value, page._log_max_entry.value) == ("500", "1")

    def test_the_section_and_the_privacy_note_are_in_the_page(self) -> None:
        page, _, _ = make_page()
        all_text = "\n".join(texts_in(page.control))
        assert texts.SET_LOG in all_text and "平文" in texts.SET_LOG_NOTE
        assert texts.SET_LOG_NOTE in all_text

    def test_the_web_version_has_no_log_section(self) -> None:
        page, _, _ = make_page(web=True)
        all_text = "\n".join(texts_in(page.control))
        assert texts.SET_LOG not in all_text and texts.SET_LOG_ENABLED not in all_text

    def test_the_switch_updates_and_persists(self) -> None:
        page, state, persist = make_page()
        page._on_log_enabled(event(False))
        assert state.settings.log_enabled is False
        persist.assert_called_once()

    def test_a_typed_folder_is_kept_trimmed_and_persisted(self) -> None:
        page, state, persist = make_page()
        page._on_log_dir(event("  D:\\my logs  "))
        assert state.settings.log_dir == "D:\\my logs"
        persist.assert_called_once()

    def test_the_numbers_update_and_ignore_empty_or_zero(self) -> None:
        page, state, _ = make_page()
        page._on_log_max_files(event("20"))
        page._on_log_max_entry(event("3"))
        assert (state.settings.log_max_files, state.settings.log_max_entry_mib) == (20, 3)
        page._on_log_max_files(event(""))
        page._on_log_max_entry(event("0"))
        assert (state.settings.log_max_files, state.settings.log_max_entry_mib) == (20, 3)

    def test_leaving_a_field_restores_the_value_in_use(self) -> None:
        page, state, _ = make_page()
        page._on_log_max_files(event("20"))
        page._log_max_files.value = ""
        page._restore_fields(mock.MagicMock())
        assert page._log_max_files.value == "20"

    def test_reset_returns_to_the_default_folder(self) -> None:
        page, state, persist = make_page()
        page._on_log_dir(event("D:\\x"))
        page._on_reset_log_dir(mock.MagicMock())
        assert state.settings.log_dir == "" and page._log_dir.value == ""

    async def test_browse_puts_the_chosen_folder_into_the_field(self) -> None:
        picker = mock.MagicMock()
        picker.get_directory_path = mock.AsyncMock(return_value="D:\\picked")
        page, state, persist = make_page(picker=picker)
        await page._on_browse_log_dir(mock.MagicMock())
        assert state.settings.log_dir == "D:\\picked" and page._log_dir.value == "D:\\picked"
        persist.assert_called()

    async def test_a_cancelled_browse_changes_nothing(self) -> None:
        picker = mock.MagicMock()
        picker.get_directory_path = mock.AsyncMock(return_value=None)
        page, state, _ = make_page(picker=picker)
        await page._on_browse_log_dir(mock.MagicMock())
        assert state.settings.log_dir == ""

    async def test_a_browse_that_cannot_work_points_to_typing_the_path(self) -> None:
        """Flet 1.0 の ``get_directory_path`` は実機で確認できていない。動かなくても直接入力できる。"""
        picker = mock.MagicMock()
        picker.get_directory_path = mock.AsyncMock(side_effect=RuntimeError("unsupported"))
        page, state, _ = make_page(picker=picker)
        await page._on_browse_log_dir(mock.MagicMock())
        assert state.settings.log_dir == ""
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_FOLDER_PICK_FAILED
