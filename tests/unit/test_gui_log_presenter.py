"""ログ画面の業務ロジック（gui/log_presenter.py。v0.7.0）。Flet 非依存。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import yaqpy
from yaqpy.app.local import LocalFileSystem
from yaqpy.gui import run_log, texts
from yaqpy.gui.log_presenter import LogPresenter
from yaqpy.options import Options

FS = LocalFileSystem()


def write_log(root: Path, name: str, text: str, fmt: str, expression: str, *, out_fmt: str = "yaml",
              when: datetime, eval_all: bool = False, inputs: tuple | None = None,
              output_text: str | None = None, max_bytes: int = 10**7) -> Path:
    options = Options(input_format=fmt, output_format=out_fmt, indent=2)
    output = output_text if output_text is not None else yaqpy.evaluate(expression, text,
                                                                        options=options)
    entry = run_log.LogEntry(
        timestamp=when, expression=expression,
        inputs=inputs or (run_log.LogInput(name=name, text=text, path="D:\\w\\" + name),),
        input_format=fmt, input_selected="auto", output_format=out_fmt, output_selected=out_fmt,
        output_text=output, indent=2, eval_all=eval_all, document_count=1, elapsed_ms=1.0,
        allow_env=False, allow_file=False, options=Options(indent=2))
    built = run_log.build_log(entry, max_entry_bytes=max_bytes)
    return Path(run_log.write_log(root, entry, built, FS.write_file))


def make_presenter(root: Path, launcher=None, max_lines: int = 5000) -> LogPresenter:
    return LogPresenter(fs=FS, log_dir=lambda: str(root), options=lambda: Options(indent=2),
                        max_display_lines=lambda: max_lines, launcher=launcher)


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    root = tmp_path / "logs"
    write_log(root, "shop.json", '{"items": [{"name": "pen", "price": 120}]}\n', "json",
              ".items[0].name", when=datetime(2026, 9, 23, 14, 5, 12))
    write_log(root, "stock.csv", "name,qty\nink,3\n", "csv", ".", out_fmt="json",
              when=datetime(2026, 9, 22, 9, 30, 0))
    write_log(root, "cfg.toml", '[db]\nport = 5432\n', "toml", ".db.port",
              when=datetime(2026, 9, 21, 18, 12, 3))
    return root


class ListTests:
    def test_the_rows_are_built_from_file_names_newest_first(self, logs: Path) -> None:
        rows = make_presenter(logs).refresh()
        assert [r.title for r in rows] == ["2026-09-23 14:05:12", "2026-09-22 09:30:00",
                                           "2026-09-21 18:12:03"]
        assert rows[0].subtitle.startswith("json → yaml  (") and rows[0].subtitle.endswith(")")
        assert rows[1].subtitle.startswith("csv → json")

    def test_a_missing_folder_gives_an_empty_list(self, tmp_path: Path) -> None:
        p = make_presenter(tmp_path / "none")
        assert p.refresh() == [] and p.total == 0

    def test_the_list_does_not_open_the_files(self, logs: Path, monkeypatch) -> None:
        import builtins

        opened: list[str] = []
        real_open = builtins.open

        def spy(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", spy)
        make_presenter(logs).refresh()
        assert not [p for p in opened if p.endswith(".yaml")]

    @pytest.mark.parametrize("size, text", [(5, "5 B"), (2048, "2.0 KB"), (3 * 1024 * 1024, "3.0 MB")])
    def test_sizes_are_human_readable(self, size: int, text: str) -> None:
        from yaqpy.gui.log_presenter import _human

        assert _human(size) == text


class FilterTests:
    def test_an_empty_query_shows_everything(self, logs: Path) -> None:
        p = make_presenter(logs)
        p.refresh()
        assert len(p.filter("")) == 3 and len(p.filter("   ")) == 3

    @pytest.mark.parametrize("query, expected", [
        ("csv", ["2026-09-22 09:30:00"]),
        ("JSON", ["2026-09-23 14:05:12", "2026-09-22 09:30:00"]),      # 入力形式か出力形式（大文字小文字は無視）
        ("json-to-yaml", ["2026-09-23 14:05:12"]),
        ("2026-09-21", ["2026-09-21 18:12:03"]),
        ("09-2", ["2026-09-23 14:05:12", "2026-09-22 09:30:00", "2026-09-21 18:12:03"]),
        ("toml yaml", ["2026-09-21 18:12:03"]),                        # 語のすべてに一致（AND）
        ("nothing-like-this", []),
    ])
    def test_by_what_the_file_name_says(self, logs: Path, query: str, expected: list[str]) -> None:
        p = make_presenter(logs)
        p.refresh()
        assert [r.title for r in p.filter(query)] == expected

    async def test_the_expression_and_input_names_need_the_head_to_be_read(self, logs: Path) -> None:
        p = make_presenter(logs)
        p.refresh()
        assert p.filter("items[0]") == []                       # まだ先頭を読んでいない
        assert len(p.pending_heads()) == 3
        assert await p.load_heads() == 3
        assert [r.title for r in p.filter("items[0]")] == ["2026-09-23 14:05:12"]
        assert [r.title for r in p.filter("stock.csv")] == ["2026-09-22 09:30:00"]
        assert [r.title for r in p.filter(".db.port")] == ["2026-09-21 18:12:03"]
        assert p.pending_heads() == []

    async def test_heads_are_cached_and_a_changed_file_is_read_again(self, logs: Path) -> None:
        p = make_presenter(logs)
        p.refresh()
        await p.load_heads()
        assert await p.load_heads() == 0
        target = Path(p.refresh()[0].file.path)
        target.write_text(target.read_text(encoding="utf-8").replace(".items[0].name", ".other"),
                          encoding="utf-8")
        import os

        os.utime(target, ns=(1, 1))                             # 更新日時を変える
        p.refresh()
        assert [f.path for f in p.pending_heads()] == [str(target)]
        await p.load_heads()
        assert [r.title for r in p.filter(".other")] == ["2026-09-23 14:05:12"]


class DetailTests:
    async def test_a_log_is_read_and_summarized(self, logs: Path) -> None:
        p = make_presenter(logs)
        detail = await p.read_detail(p.refresh()[0].file.path)
        assert not detail.error and detail.parsed.ok
        assert detail.expression == ".items[0].name"
        assert detail.input_summary == "shop.json（json → yaml）"
        assert detail.can_rerun and detail.can_save_expression
        assert detail.text.startswith("# ----- summary -----") and detail.truncated_lines == 0

    async def test_a_long_log_is_shortened_for_display_only(self, logs: Path) -> None:
        p = make_presenter(logs, max_lines=5)
        detail = await p.read_detail(p.refresh()[0].file.path)
        assert detail.display_text.count("\n") <= 5 and detail.truncated_lines > 0
        assert detail.text.count("\n") > 5                       # 全文は保存・再実行のために残る

    async def test_a_hand_broken_log_is_shown_but_cannot_be_rerun(self, logs: Path) -> None:
        p = make_presenter(logs)
        path = Path(p.refresh()[0].file.path)
        path.write_text("garbage: [unclosed\n", encoding="utf-8")
        detail = await p.read_detail(str(path))
        assert detail.error and detail.text.replace("\r\n", "\n") == "garbage: [unclosed\n"
        assert not detail.can_rerun and not detail.can_save_expression

    async def test_a_missing_file_reports_an_error(self, tmp_path: Path) -> None:
        detail = await make_presenter(tmp_path).read_detail(str(tmp_path / "gone.yaml"))
        assert detail.error and detail.parsed is None

    async def test_an_unknown_version_can_be_saved_but_not_rerun(self, logs: Path) -> None:
        p = make_presenter(logs)
        path = Path(p.refresh()[0].file.path)
        path.write_text(path.read_text(encoding="utf-8").replace("yaqpy_log: 1", "yaqpy_log: 9"),
                        encoding="utf-8")
        detail = await p.read_detail(str(path))
        assert not detail.can_rerun and detail.can_save_expression


class RerunTests:
    async def test_the_payload_restores_expression_formats_and_input(self, logs: Path) -> None:
        p = make_presenter(logs)
        detail = await p.read_detail(p.refresh()[0].file.path)
        payload = await p.build_rerun(detail)
        assert not isinstance(payload, str)
        assert payload.expression == ".items[0].name"
        assert payload.input_format == "json"                    # 実際に使った形式（auto に戻さない）
        assert payload.output_format == "yaml" and payload.indent == 2
        assert not payload.eval_all and not payload.needs_replace_confirmation
        (name, text), = payload.inputs
        assert name == "shop.json"
        import json

        assert json.loads(text) == {"items": [{"name": "pen", "price": 120}]}   # 元の形式に戻っている

    async def test_a_csv_input_comes_back_as_csv(self, logs: Path) -> None:
        p = make_presenter(logs)
        rows = p.refresh()
        detail = await p.read_detail(rows[1].file.path)
        payload = await p.build_rerun(detail)
        assert payload.input_format == "csv" and payload.output_format == "json"
        assert payload.inputs[0][1].splitlines() == ["name,qty", "ink,3"]

    async def test_the_restored_input_gives_the_same_result_again(self, logs: Path) -> None:
        originals = {
            "shop.json": ('{"items": [{"name": "pen", "price": 120}]}\n', "json"),
            "stock.csv": ("name,qty\nink,3\n", "csv"),
            "cfg.toml": ('[db]\nport = 5432\n', "toml"),
        }
        p = make_presenter(logs)
        for row in p.refresh():
            detail = await p.read_detail(row.file.path)
            payload = await p.build_rerun(detail)
            name, restored = payload.inputs[0]
            text, fmt = originals[name]

            def run(source: str) -> str:
                return yaqpy.evaluate(payload.expression, source, options=Options(
                    input_format=payload.input_format, output_format=payload.output_format,
                    indent=payload.indent))

            assert run(restored) == run(text)              # 戻した入力で、元の入力と同じ結果になる

    async def test_eval_all_logs_ask_for_a_replace(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        inputs = (run_log.LogInput("a.json", '{"a": 1}\n', "D:\\a.json"),
                  run_log.LogInput("b.json", '{"b": 2}\n', "D:\\b.json"))
        path = write_log(root, "a.json", '{"a": 1}\n', "json", ".", eval_all=True, inputs=inputs,
                         output_text="{}\n", when=datetime(2026, 1, 2, 3, 4, 5))
        p = make_presenter(root)
        payload = await p.build_rerun(await p.read_detail(str(path)))
        assert payload.eval_all and payload.needs_replace_confirmation
        assert [n for n, _ in payload.inputs] == ["a.json", "b.json"]

    async def test_a_log_with_an_omitted_input_cannot_be_rerun(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        path = write_log(root, "big.json", '{"k": "' + "x" * 300 + '"}\n', "json", ".k",
                         when=datetime(2026, 1, 2, 3, 4, 5), max_bytes=100)
        p = make_presenter(root)
        detail = await p.read_detail(str(path))
        assert not detail.can_rerun and detail.can_save_expression
        assert await p.build_rerun(detail) == texts.MSG_LOG_CANNOT_RERUN

    async def test_a_log_with_text_kept_reruns_from_the_original_text(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        path = write_log(root, "d.json", '{"a": 1, "a": 2}\n', "json", ".a", output_text="2\n",
                         when=datetime(2026, 1, 2, 3, 4, 5))
        p = make_presenter(root)
        payload = await p.build_rerun(await p.read_detail(str(path)))
        assert payload.inputs[0][1] == '{"a": 1, "a": 2}\n'


class DeleteTests:
    def test_delete_one_and_all(self, logs: Path) -> None:
        p = make_presenter(logs)
        rows = p.refresh()
        assert p.delete(rows[0].file.path)
        assert len(p.refresh()) == 2
        assert p.delete_all() == 2 and p.refresh() == []

    def test_delete_all_keeps_files_that_are_not_logs(self, logs: Path) -> None:
        mine = logs / "2026" / "mine.txt"
        mine.write_text("keep", encoding="utf-8")
        make_presenter(logs).delete_all()
        assert mine.exists()


class SaveExpressionTests:
    async def test_the_default_name_follows_the_input_name(self, logs: Path) -> None:
        p = make_presenter(logs)
        detail = await p.read_detail(p.refresh()[0].file.path)
        assert p.default_expression_name(detail) == "shop.yaqpy"

    async def test_a_pasted_input_gives_expression_yaqpy(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        path = write_log(root, texts.MSG_PASTED, "a: 1\n", "yaml", ".a",
                         when=datetime(2026, 1, 2, 3, 4, 5))
        p = make_presenter(root)
        assert p.default_expression_name(await p.read_detail(str(path))) == "expression.yaqpy"

    async def test_the_expression_is_saved_as_a_yaqpy_file(self, logs: Path, tmp_path: Path) -> None:
        p = make_presenter(logs)
        detail = await p.read_detail(p.refresh()[0].file.path)
        saved = await p.save_expression(detail, str(tmp_path / "out"))
        assert saved == str(tmp_path / "out.yaqpy")
        assert Path(saved).read_bytes() == b".items[0].name\n"

    async def test_a_multiline_expression_round_trips_through_the_file(self, tmp_path: Path) -> None:
        root = tmp_path / "logs"
        expression = ".items[]\n| select(.enabled)\n| .name"
        path = write_log(root, "a.json", '{"items": []}\n', "json", expression,
                         output_text="[]\n", when=datetime(2026, 1, 2, 3, 4, 5))
        p = make_presenter(root)
        detail = await p.read_detail(str(path))
        saved = await p.save_expression(detail, str(tmp_path / "e.yaqpy"))
        from yaqpy.gui import expression_file

        assert expression_file.decode_expression(Path(saved).read_bytes()) == expression


class OpenFolderTests:
    def test_the_folder_is_created_and_opened(self, tmp_path: Path) -> None:
        opened: list[str] = []
        root = tmp_path / "new" / "logs"
        p = make_presenter(root, launcher=opened.append)
        assert p.open_folder() == str(root)
        assert root.is_dir() and opened == [str(root)]
