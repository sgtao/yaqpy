"""ログ画面と、ログからの再実行（v0.7.0）。実際のログのファイルの上で確かめる。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from tests.unit.test_gui_log_presenter import FS, make_presenter as make_log_presenter, write_log
from yaqpy.app.ports import StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui import run_log, texts
from yaqpy.gui.log_presenter import RerunPayload
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

JSON_TEXT = '{"items": [{"name": "pen", "price": 120}, {"name": "ink", "price": 80}]}\n'


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "logs"
    write_log(root, "shop.json", JSON_TEXT, "json", ".items[0].name",
              when=datetime(2026, 9, 23, 14, 5, 12))
    write_log(root, "stock.csv", "name,qty\nink,3\n", "csv", ".", out_fmt="json",
              when=datetime(2026, 9, 22, 9, 30, 0))
    return root


def make_page(root: Path):
    from yaqpy.gui.pages.log_page import LogPage

    presenter = make_log_presenter(root, launcher=mock.MagicMock())
    picker = mock.MagicMock()
    picker.save_file = mock.AsyncMock(return_value=None)
    on_rerun = mock.AsyncMock()
    page = LogPage(page=mock.MagicMock(), presenter=presenter, picker=picker, on_rerun=on_rerun)
    return page, presenter, picker, on_rerun


def tile_titles(page) -> list[str]:
    return [t.title.value for t in page._list.controls]


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class ListAndDetailTests:
    async def test_showing_the_tab_lists_the_logs_newest_first(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        assert tile_titles(page) == ["2026-09-23 14:05:12", "2026-09-22 09:30:00"]
        assert page._status.value == texts.MSG_LOG_STATUS.format(total=2, shown=2, path=str(root))
        assert not page._empty_note.visible

    async def test_no_logs_says_so(self, tmp_path: Path) -> None:
        page, *_ = make_page(tmp_path / "none")
        await page.on_show()
        assert page._list.controls == [] and page._empty_note.visible
        assert page._empty_note.value == texts.MSG_LOG_EMPTY

    async def test_selecting_a_log_shows_its_summary_and_full_text(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        assert page._input_line.value == "shop.json（json → yaml）"
        assert page._expr_line.value == ".items[0].name"
        assert page._full.value.startswith("# ----- summary -----")
        assert not page._rerun_button.disabled and not page._save_button.disabled
        assert not page._delete_button.disabled
        assert page._list.controls[0].selected and not page._list.controls[1].selected

    async def test_nothing_is_selected_at_first(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        assert page._rerun_button.disabled and page._save_button.disabled
        assert page._delete_button.disabled and page._full.value == texts.MSG_LOG_SELECT

    async def test_a_broken_log_shows_the_text_and_disables_the_rerun(self, root: Path) -> None:
        page, presenter, *_ = make_page(root)
        await page.on_show()
        path = Path(page._rows[0].file.path)
        path.write_bytes(b"garbage: [unclosed\n")
        await page._select(str(path))
        assert page._full.value.startswith("garbage")
        assert page._notice.visible and page._rerun_button.disabled and page._save_button.disabled
        assert not page._delete_button.disabled

    async def test_the_filter_narrows_the_list_and_reads_the_heads(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        page._search.value = "stock.csv"
        await page._apply_filter()
        assert tile_titles(page) == ["2026-09-22 09:30:00"]
        assert page._status.value == texts.MSG_LOG_STATUS.format(total=2, shown=1, path=str(root))
        page._search.value = "zzz"
        await page._apply_filter()
        assert page._list.controls == [] and page._empty_note.value == texts.MSG_LOG_NO_MATCH

    async def test_a_selection_that_the_filter_hides_is_cleared(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        page._search.value = "csv"
        await page._apply_filter()
        assert page._selected == "" and page._full.value == texts.MSG_LOG_SELECT

    async def test_refresh_picks_up_new_logs(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        write_log(root, "new.json", '{"a": 1}\n', "json", ".a", when=datetime(2026, 9, 24, 1, 2, 3))
        await page._on_refresh(mock.MagicMock())
        assert len(page._list.controls) == 3 and page._list.controls[0].title.value.startswith(
            "2026-09-24")

    async def test_the_folder_button_opens_the_folder(self, root: Path) -> None:
        page, presenter, *_ = make_page(root)
        page._on_open_folder(mock.MagicMock())
        presenter._launcher.assert_called_once_with(str(root))

    async def test_a_folder_that_cannot_open_shows_a_message(self, root: Path) -> None:
        page, presenter, *_ = make_page(root)
        presenter._launcher.side_effect = OSError("no file manager")
        page._on_open_folder(mock.MagicMock())
        snack = page._page.show_dialog.call_args.args[0]
        assert "no file manager" in snack.content.value


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class ActionTests:
    async def test_rerun_sends_the_payload_without_replacing(self, root: Path) -> None:
        page, _, _, on_rerun = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        await page._on_rerun_click(mock.MagicMock())
        (payload, replace), _ = on_rerun.call_args
        assert isinstance(payload, RerunPayload) and replace is False
        assert payload.expression == ".items[0].name" and payload.input_format == "json"

    async def test_an_eval_all_log_asks_before_replacing(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        inputs = (run_log.LogInput("a.json", '{"a": 1}\n'), run_log.LogInput("b.json", '{"b": 2}\n'))
        write_log(root, "a.json", '{"a": 1}\n', "json", ".", eval_all=True, inputs=inputs,
                  output_text="{}\n", when=datetime(2026, 1, 2, 3, 4, 5))
        page, _, _, on_rerun = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        await page._on_rerun_click(mock.MagicMock())
        on_rerun.assert_not_called()                             # 確認してから
        dialog = page._page.show_dialog.call_args.args[0]
        assert dialog.title.value == texts.DLG_LOG_REPLACE_TITLE
        cancel, ok = dialog.actions
        assert cancel.autofocus                                  # 既定は「やめる」
        await ok.on_click(mock.MagicMock())
        (payload, replace), _ = on_rerun.call_args
        assert replace is True and payload.eval_all

    async def test_a_log_that_cannot_be_rerun_has_the_button_disabled(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        write_log(root, "big.json", '{"k": "' + "x" * 300 + '"}\n', "json", ".k",
                  when=datetime(2026, 1, 2, 3, 4, 5), max_bytes=100)
        page, *_ = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        assert page._rerun_button.disabled and not page._save_button.disabled

    async def test_save_expression_writes_the_yaqpy_file(self, root: Path, tmp_path: Path) -> None:
        page, _, picker, _ = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        picker.save_file = mock.AsyncMock(return_value=str(tmp_path / "sel"))
        await page._on_save_expression(mock.MagicMock())
        kwargs = picker.save_file.call_args.kwargs
        assert kwargs["file_name"] == "shop.yaqpy" and kwargs["allowed_extensions"] == ["yaqpy"]
        assert (tmp_path / "sel.yaqpy").read_bytes() == b".items[0].name\n"
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_EXPR_SAVED.format(
            path=str(tmp_path / "sel.yaqpy"))

    async def test_a_cancelled_save_writes_nothing(self, root: Path, tmp_path: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        await page._select(page._rows[0].file.path)
        await page._on_save_expression(mock.MagicMock())
        assert not list(tmp_path.glob("*.yaqpy"))

    async def test_delete_asks_first_then_removes_one_log(self, root: Path) -> None:
        page, presenter, *_ = make_page(root)
        await page.on_show()
        target = page._rows[0].file.path
        await page._select(target)
        page._on_delete_click(mock.MagicMock())
        dialog = page._page.show_dialog.call_args.args[0]
        assert dialog.title.value == texts.DLG_LOG_DELETE_TITLE
        assert Path(target).exists()                             # 確認前は消えない
        await dialog.actions[1].on_click(mock.MagicMock())
        assert not Path(target).exists()
        assert len(page._list.controls) == 1 and page._selected == ""
        assert page._delete_button.disabled

    async def test_cancelling_the_delete_keeps_the_log(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        target = page._rows[0].file.path
        await page._select(target)
        page._on_delete_click(mock.MagicMock())
        page._page.show_dialog.call_args.args[0].actions[0].on_click(mock.MagicMock())
        assert Path(target).exists()

    async def test_delete_all_asks_with_the_count_and_removes_only_logs(self, root: Path) -> None:
        page, *_ = make_page(root)
        await page.on_show()
        mine = root / "2026" / "mine.txt"
        mine.write_text("keep", encoding="utf-8")
        page._on_delete_all_click(mock.MagicMock())
        dialog = page._page.show_dialog.call_args.args[0]
        assert dialog.content.value == texts.DLG_LOG_DELETE_ALL_BODY.format(n=2)
        await dialog.actions[1].on_click(mock.MagicMock())
        assert page._list.controls == [] and mine.exists()
        assert page._empty_note.value == texts.MSG_LOG_EMPTY

    async def test_delete_all_with_no_logs_does_nothing(self, tmp_path: Path) -> None:
        page, *_ = make_page(tmp_path / "none")
        await page.on_show()
        page._page.show_dialog.reset_mock()
        page._on_delete_all_click(mock.MagicMock())
        page._page.show_dialog.assert_not_called()


def make_main(tmp_path: Path):
    from yaqpy.gui.pages.main_page import MainPage

    state = GuiState()
    fs = FS
    presenter = MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=state)
    page = MainPage(page=mock.MagicMock(), presenter=presenter, state=state, picker=mock.MagicMock())
    presenter.record_run = mock.AsyncMock()
    return page, presenter, state


def payload(**over) -> RerunPayload:
    fields = dict(expression=".items[0].name", inputs=(("shop.json", JSON_TEXT),),
                  input_format="json", output_format="yaml", indent=4, eval_all=False)
    fields.update(over)
    return RerunPayload(**fields)


class PresenterRerunTests:
    def test_the_input_is_added_and_the_query_restored(self) -> None:
        presenter = MainPresenter(service=YqService(FS, StaticEnvironment({})), fs=FS,
                                  state=GuiState())
        assert presenter.apply_rerun(payload()) is None
        s = presenter.state
        assert [d.name for d in s.documents] == ["shop.json"] and s.documents[0].path is None
        assert s.documents[0].original_text == JSON_TEXT
        assert (s.query.expression, s.query.input_format, s.query.output_format, s.query.indent) == (
            ".items[0].name", "json", "yaml", 4)
        assert s.eval_all is False

    def test_open_documents_are_kept_and_the_new_one_becomes_active(self) -> None:
        presenter = MainPresenter(service=YqService(FS, StaticEnvironment({})), fs=FS,
                                  state=GuiState())
        presenter.open_text("a: 1\n", name="old.yaml")
        presenter.apply_rerun(payload())
        s = presenter.state
        assert [d.name for d in s.documents] == ["old.yaml", "shop.json"] and s.active_index == 1

    def test_replace_closes_everything_first(self) -> None:
        presenter = MainPresenter(service=YqService(FS, StaticEnvironment({})), fs=FS,
                                  state=GuiState())
        presenter.open_text("a: 1\n", name="old.yaml")
        presenter.apply_rerun(payload(inputs=(("a.json", '{"a": 1}\n'), ("b.json", '{"b": 2}\n')),
                                      eval_all=True), replace=True)
        s = presenter.state
        assert [d.name for d in s.documents] == ["a.json", "b.json"] and s.eval_all is True

    def test_eval_all_is_dropped_when_the_documents_are_added_to_others_by_a_single_input(self) -> None:
        presenter = MainPresenter(service=YqService(FS, StaticEnvironment({})), fs=FS,
                                  state=GuiState())
        presenter.apply_rerun(payload(eval_all=True))            # 1 件だけなら eval_all にならない
        assert presenter.state.eval_all is False

    def test_too_large_an_input_changes_nothing(self) -> None:
        state = GuiState()
        state.settings.max_input_mib = 1
        presenter = MainPresenter(service=YqService(FS, StaticEnvironment({})), fs=FS, state=state)
        presenter.open_text("a: 1\n", name="old.yaml")
        state.query.expression = ".keep"
        big = "x" * (1024 * 1024 + 1)
        error = presenter.apply_rerun(payload(inputs=(("big.json", big),)), replace=True)
        assert error is not None and error.code == "intake"
        assert [d.name for d in state.documents] == ["old.yaml"] and state.query.expression == ".keep"


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class MainPageRerunTests:
    async def test_the_page_shows_the_restored_state_and_runs(self, tmp_path: Path) -> None:
        page, presenter, state = make_main(tmp_path)
        await page.apply_rerun(payload())
        assert page._input_dd.value == "json" and page._output_dd.value == "yaml"
        assert page._indent_field.value == "4" and page._expr_field.value == ".items[0].name"
        assert page._file_label.value.startswith("shop.json")
        assert page._original.value == JSON_TEXT
        assert page._converted.value.strip() == "pen"            # すぐ実行して結果が出る
        assert not page._run_button.disabled and not page._close_button.disabled

    async def test_it_does_not_record_the_run(self, tmp_path: Path) -> None:
        """決定 S：ログから開いた入力は整形が変わり重複除外に掛からないので、再実行は記録しない。"""
        page, presenter, _ = make_main(tmp_path)
        page._page.run_task = mock.MagicMock()
        await page.apply_rerun(payload())
        presenter.record_run.assert_not_called()
        assert not [c for c in page._page.run_task.call_args_list if c.args[0] == page._record]

    async def test_a_second_rerun_adds_another_document_and_keeps_the_first(self, tmp_path: Path) -> None:
        page, presenter, state = make_main(tmp_path)
        await page.apply_rerun(payload())
        await page.apply_rerun(payload(inputs=(("stock.csv", "name,qty\nink,3\n"),),
                                       input_format="csv", output_format="json",
                                       expression=".[0].name"))
        assert [d.name for d in state.documents] == ["shop.json", "stock.csv"]
        assert page._input_dd.value == "csv" and page._converted.value.strip() == '"ink"'
        assert [type(c) for c in page._files_row.controls] == [ft.Chip, ft.Chip]

    async def test_replace_brings_back_the_logged_inputs_only(self, tmp_path: Path) -> None:
        page, presenter, state = make_main(tmp_path)
        presenter.open_text("x: 1\n", name="other.yaml")
        await page.apply_rerun(payload(inputs=(("a.json", '{"a": 1}\n'), ("b.json", '{"b": 2}\n')),
                                       eval_all=True, expression="."), replace=True)
        assert [d.name for d in state.documents] == ["a.json", "b.json"]

    async def test_a_failure_shows_the_reason_and_keeps_the_screen(self, tmp_path: Path) -> None:
        page, presenter, state = make_main(tmp_path)
        state.settings.max_input_mib = 1
        await page.apply_rerun(payload(inputs=(("big.json", "x" * (1024 * 1024 + 1)),)))
        assert not state.documents and page._status_text.value

    async def test_a_restored_expression_that_is_not_valid_is_marked(self, tmp_path: Path) -> None:
        page, *_ = make_main(tmp_path)
        await page.apply_rerun(payload(expression=".a["))
        assert page._expr_field.error


class WiringTests:
    def test_the_log_tab_is_the_fourth_page_and_only_on_the_desktop(self) -> None:
        from yaqpy.gui import _run

        assert (_run.MAIN, _run.SETTINGS, _run.ASK_AI, _run.LOG) == (0, 1, 2, 3)
        assert texts.NAV_LOG

    def test_the_web_version_has_no_log_page_code_path(self) -> None:
        import inspect

        from yaqpy.gui import _run

        source = inspect.getsource(_run._main)
        assert "if web is None:" in source and "LogPage(" in source
        assert source.index("LogPage(") > source.index("if web is None:", source.index("pages: list"))
