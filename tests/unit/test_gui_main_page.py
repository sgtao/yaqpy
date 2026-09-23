"""メイン画面の見た目の約束：ファイル名の文字、プロパティ行と式の行の間隔、形式の札。
Flet の部品を組み立てるだけで、窓は開かない（flet が無い環境では飛ばす）。"""

from __future__ import annotations

from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter, RunViewModel
from yaqpy.gui.state import GuiState

FILES = {"/w/shop.xml": "<shop><item>pen</item></shop>\n", "/w/app.toml": "[db]\nport = 1\n"}


def make_page():
    from yaqpy.gui.pages.main_page import MainPage

    fs = InMemoryFileSystem(dict(FILES))
    state = GuiState()
    presenter = MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=state,
                              size_of=lambda p: len(fs.files[p].encode("utf-8")))
    page = MainPage(page=mock.MagicMock(), presenter=presenter, state=state, picker=mock.MagicMock())
    return page, presenter, state


def badge(page, side: str) -> tuple[bool, str]:
    container = getattr(page, f"_{side}_badge")
    return container.visible, getattr(page, f"_{side}_format").value


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class LayoutTests:
    def test_file_name_uses_the_button_font_size_and_bold(self) -> None:
        from yaqpy.gui.pages.main_page import BUTTON_TEXT_SIZE

        page, _, _ = make_page()
        assert BUTTON_TEXT_SIZE == 14                 # Flet の Button の文字と同じ大きさ
        assert page._file_label.size == BUTTON_TEXT_SIZE
        assert page._file_label.weight == ft.FontWeight.BOLD

    def test_the_property_row_and_the_expression_row_are_apart(self) -> None:
        from yaqpy.gui.pages.main_page import FILTER_ROW_SPACING

        page, _, _ = make_page()
        filter_bar = next(c for c in page.control.controls
                          if isinstance(c, ft.Column) and any(
                              isinstance(r, ft.Row) and page._property_dd in r.controls
                              for r in c.controls))
        assert FILTER_ROW_SPACING >= 12        # 以前は 2
        assert filter_bar.spacing == FILTER_ROW_SPACING

    def test_add_file_button_sits_to_the_right_of_the_file_name(self) -> None:
        """要望：ファイル名の右に [＋ファイルを追加] を置く。"""
        page, _, _ = make_page()
        file_bar = next(c for c in page.control.controls
                        if isinstance(c, ft.Row) and page._file_label in c.controls)
        names = file_bar.controls
        assert names.index(page._file_label) < names.index(page._add_file_button)

    def test_indent_field_is_wide_enough_for_the_label_to_stay_on_one_line(self) -> None:
        """要望：「インデント」ラベルが折り返さない幅にする。"""
        page, _, _ = make_page()
        assert page._indent_field.width >= 90


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class FormatBadgeTests:
    async def test_hidden_before_a_document_is_opened(self) -> None:
        page, _, _ = make_page()
        assert badge(page, "original") == (False, "")
        assert badge(page, "converted") == (False, "")

    async def test_shows_the_resolved_format_when_the_dropdowns_are_auto(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        assert state.query.input_format == "auto"
        assert badge(page, "original") == (True, "xml")
        assert badge(page, "converted") == (True, "xml")

    async def test_follows_a_specified_format(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        state.query.output_format = "toon"
        page._apply(await presenter.run())
        assert badge(page, "original") == (True, "xml")
        assert badge(page, "converted") == (True, "toon")
        state.query.input_format = "yaml"
        state.query.output_format = "auto"
        page._apply(RunViewModel())
        assert badge(page, "original") == (True, "yaml")
        assert badge(page, "converted") == (True, "yaml")

    async def test_stays_after_a_failed_run(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/app.toml")
        page._after_open()
        state.query.expression = ".db.("
        vm = await presenter.run()
        assert not vm.ok
        page._apply(vm)
        assert badge(page, "original") == (True, "toml")
        assert badge(page, "converted") == (True, "toml")

    async def test_hidden_again_when_the_document_is_closed(self) -> None:
        page, presenter, _ = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._on_close(mock.MagicMock())
        assert badge(page, "original") == (False, "")
        assert badge(page, "converted") == (False, "")

    async def test_pasted_text_is_yaml(self) -> None:
        page, presenter, _ = make_page()
        presenter.open_text("a: 1\n")
        page._after_open()
        assert badge(page, "original") == (True, "yaml")


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class OpenDialogTests:
    """開くダイアログは拡張子で絞らない：開いたあと中身で形式を判定する（yaqpy 独自）。

    「開く」と「＋ファイルを追加」は 1 つのボタン（``_on_add_file``）に統一されている。
    """

    async def test_the_file_picker_is_not_restricted_to_known_extensions(self) -> None:
        page, _, _ = make_page()
        page._picker.pick_files = mock.AsyncMock(return_value=[])
        await page._on_add_file(mock.MagicMock())
        _, kwargs = page._picker.pick_files.call_args
        assert "allowed_extensions" not in kwargs

    async def test_a_file_with_an_unfamiliar_extension_still_opens_and_is_read_by_content(self) -> None:
        page, presenter, _ = make_page()
        presenter._fs.files["/w/weird.dat"] = "[db]\nport = 1\n"
        picked = mock.MagicMock(path="/w/weird.dat")
        page._picker.pick_files = mock.AsyncMock(return_value=[picked])
        await page._on_add_file(mock.MagicMock())
        assert badge(page, "original") == (True, "toml")


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class MultiFileUiTests:
    """複数ファイル UI（U3）：チップで開き・切り替え・閉じる。

    「まとめて評価 (eval-all)」のトグルは撤去した（形式が異なる組み合わせで変換に失敗する
    ことがあり、ユースケースを精査してからにする。presenter 側のロジックは残っているので
    ``test_gui_presenter.py`` の ``EvalAllTests`` で検査する）。
    """

    async def test_the_files_row_is_hidden_with_a_single_document(self) -> None:
        page, presenter, _ = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        assert page._files_row.visible is False

    async def test_adding_a_second_file_shows_the_chips(self) -> None:
        page, presenter, _ = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._picker.pick_files = mock.AsyncMock(
            return_value=[mock.MagicMock(path="/w/app.toml")])
        await page._on_add_file(mock.MagicMock())
        assert page._files_row.visible is True
        assert [c.label for c in page._files_row.controls] == ["shop.xml", "app.toml"]
        assert page._files_row.controls[1].selected            # 追加した方が選ばれている
        assert not page._files_row.controls[0].selected

    async def test_selecting_a_chip_switches_the_active_document(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        await presenter.add_path("/w/app.toml")
        page._refresh_multi_file_ui()
        await page._on_select_document(0)
        assert state.document.name == "shop.xml"
        assert page._files_row.controls[0].selected
        assert not page._files_row.controls[1].selected

    async def test_closing_a_chip_removes_just_that_document(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        await presenter.add_path("/w/app.toml")
        page._refresh_multi_file_ui()
        await page._on_close_document_at(0)
        assert [d.name for d in state.documents] == ["app.toml"]
        assert page._files_row.visible is False                 # 1 件に戻ったので隠れる

    async def test_closing_the_last_chip_returns_to_the_unloaded_screen(self) -> None:
        from yaqpy.gui import texts

        page, presenter, _ = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        await page._on_close_document_at(0)
        assert page._drop_hint.visible is True
        assert page._file_label.value == texts.MSG_NO_DOCUMENT


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class StartupFileTests:
    """``yaqpy --gui a.yaml`` で渡された 1 ファイルを、起動直後に開く（U2）。"""

    async def test_opens_and_runs_the_given_file(self) -> None:
        page, presenter, state = make_page()
        await page.open_startup_file("/w/shop.xml")
        assert state.document.is_loaded
        assert badge(page, "original") == (True, "xml")
        assert page._run_button.disabled is False

    async def test_a_missing_file_shows_an_error_instead_of_crashing(self) -> None:
        page, presenter, state = make_page()
        await page.open_startup_file("/w/does-not-exist.yaml")
        assert not state.document.is_loaded
        assert page._status_icon.color == ft.Colors.ERROR


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class UnifiedAddFileButtonTests:
    """「ファイルを開く」と「＋ファイルを追加」を 1 つのボタンに統一した（要望）。"""

    async def test_is_enabled_from_the_start(self) -> None:
        page, _presenter, _state = make_page()
        assert page._add_file_button.disabled is False

    async def test_with_nothing_open_the_first_pick_opens_it(self) -> None:
        page, _presenter, state = make_page()
        page._picker.pick_files = mock.AsyncMock(
            return_value=[mock.MagicMock(path="/w/shop.xml")])
        await page._on_add_file(mock.MagicMock())
        assert [d.name for d in state.documents] == ["shop.xml"]
        assert badge(page, "original") == (True, "xml")

    async def test_with_something_open_it_adds_instead_of_replacing(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._picker.pick_files = mock.AsyncMock(
            return_value=[mock.MagicMock(path="/w/app.toml")])
        await page._on_add_file(mock.MagicMock())
        assert [d.name for d in state.documents] == ["shop.xml", "app.toml"]

    async def test_selecting_several_files_with_nothing_open_opens_the_first_and_adds_the_rest(
        self) -> None:
        page, _presenter, state = make_page()
        page._picker.pick_files = mock.AsyncMock(return_value=[
            mock.MagicMock(path="/w/shop.xml"), mock.MagicMock(path="/w/app.toml")])
        await page._on_add_file(mock.MagicMock())
        assert [d.name for d in state.documents] == ["shop.xml", "app.toml"]


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class EditableOriginalTests:
    """読み込み後も原文欄を編集できる（追加編集。要望）。"""

    async def test_loaded_original_is_not_read_only(self) -> None:
        page, presenter, _state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        assert page._original.read_only is False

    async def test_editing_shows_the_edited_label_and_reruns(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        assert page._edited_label.visible is False
        page._original.value = "<shop><item>pencil</item></shop>\n"
        await page._apply_edit()
        assert page._edited_label.visible is True
        assert state.document.edited
        assert "pencil" in page._converted.value

    async def test_reapplying_the_same_text_is_a_no_op(self) -> None:
        page, presenter, _state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._original.value = presenter.state.document.original_text
        await page._apply_edit()
        assert page._edited_label.visible is False

    async def test_a_fresh_document_hides_the_edited_label(self) -> None:
        page, presenter, _state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._original.value = "<shop><item>pencil</item></shop>\n"
        await page._apply_edit()
        await presenter.open_path("/w/app.toml")
        page._after_open()
        assert page._edited_label.visible is False

    async def test_switching_tabs_keeps_each_documents_edited_flag(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        await presenter.add_path("/w/app.toml")
        page._refresh_multi_file_ui()
        page._original.value = "[db]\nport = 2\n"
        await page._apply_edit()
        assert page._edited_label.visible is True
        await page._on_select_document(0)              # shop.xml（編集していない）
        assert page._edited_label.visible is False
        await page._on_select_document(1)              # app.toml（編集した）
        assert page._edited_label.visible is True


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class IndentStepperTests:
    """インデントを ± ボタンでも操作できる（要望）。"""

    async def test_plus_increments_the_field_and_state(self) -> None:
        page, _presenter, state = make_page()
        page._on_indent_plus(mock.MagicMock())
        assert state.query.indent == 3
        assert page._indent_field.value == "3"

    async def test_minus_decrements_the_field_and_state(self) -> None:
        page, _presenter, state = make_page()
        page._on_indent_minus(mock.MagicMock())
        assert state.query.indent == 1
        assert page._indent_field.value == "1"

    async def test_minus_does_not_go_below_zero(self) -> None:
        page, _presenter, state = make_page()
        for _ in range(5):
            page._on_indent_minus(mock.MagicMock())
        assert state.query.indent == 0
        assert page._indent_field.value == "0"


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class GuidePromptDialogTests:
    """CLI の --guide-prompt を GUI からも呼べる（要望）。

    実際のクリップボード操作（``ft.Clipboard().set``）は、生きた page が無いと
    ``RuntimeError`` になる（他の ``_on_copy`` も同様に未検査）。ここではダイアログの
    中身が正しく組み立てられることだけを確かめる。
    """

    async def test_opens_a_dialog_with_the_guide_prompt_prefilled(self) -> None:
        from yaqpy.app.selfdoc import render_guide_prompt

        page, presenter, _state = make_page()
        await page._on_open_guide_prompt(mock.MagicMock())
        dialog = page._page.show_dialog.call_args.args[0]
        assert isinstance(dialog, ft.AlertDialog)
        assert dialog.title.value == "AI への相談文"
        field = dialog.content.controls[-1]
        assert field.value == render_guide_prompt(presenter._service)

    async def test_works_without_a_document_open(self) -> None:
        page, _presenter, _state = make_page()
        await page._on_open_guide_prompt(mock.MagicMock())
        page._page.show_dialog.assert_called_once()


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class CopyFailureTests:
    """コピーの失敗で画面を止めない（W0：ブラウザが clipboard-write を拒むと例外になる）。"""

    async def _page_with_result(self):
        page, presenter, _state = make_page()
        await presenter.open_path("/w/app.toml")
        await presenter.run()
        return page

    async def test_a_refused_clipboard_shows_a_hint_instead_of_raising(self) -> None:
        from yaqpy.gui import texts

        page = await self._page_with_result()
        with mock.patch.object(ft.Clipboard, "set", mock.AsyncMock(
                side_effect=RuntimeError("PlatformException(copy_fail, ...)"))):
            await page._on_copy(mock.MagicMock())
        snack = page._page.show_dialog.call_args.args[0]
        assert snack.content.value == texts.MSG_COPY_FAILED

    async def test_a_successful_copy_says_so(self) -> None:
        from yaqpy.gui import texts

        page = await self._page_with_result()
        with mock.patch.object(ft.Clipboard, "set", mock.AsyncMock(return_value=None)) as set_:
            await page._on_copy(mock.MagicMock())
        set_.assert_awaited_once()
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_COPIED


def make_web_page(uploaded: list | None = None):
    """Web 版のセッションの画面（v0.6.0）。本番と同じ組み立てで、アップロードだけ偽物にする。"""
    from yaqpy.gui._di import make_presenter as make_real_presenter
    from yaqpy.gui.pages.main_page import MainPage
    from yaqpy.gui.state import WebLimits

    state = GuiState(web=WebLimits(max_input_bytes=1024 * 1024, timeout_seconds=5.0))
    presenter = make_real_presenter(state)
    uploader = mock.MagicMock()
    uploader.pick = mock.AsyncMock(return_value=uploaded or [])
    picker = mock.MagicMock()
    picker.save_file = mock.AsyncMock(return_value=None)
    page = MainPage(page=mock.MagicMock(), presenter=presenter, state=state, picker=picker,
                    on_open_settings=lambda capability: None, uploader=uploader)
    return page, presenter, state


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class WebMainPageTests:
    """Web 版：開くのはアップロード、保存はダウンロード（W1）。"""

    async def test_the_save_button_is_a_download_button(self) -> None:
        from yaqpy.gui import texts

        page, _, _ = make_web_page()
        assert page._save_button.content == texts.BTN_DOWNLOAD

    async def test_uploaded_files_open_the_first_and_add_the_rest(self) -> None:
        from yaqpy.gui._upload import Uploaded

        page, _, state = make_web_page([Uploaded("shop.xml", b"<shop><item>pen</item></shop>\n"),
                                        Uploaded("app.toml", b"[db]\nport = 1\n")])
        await page._on_add_file(mock.MagicMock())
        assert [d.name for d in state.documents] == ["shop.xml", "app.toml"]
        assert all(d.path is None for d in state.documents)      # サーバー側のパスは持たない
        page._picker.pick_files.assert_not_called()                # パスを返すダイアログは使わない
        assert page._files_row.visible

    async def test_a_refused_file_is_reported_and_the_others_still_open(self) -> None:
        from yaqpy.gui._upload import Uploaded

        page, _, state = make_web_page([Uploaded("big.yaml", error="ファイルが大きすぎます"),
                                        Uploaded("app.toml", b"[db]\nport = 1\n")])
        await page._on_add_file(mock.MagicMock())
        assert [d.name for d in state.documents] == ["app.toml"]
        assert "大きすぎます" in page._status_text.value

    async def test_the_size_check_uses_the_server_cap(self) -> None:
        page, _, _ = make_web_page()
        await page._on_add_file(mock.MagicMock())
        check_size = page._uploader.pick.call_args.kwargs["check_size"]
        assert check_size(1024 * 1024) == ""
        assert check_size(1024 * 1024 + 1) != ""

    async def test_save_downloads_the_full_result(self) -> None:
        from yaqpy.gui._upload import Uploaded

        page, presenter, state = make_web_page([Uploaded("app.toml", b"[db]\nport = 1\n")])
        await page._on_add_file(mock.MagicMock())
        state.query.output_format = "json"
        await presenter.run()
        await page._on_save(mock.MagicMock())
        kwargs = page._picker.save_file.call_args.kwargs
        assert kwargs["file_name"] == "app.json"
        assert kwargs["src_bytes"] == presenter.last_run.full_text.encode("utf-8")

    async def test_no_settings_link_for_a_security_error(self) -> None:
        page, presenter, state = make_web_page()
        presenter.open_text("a: 1\n")
        page._after_open()
        state.query.expression = 'env("PATH")'
        await page._run()
        assert not page._settings_link.visible                     # 許可する手段が無い
        assert "Web" in page._status_text.value


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class WebSettingsPageTests:
    """Web 版の設定画面：危険な許可のスイッチと言語の切り替えを出さない（計画書 5-5 節の 2）。"""

    def _controls(self, web: bool):
        from yaqpy.gui.pages.settings_page import SettingsPage
        from yaqpy.gui.state import WebLimits

        state = GuiState(web=WebLimits(max_input_bytes=10 * 1024 * 1024, timeout_seconds=10.0)
                         if web else None)
        settings = SettingsPage(page=mock.MagicMock(), state=state, on_changed=lambda: None)
        return settings, settings.control.controls

    def test_desktop_still_has_the_switches(self) -> None:
        settings, controls = self._controls(web=False)
        assert settings._boxes["env"] in controls
        assert settings._language in controls

    def test_web_hides_the_security_switches_and_the_language(self) -> None:
        from yaqpy.gui import texts

        settings, controls = self._controls(web=True)
        assert settings._boxes["env"] not in controls
        assert settings._boxes["file"] not in controls
        assert settings._language not in controls
        values = [getattr(c, "value", None) for c in controls]
        assert texts.SET_WEB_SECURITY_NOTE in values
        assert texts.SET_WEB_LANGUAGE_NOTE in values
        assert any(isinstance(v, str) and "10 MiB" in v for v in values)
