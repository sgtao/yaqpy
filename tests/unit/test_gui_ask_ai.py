"""「AI に相談」画面（v0.7.0）。プロンプトへの反映のロジックと、画面のボタンの動き。"""

from __future__ import annotations

from unittest import mock

import pytest

from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.selfdoc import GUIDE_PROMPT_PLACEHOLDER, render_guide_prompt
from yaqpy.app.service import YqService
from yaqpy.gui.ask_ai import apply_user_input
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

try:
    import flet as ft
except ImportError:                                  # pragma: no cover
    ft = None


class ApplyUserInputTests:
    def test_the_placeholder_line_is_replaced(self) -> None:
        prompt = f"## 依頼\n\n{GUIDE_PROMPT_PLACEHOLDER}\n"
        assert apply_user_input(prompt, "a: 1 を b にしたい") == "## 依頼\n\na: 1 を b にしたい\n"

    def test_the_real_guide_prompt_ends_with_the_user_input(self) -> None:
        service = YqService(InMemoryFileSystem({}), StaticEnvironment({}))
        prompt = render_guide_prompt(service)
        out = apply_user_input(prompt, "name を取り出したい")
        assert GUIDE_PROMPT_PLACEHOLDER not in out
        assert out.rstrip().endswith("name を取り出したい")
        assert out.startswith(prompt[: prompt.index("## 依頼")])     # 前の部分は変えない

    def test_a_second_time_appends_at_the_end(self) -> None:
        once = apply_user_input(f"## 依頼\n\n{GUIDE_PROMPT_PLACEHOLDER}\n", "first")
        twice = apply_user_input(once, "second")
        assert twice == "## 依頼\n\nfirst\n\nsecond\n"

    def test_an_edited_prompt_without_the_placeholder_gets_an_append(self) -> None:
        assert apply_user_input("my own text", "more") == "my own text\n\nmore\n"

    @pytest.mark.parametrize("user_text", ["", "   ", "\n\n"])
    def test_an_empty_input_changes_nothing(self, user_text: str) -> None:
        assert apply_user_input("prompt", user_text) == "prompt"

    def test_only_the_first_placeholder_is_replaced(self) -> None:
        prompt = f"{GUIDE_PROMPT_PLACEHOLDER} / {GUIDE_PROMPT_PLACEHOLDER}"
        assert apply_user_input(prompt, "x") == f"x / {GUIDE_PROMPT_PLACEHOLDER}"


def make_ask_page():
    from yaqpy.gui.pages.ask_ai_page import AskAiPage

    fs = InMemoryFileSystem({})
    presenter = MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=GuiState())
    return AskAiPage(page=mock.MagicMock(), presenter=presenter), presenter


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class AskAiPageTests:
    async def test_the_prompt_is_built_when_first_shown_and_only_once(self) -> None:
        page, presenter = make_ask_page()
        assert not page._prompt.value
        await page.on_show()
        assert page._prompt.value == render_guide_prompt(presenter._service)
        page._prompt.value = "edited"
        await page.on_show()                          # 2 回目の表示では作り直さない（編集を消さない）
        assert page._prompt.value == "edited"

    async def test_apply_puts_the_left_input_into_the_prompt(self) -> None:
        page, _ = make_ask_page()
        await page.on_show()
        page._user_input.value = "items を name だけに"
        page._on_apply(mock.MagicMock())
        assert page._prompt.value.rstrip().endswith("items を name だけに")
        assert GUIDE_PROMPT_PLACEHOLDER not in page._prompt.value

    async def test_apply_twice_appends(self) -> None:
        page, _ = make_ask_page()
        await page.on_show()
        page._user_input.value = "one"
        page._on_apply(mock.MagicMock())
        page._user_input.value = "two"
        page._on_apply(mock.MagicMock())
        assert page._prompt.value.rstrip().endswith("one\n\ntwo")

    async def test_apply_with_an_empty_input_says_so_and_keeps_the_prompt(self) -> None:
        from yaqpy.gui import texts

        page, _ = make_ask_page()
        await page.on_show()
        before = page._prompt.value
        page._on_apply(mock.MagicMock())
        assert page._prompt.value == before
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_APPLY_EMPTY

    async def test_reset_returns_to_the_freshly_built_prompt(self) -> None:
        page, presenter = make_ask_page()
        await page.on_show()
        page._prompt.value = "edited"
        await page._on_reset(mock.MagicMock())
        assert page._prompt.value == render_guide_prompt(presenter._service)

    async def test_clear_buttons_empty_their_own_box_only(self) -> None:
        page, _ = make_ask_page()
        await page.on_show()
        page._user_input.value = "left"
        page._on_clear_prompt(mock.MagicMock())
        assert page._prompt.value == "" and page._user_input.value == "left"
        page._on_clear_input(mock.MagicMock())
        assert page._user_input.value == ""

    async def test_paste_puts_the_clipboard_into_the_left_box(self) -> None:
        page, _ = make_ask_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(return_value="from clipboard")):
            await page._on_paste(mock.MagicMock())
        assert page._user_input.value == "from clipboard"

    async def test_a_refused_clipboard_read_shows_a_hint(self) -> None:
        from yaqpy.gui import texts

        page, _ = make_ask_page()
        with mock.patch.object(ft.Clipboard, "get", mock.AsyncMock(side_effect=RuntimeError("no"))):
            await page._on_paste(mock.MagicMock())
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_PASTE_FAILED
        assert not page._user_input.value

    async def test_copy_sends_the_whole_prompt_and_reports_failure(self) -> None:
        from yaqpy.gui import texts

        page, _ = make_ask_page()
        await page.on_show()
        with mock.patch.object(ft.Clipboard, "set", mock.AsyncMock(return_value=None)) as set_:
            with mock.patch("yaqpy.gui.pages.ask_ai_page.asyncio.sleep", mock.AsyncMock()):
                await page._on_copy(mock.MagicMock())
        set_.assert_awaited_once_with(page._prompt.value)
        assert page._copy_button.content == texts.BTN_COPY          # 表示は元に戻る
        with mock.patch.object(ft.Clipboard, "set", mock.AsyncMock(side_effect=RuntimeError("no"))):
            await page._on_copy(mock.MagicMock())
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_COPY_FAILED


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class NavigationTests:
    def test_the_ask_ai_tab_is_the_third_page(self) -> None:
        from yaqpy.gui import _run, texts

        assert (_run.MAIN, _run.SETTINGS, _run.ASK_AI) == (0, 1, 2)
        assert texts.NAV_ASK_AI
