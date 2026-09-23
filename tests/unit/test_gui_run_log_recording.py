"""実行ログの記録の組み込み（Presenter と画面。v0.7.0）。実際のファイルの上で確かめる。"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from yaqpy.app.local import LocalFileSystem
from yaqpy.app.ports import StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui import run_log
from yaqpy.gui.presenter import MainPresenter, RecordViewModel
from yaqpy.gui.state import GuiState, WebLimits


def make_presenter(tmp_path: Path, **settings) -> MainPresenter:
    state = GuiState()
    state.settings.log_dir = str(tmp_path / "logs")
    for key, value in settings.items():
        setattr(state.settings, key, value)
    fs = LocalFileSystem()
    return MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=state)


def data_file(tmp_path: Path, name: str = "data.json", text: str = '{"a": 1, "b": [1, 2]}\n') -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


async def run_and_record(p: MainPresenter, expression: str = ".a") -> tuple[RecordViewModel, object]:
    p.state.query.expression = expression
    vm = await p.run()
    assert vm.ok, vm.error
    source = p.last_source
    assert source is not None
    return await p.record_run(source, vm), vm


class RecordRunTests:
    async def test_a_successful_run_writes_one_readable_log(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        result, _ = await run_and_record(p, ".b | .[0]")
        assert result.recorded and not result.skipped and not result.error
        files = run_log.list_log_files(tmp_path / "logs")
        assert len(files) == 1 and files[0].path == result.path
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.ok and parsed.rerunnable and parsed.expression == ".b | .[0]"
        assert (files[0].input_format, files[0].output_format) == ("json", "yaml")   # 既定の出力は YAML
        assert parsed.summary["input"]["selected"] == "auto"
        assert parsed.summary["output"]["selected"] == "yaml"
        assert parsed.summary["input"]["files"][0]["name"] == "data.json"

    async def test_the_same_content_is_not_recorded_twice(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        first, _ = await run_and_record(p)
        again, _ = await run_and_record(p)
        assert first.recorded and again.skipped == "duplicate"
        assert len(run_log.list_log_files(tmp_path / "logs")) == 1

    @pytest.mark.parametrize("change", ["expression", "output_format", "indent", "input_format"])
    async def test_a_changed_setting_is_a_new_record(self, tmp_path: Path, change: str) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        await run_and_record(p)
        if change == "expression":
            p.state.query.expression = ".b"
        elif change == "output_format":
            p.state.query.output_format = "toml"
        elif change == "indent":
            p.state.query.indent = 4
        else:
            p.state.query.input_format = "json"
        vm = await p.run()
        assert vm.ok, vm.error
        result = await p.record_run(p.last_source, vm)
        assert result.recorded

    async def test_a_changed_input_is_a_new_record(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        await run_and_record(p)
        p.edit_active_document('{"a": 2}\n')
        result, _ = await run_and_record(p)
        assert result.recorded
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.summary["input"]["files"][0]["edited"] is True

    async def test_a_changed_permission_is_a_new_record(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        await run_and_record(p)
        p.state.settings.allow_env = True
        result, _ = await run_and_record(p)
        assert result.recorded
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.summary["security"]["allow_env"] is True

    async def test_a_failed_write_is_reported_and_is_retried_next_time(self, tmp_path: Path) -> None:
        blocked = tmp_path / "blocked"
        blocked.write_text("a file, not a folder", encoding="utf-8")
        p = make_presenter(tmp_path, log_dir=str(blocked))
        await p.open_path(data_file(tmp_path))
        result, _ = await run_and_record(p)
        assert not result.recorded and result.error
        p.state.settings.log_dir = str(tmp_path / "logs")
        again, _ = await run_and_record(p)                       # キーを更新していないので記録される
        assert again.recorded

    async def test_the_log_of_a_failed_run_is_never_written(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        p.state.query.expression = ".a["
        vm = await p.run()
        assert not vm.ok and p.last_source is None
        result = await p.record_run(mock.MagicMock(), vm)
        assert result.skipped == "failed_run"
        assert run_log.list_log_files(tmp_path / "logs") == []

    async def test_nothing_is_recorded_when_the_setting_is_off(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path, log_enabled=False)
        await p.open_path(data_file(tmp_path))
        result, _ = await run_and_record(p)
        assert result.skipped == "disabled"
        assert run_log.list_log_files(tmp_path / "logs") == []

    async def test_the_web_version_never_records(self, tmp_path: Path) -> None:
        state = GuiState(web=WebLimits(max_input_bytes=1024 * 1024, timeout_seconds=5.0))
        state.settings.log_dir = str(tmp_path / "logs")
        from yaqpy.gui._di import make_presenter as make_real

        p = make_real(state)
        p.open_text('{"a": 1}\n')
        p.state.query.expression = ".a"
        vm = await p.run()
        assert vm.ok
        result = await p.record_run(p.last_source, vm)
        assert result.skipped == "web" and not (tmp_path / "logs").exists()

    async def test_the_oldest_logs_are_removed_beyond_the_limit(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path, log_max_files=2)
        await p.open_path(data_file(tmp_path))
        for expression in (".a", ".b", ".b[0]"):
            await run_and_record(p, expression)
        assert len(run_log.list_log_files(tmp_path / "logs")) == 2

    async def test_a_large_input_is_recorded_without_its_body(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path, log_max_entry_mib=1)
        big = '{"k": "' + "x" * (1024 * 1024 + 10) + '"}\n'
        await p.open_path(data_file(tmp_path, "big.json", big))
        result, _ = await run_and_record(p, ".k | length")
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.inputs[0].omitted and not parsed.rerunnable

    async def test_eval_all_records_every_open_document(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path, "a.json", '{"a": 1}\n'))
        await p.add_path(data_file(tmp_path, "b.json", '{"b": 2}\n'))
        p.state.eval_all = True
        result, _ = await run_and_record(p, ".")
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert [i.name for i in parsed.inputs] == ["a.json", "b.json"]
        assert parsed.summary["eval_all"] is True

    async def test_a_pasted_document_is_recorded_without_a_path(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        p.open_text("a: 1\n")
        result, _ = await run_and_record(p, ".a")
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.summary["input"]["files"][0]["path"] is None

    def test_the_default_folder_is_used_when_the_setting_is_empty(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path, log_dir="")
        assert p.log_dir() == run_log.default_log_dir()


class LastSourceTests:
    async def test_the_source_belongs_to_the_run_that_made_it(self, tmp_path: Path) -> None:
        """記録は後から別タスクで走る。その間に式や文書が変わっても、押した回の内容のまま。"""
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        p.state.query.expression = ".a"
        vm = await p.run()
        source = p.last_source
        p.state.query.expression = ".b"                        # 実行の後で式が変わる
        p.edit_active_document('{"a": 99}\n')
        result = await p.record_run(source, vm)
        parsed = run_log.parse_log_text(Path(result.path).read_text(encoding="utf-8"))
        assert parsed.expression == ".a"
        assert '"a": 1' in run_log.restore_input_text(parsed.inputs[0]).replace("\n", " ")

    async def test_a_new_run_clears_the_previous_source(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path)
        await p.open_path(data_file(tmp_path))
        await run_and_record(p)
        p.state.query.expression = ".a["
        await p.run()
        assert p.last_source is None


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class PageRecordingTests:
    """「実行」ボタンで始まった成功だけが記録の対象になる（決定 H）。"""

    def make(self, tmp_path: Path):
        from yaqpy.gui.pages.main_page import MainPage

        presenter = make_presenter(tmp_path)
        page = MainPage(page=mock.MagicMock(), presenter=presenter, state=presenter.state,
                        picker=mock.MagicMock())
        presenter.record_run = mock.AsyncMock(return_value=RecordViewModel(recorded=True))
        return page, presenter

    def recorded(self, page) -> list:
        return [c for c in page._page.run_task.call_args_list if c.args[0] == page._record]

    async def test_the_run_button_records_once(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await presenter.open_path(data_file(tmp_path))
        await page._on_run(mock.MagicMock())
        calls = self.recorded(page)
        assert len(calls) == 1
        assert calls[0].args[1] is presenter.last_source or calls[0].args[1].request

    async def test_automatic_reruns_do_not_record(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await presenter.open_path(data_file(tmp_path))
        await page._run()                                      # 形式・インデントの変更などの再実行
        await page.rerun()                                     # 設定の変更
        assert self.recorded(page) == []

    async def test_a_format_change_after_the_button_does_not_record_again(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await presenter.open_path(data_file(tmp_path))
        await page._on_run(mock.MagicMock())
        page._state.query.output_format = "json"
        await page._run()
        assert len(self.recorded(page)) == 1

    async def test_a_failed_run_is_not_recorded(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await presenter.open_path(data_file(tmp_path))
        page._state.query.expression = ".a["
        await page._on_run(mock.MagicMock())
        assert self.recorded(page) == []

    async def test_a_request_made_while_running_is_kept_for_the_next_pass(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await presenter.open_path(data_file(tmp_path))
        presenter.state.running = True                          # 実行中に Enter が押された
        await page._on_run(mock.MagicMock())
        assert page._rerun_requested and page._record_requested
        assert self.recorded(page) == []
        presenter.state.running = False
        await page._run()                                       # 走っていた実行が終わって、もう 1 回
        assert len(self.recorded(page)) == 1

    async def test_pressing_run_with_no_document_leaves_no_stale_request(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        await page._on_run(mock.MagicMock())
        assert not page._record_requested
        await presenter.open_path(data_file(tmp_path))
        await page._run()
        assert self.recorded(page) == []

    async def test_a_write_failure_shows_a_message_and_keeps_the_result(self, tmp_path: Path) -> None:
        from yaqpy.gui import texts

        page, presenter = self.make(tmp_path)
        presenter.record_run = mock.AsyncMock(return_value=RecordViewModel(error="disk full"))
        await presenter.open_path(data_file(tmp_path))
        await page._on_run(mock.MagicMock())
        await page._record(presenter.last_source, presenter.last_run)
        snack = page._page.show_dialog.call_args.args[0]
        assert snack.content.value == texts.MSG_LOG_WRITE_FAILED.format(reason="disk full")
        assert page._converted.value                            # 結果は画面に出たまま

    async def test_a_skipped_record_shows_nothing(self, tmp_path: Path) -> None:
        page, presenter = self.make(tmp_path)
        presenter.record_run = mock.AsyncMock(return_value=RecordViewModel(skipped="duplicate"))
        await presenter.open_path(data_file(tmp_path))
        await page._on_run(mock.MagicMock())
        await page._record(presenter.last_source, presenter.last_run)
        page._page.show_dialog.assert_not_called()
