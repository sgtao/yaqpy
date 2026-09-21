"""メイン画面の見た目の約束：ファイル名の文字、プロパティ行と式の行の間隔、形式の札。
Flet の部品を組み立てるだけで、窓は開かない（flet が無い環境では飛ばす）。"""

from __future__ import annotations

import unittest
from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

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


@unittest.skipIf(ft is None, "flet is not installed")
class LayoutTests(unittest.TestCase):
    def test_file_name_uses_the_button_font_size_and_bold(self) -> None:
        from yaqpy.gui.pages.main_page import BUTTON_TEXT_SIZE

        page, _, _ = make_page()
        self.assertEqual(BUTTON_TEXT_SIZE, 14)                 # Flet の Button の文字と同じ大きさ
        self.assertEqual(page._file_label.size, BUTTON_TEXT_SIZE)
        self.assertEqual(page._file_label.weight, ft.FontWeight.BOLD)

    def test_the_property_row_and_the_expression_row_are_apart(self) -> None:
        from yaqpy.gui.pages.main_page import FILTER_ROW_SPACING

        page, _, _ = make_page()
        filter_bar = next(c for c in page.control.controls
                          if isinstance(c, ft.Column) and any(
                              isinstance(r, ft.Row) and page._property_dd in r.controls
                              for r in c.controls))
        self.assertGreaterEqual(FILTER_ROW_SPACING, 12)        # 以前は 2
        self.assertEqual(filter_bar.spacing, FILTER_ROW_SPACING)


@unittest.skipIf(ft is None, "flet is not installed")
class FormatBadgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_before_a_document_is_opened(self) -> None:
        page, _, _ = make_page()
        self.assertEqual(badge(page, "original"), (False, ""))
        self.assertEqual(badge(page, "converted"), (False, ""))

    async def test_shows_the_resolved_format_when_the_dropdowns_are_auto(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        self.assertEqual(state.query.input_format, "auto")
        self.assertEqual(badge(page, "original"), (True, "xml"))
        self.assertEqual(badge(page, "converted"), (True, "xml"))

    async def test_follows_a_specified_format(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        state.query.output_format = "toon"
        page._apply(await presenter.run())
        self.assertEqual(badge(page, "original"), (True, "xml"))
        self.assertEqual(badge(page, "converted"), (True, "toon"))
        state.query.input_format = "yaml"
        state.query.output_format = "auto"
        page._apply(RunViewModel())
        self.assertEqual(badge(page, "original"), (True, "yaml"))
        self.assertEqual(badge(page, "converted"), (True, "yaml"))

    async def test_stays_after_a_failed_run(self) -> None:
        page, presenter, state = make_page()
        await presenter.open_path("/w/app.toml")
        page._after_open()
        state.query.expression = ".db.("
        vm = await presenter.run()
        self.assertFalse(vm.ok)
        page._apply(vm)
        self.assertEqual(badge(page, "original"), (True, "toml"))
        self.assertEqual(badge(page, "converted"), (True, "toml"))

    async def test_hidden_again_when_the_document_is_closed(self) -> None:
        page, presenter, _ = make_page()
        await presenter.open_path("/w/shop.xml")
        page._after_open()
        page._on_close(mock.MagicMock())
        self.assertEqual(badge(page, "original"), (False, ""))
        self.assertEqual(badge(page, "converted"), (False, ""))

    async def test_pasted_text_is_yaml(self) -> None:
        page, presenter, _ = make_page()
        presenter.open_text("a: 1\n")
        page._after_open()
        self.assertEqual(badge(page, "original"), (True, "yaml"))


if __name__ == "__main__":
    unittest.main()
