"""メイン画面の道具立て（v0.7.0）：未読込の画面のボタン、式欄の貼り付け・コピー・クリア。"""

from __future__ import annotations

from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from tests.unit.test_gui_main_page import make_page


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class InitialScreenButtonsTests:
    """未読込の画面に［ファイルを開く］と［貼り付け］のボタン。"""

    def _buttons(self, page):
        row = next(c for c in page._drop_hint.content.controls if isinstance(c, ft.Row))
        return {b.content: b for b in row.controls}

    def test_the_open_and_paste_buttons_are_on_the_initial_screen(self) -> None:
        from yaqpy.gui import texts

        page, _, _ = make_page()
        buttons = self._buttons(page)
        assert set(buttons) == {texts.BTN_OPEN_FILE, texts.BTN_PASTE}
        assert buttons[texts.BTN_OPEN_FILE].on_click == page._on_add_file
        assert page._drop_hint.on_click == page._on_add_file          # 枠全体のクリックも残す

    async def test_the_paste_button_opens_the_clipboard_as_a_document(self) -> None:
        page, _, state = make_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(return_value="a: 1\n")):
            await page._on_paste_button(mock.MagicMock())
        assert state.document.is_loaded and state.document.original_text == "a: 1\n"
        assert page._original.value == "a: 1\n"

    async def test_a_refused_clipboard_shows_a_hint_and_opens_nothing(self) -> None:
        from yaqpy.gui import texts

        page, _, state = make_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(side_effect=RuntimeError("no"))):
            await page._on_paste_button(mock.MagicMock())
        assert not state.document.is_loaded
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_PASTE_FAILED

    async def test_an_empty_clipboard_opens_nothing(self) -> None:
        page, _, state = make_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(return_value="  \n")):
            await page._on_paste_button(mock.MagicMock())
        assert not state.document.is_loaded


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class ExpressionToolsTests:
    """式欄の貼り付け・コピー・クリア。"""

    async def test_paste_replaces_the_expression_and_validates_it(self) -> None:
        page, _, state = make_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(return_value=".items[")):
            await page._on_expr_paste(mock.MagicMock())
        assert page._expr_field.value == state.query.expression == ".items["
        assert page._expr_field.error                        # 誤った式は赤枠で知らせる
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(return_value=".items[]")):
            await page._on_expr_paste(mock.MagicMock())
        assert page._expr_field.error is None

    async def test_a_refused_paste_keeps_the_expression(self) -> None:
        page, _, state = make_page()
        state.query.expression = ".a"
        page._expr_field.value = ".a"
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(side_effect=RuntimeError("no"))):
            await page._on_expr_paste(mock.MagicMock())
        assert page._expr_field.value == ".a"

    async def test_copy_sends_the_expression(self) -> None:
        from yaqpy.gui import texts

        page, _, _ = make_page()
        page._expr_field.value = ".a | .b"
        with mock.patch.object(ft.Clipboard, "set", mock.AsyncMock(return_value=None)) as set_:
            await page._on_expr_copy(mock.MagicMock())
        set_.assert_awaited_once_with(".a | .b")
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_EXPR_COPIED

    def test_clear_empties_the_expression_and_the_add_pipe_button(self) -> None:
        page, _, state = make_page()
        state.query.expression = ".a"
        page._expr_field.value = ".a"
        page._on_expr_clear(mock.MagicMock())
        assert page._expr_field.value == state.query.expression == ""
        assert page._add_button.disabled
        assert page._expr_field.error is None

    def test_the_tools_sit_between_the_field_and_the_run_button(self) -> None:
        page, _, _ = make_page()
        bars = [c for c in page.control.controls[4].controls
                if isinstance(c, ft.Row) and page._expr_field in c.controls]
        order = bars[0].controls
        assert order.index(page._expr_field) < order.index(page._expr_tools) < order.index(
            page._run_button)
