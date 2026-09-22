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
    """開くダイアログは拡張子で絞らない：開いたあと中身で形式を判定する（yaqpy 独自）。"""

    async def test_the_file_picker_is_not_restricted_to_known_extensions(self) -> None:
        page, _, _ = make_page()
        page._picker.pick_files = mock.AsyncMock(return_value=[])
        await page._on_open(mock.MagicMock())
        _, kwargs = page._picker.pick_files.call_args
        assert "allowed_extensions" not in kwargs

    async def test_a_file_with_an_unfamiliar_extension_still_opens_and_is_read_by_content(self) -> None:
        page, presenter, _ = make_page()
        presenter._fs.files["/w/weird.dat"] = "[db]\nport = 1\n"
        picked = mock.MagicMock(path="/w/weird.dat")
        page._picker.pick_files = mock.AsyncMock(return_value=[picked])
        await page._on_open(mock.MagicMock())
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
