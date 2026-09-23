"""実行ログの記録・読み戻し・保存先の整理（gui/run_log.py。v0.7.0）。Flet 非依存。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

import yaqpy
from yaqpy import api
from yaqpy.core.model.convert import to_python
from yaqpy.gui import run_log
from yaqpy.gui.run_log import LogEntry, LogInput
from yaqpy.options import Options

NOW = datetime(2026, 9, 23, 14, 5, 12)

SAMPLES = {
    "json": ('sample.json', '{"a": 1, "s": "x # y --- z", "b": [1, 2.50, null, true]}\n'),
    "yaml": ('sample.yaml', "a: 1\n# a comment\nb: [1, 2]\n---\nc: 3\n"),
    "xml": ('sample.xml', '<shop name="s"><item id="1">pen</item><item id="2">ink</item></shop>\n'),
    "csv": ('sample.csv', "name,price\npen,120\nink,80\n"),
    "tsv": ('sample.tsv', "name\tprice\npen\t120\n"),
    "toml": ('sample.toml', '[db]\nport = 5432\nname = "x"\n'),
    "props": ('sample.properties', "db.port = 5432\ndb.name = x\n"),
}


def make_entry(name: str, text: str, fmt: str, expression: str = ".", *,
               out_fmt: str | None = None, output_text: str | None = None,
               **overrides) -> LogEntry:
    out_fmt = out_fmt or fmt
    options = Options(input_format=fmt, output_format=out_fmt, indent=2)
    if output_text is None:
        output_text = yaqpy.evaluate(expression, text, options=options)
    fields = dict(
        timestamp=NOW, expression=expression,
        inputs=(LogInput(name=name, text=text, path="D:\\work\\" + name),),
        input_format=fmt, input_selected="auto", output_format=out_fmt,
        output_selected=out_fmt, output_text=output_text, indent=2, eval_all=False,
        document_count=1, elapsed_ms=1.83, allow_env=False, allow_file=False,
        options=Options(indent=2))
    fields.update(overrides)
    return LogEntry(**fields)


def python_of(text: str, fmt: str) -> list:
    return [to_python(d) for d in api.load(text, format=fmt)]


class BuildAndParseTests:
    @pytest.mark.parametrize("fmt", sorted(SAMPLES))
    def test_every_format_round_trips_and_can_be_rerun(self, fmt: str) -> None:
        name, text = SAMPLES[fmt]
        built = run_log.build_log(make_entry(name, text, fmt))
        parsed = run_log.parse_log_text(built.text)
        assert parsed.ok, parsed.error
        assert built.rerunnable and parsed.rerunnable
        assert (built.input_format, built.output_format) == (fmt, fmt)
        restored = run_log.restore_input_text(parsed.inputs[0])
        assert python_of(restored, fmt) == python_of(text, fmt)          # データの中身は同じ
        assert parsed.inputs[0].format == fmt and parsed.inputs[0].name == name

    def test_toon_round_trips_too(self) -> None:
        text = yaqpy.evaluate(".", '{"items": [{"a": 1}, {"a": 2}]}',
                              options=Options(input_format="json", output_format="toon"))
        built = run_log.build_log(make_entry("s.toon", text, "toon"))
        parsed = run_log.parse_log_text(built.text)
        assert parsed.rerunnable
        assert python_of(run_log.restore_input_text(parsed.inputs[0]), "toon") == python_of(
            text, "toon")

    def test_the_log_has_four_yaml_documents_with_the_documented_headers(self) -> None:
        built = run_log.build_log(make_entry(*SAMPLES["json"][:2], "json",
                                             ".a"))
        docs = built.text.split("\n---\n")
        assert len(docs) == 4
        assert docs[0].startswith("# ----- summary -----\nyaqpy_log: 1\n")
        assert docs[1].startswith("# ----- expression -----\n# expression\nexpression: ")
        assert docs[2].startswith("# ----- original (input) -----\nfiles:\n")
        assert docs[3].startswith("# ----- result (output) -----\nformat: json\n")

    def test_the_log_is_readable_by_yaqpy_itself_as_documented(self) -> None:
        """6-3 節：``select(document_index == 1) | .expression`` で式が取り出せる。"""
        built = run_log.build_log(make_entry("a.json", '{"a": 1}\n', "json", ".a"))
        out = yaqpy.evaluate("select(document_index == 1) | .expression", built.text,
                             options=Options(output_format="json", indent=0))
        assert json.loads(out) == ".a"

    def test_the_summary_records_the_run(self) -> None:
        name, text = SAMPLES["json"]
        built = run_log.build_log(make_entry(name, text, "json", ".a", allow_env=True,
                                             elapsed_ms=1.83))
        summary = run_log.parse_log_text(built.text).summary
        assert summary["yaqpy_log"] == run_log.LOG_VERSION
        assert summary["yaqpy_version"] == yaqpy.__version__
        assert summary["timestamp"].startswith("2026-09-23T14:05:12")
        assert summary["input"] == {
            "format": "json", "selected": "auto",
            "files": [{"name": name, "path": "D:\\work\\" + name, "bytes": len(text.encode()),
                       "edited": False}]}
        assert summary["output"]["format"] == "json" and summary["output"]["indent"] == 2
        assert summary["security"] == {"allow_env": True, "allow_file": False}
        assert summary["eval_all"] is False and summary["document_count"] == 1
        assert summary["elapsed_ms"] == 1.8 and summary["rerunnable"] is True

    def test_a_pasted_text_has_a_null_path(self) -> None:
        entry = make_entry("(pasted)", "a: 1\n", "yaml")
        entry = LogEntry(**{**{f: getattr(entry, f) for f in entry.__slots__},
                            "inputs": (LogInput(name="(pasted)", text="a: 1\n", path=None),)})
        summary = run_log.parse_log_text(run_log.build_log(entry).text).summary
        assert summary["input"]["files"][0]["path"] is None

    def test_an_edited_input_is_marked(self) -> None:
        entry = make_entry("a.yaml", "a: 1\n", "yaml")
        entry = LogEntry(**{**{f: getattr(entry, f) for f in entry.__slots__},
                            "inputs": (LogInput(name="a.yaml", text="a: 1\n", edited=True),)})
        summary = run_log.parse_log_text(run_log.build_log(entry).text).summary
        assert summary["input"]["files"][0]["edited"] is True


class ExpressionTests:
    @pytest.mark.parametrize("expression", [
        ".a",
        ".items[]\n| select(.enabled)",
        '.a | "x # not a comment" # a real one\n| .b',
        '.a = "quote \\" and \\\\ backslash"',
        ".a | \"日本語\\n二行目\"",
        "  .a  \n",
        "# only a comment\n.a",
        "line1\r\nline2",
    ])
    def test_the_expression_is_restored_exactly(self, expression: str) -> None:
        entry = make_entry("a.json", '{"a": 1}\n', "json", expression, output_text="1\n")
        built = run_log.build_log(entry)
        parsed = run_log.parse_log_text(built.text)
        assert parsed.ok and parsed.expression == expression
        assert built.rerunnable

    def test_the_expression_is_written_on_one_line(self) -> None:
        entry = make_entry("a.json", '{"a": 1}\n', "json", ".a\n| . + 1", output_text="2\n")
        line = next(ln for ln in run_log.build_log(entry).text.split("\n")
                    if ln.startswith("expression:"))
        assert line == 'expression: ".a\\n| . + 1"'

    @pytest.mark.parametrize("expression", ["", ".", " . ", "\n"])
    def test_no_expression_is_recorded_as_not_used(self, expression: str) -> None:
        entry = make_entry("a.json", '{"a": 1}\n', "json", expression, output_text="{}\n")
        built = run_log.build_log(entry)
        assert "# expression (not used)\nexpression: \".\"" in built.text
        assert run_log.parse_log_text(built.text).expression == "."


class RepresentationTests:
    def test_strings_that_used_to_break_the_yaml_emitter_now_round_trip(self) -> None:
        """v0.3.0 からの不具合（v0.7.0 で修正）：先頭が改行・空白だけの行を含む文字列。"""
        data = {"lead": "\nx", "blank": "a\n \nb", "tab": "a\n\t\nb", "sep": "a\n---\nb",
                "seq": ["\ny", " z\n"]}
        text = json.dumps(data)
        built = run_log.build_log(make_entry("d.json", text, "json"))
        parsed = run_log.parse_log_text(built.text)
        assert parsed.rerunnable and "representation" not in parsed.summary
        assert python_of(run_log.restore_input_text(parsed.inputs[0]), "json") == [data]

    def test_multiple_scalar_results_are_kept_as_text(self) -> None:
        """``.items[].name`` の出力 ``a``＋改行＋``b`` は、YAML として読み直すと別の値になる（6-4 節）。"""
        text = '{"items": [{"name": "a"}, {"name": "b"}]}\n'
        entry = make_entry("s.json", text, "json", ".items[].name", out_fmt="yaml")
        built = run_log.build_log(entry)
        parsed = run_log.parse_log_text(built.text)
        assert parsed.result is not None
        assert parsed.result.docs is None and parsed.result.text == "a\nb\n"
        assert parsed.summary["representation"] == {"output": "text"}
        assert parsed.rerunnable                       # 入力は戻せる

    def test_a_structured_result_is_kept_as_documents(self) -> None:
        text = '{"items": [{"name": "a"}, {"name": "b"}]}\n'
        entry = make_entry("s.json", text, "json", "[.items[]]", out_fmt="yaml")
        parsed = run_log.parse_log_text(run_log.build_log(entry).text)
        assert parsed.result is not None and parsed.result.text is None
        assert [to_python(d) for d in parsed.result.docs] == [[{"name": "a"}, {"name": "b"}]]

    def test_a_result_with_repeated_keys_is_kept_as_text(self) -> None:
        """``.items[]`` を YAML で出すと ``name: a`` と ``name: b`` が続く（同じキーが 2 度）。
        データとして読めない形は、原文で記録する。"""
        text = '{"items": [{"name": "a"}, {"name": "b"}]}\n'
        entry = make_entry("s.json", text, "json", ".items[]", out_fmt="yaml")
        parsed = run_log.parse_log_text(run_log.build_log(entry).text)
        assert parsed.result.docs is None and parsed.result.text == "name: a\nname: b\n"
        assert parsed.summary["representation"] == {"output": "text"}

    def test_an_input_with_repeated_keys_is_kept_as_text_and_rerunnable(self) -> None:
        text = '{"a": 1, "a": 2}\n'
        parsed = run_log.parse_log_text(
            run_log.build_log(make_entry("d.json", text, "json", ".a", output_text="2\n")).text)
        assert parsed.inputs[0].docs is None and parsed.inputs[0].text == text
        assert parsed.summary["representation"] == {"input_0": "text"} and parsed.rerunnable

    def test_an_input_that_cannot_be_restored_falls_back_to_its_original_text(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        real = run_log._verify
        calls: list[int] = []

        def fake(*args, **kwargs):
            calls.append(1)
            problems = real(*args, **kwargs)
            if len(calls) == 1:
                problems.inputs.append(0)               # 1 回目の検査で「戻らない」と判定させる
            return problems

        monkeypatch.setattr(run_log, "_verify", fake)
        name, text = SAMPLES["json"]
        built = run_log.build_log(make_entry(name, text, "json"))
        parsed = run_log.parse_log_text(built.text)
        assert parsed.inputs[0].docs is None and parsed.inputs[0].text == text
        assert parsed.summary["representation"] == {"input_0": "text"}
        assert parsed.rerunnable
        assert run_log.restore_input_text(parsed.inputs[0]) == text

    def test_an_unreadable_expression_disables_the_rerun(self, monkeypatch: pytest.MonkeyPatch
                                                         ) -> None:
        real = run_log._verify

        def fake(*args, **kwargs):
            problems = real(*args, **kwargs)
            problems.expression = True
            return problems

        monkeypatch.setattr(run_log, "_verify", fake)
        built = run_log.build_log(make_entry("a.json", '{"a": 1}\n', "json"))
        assert not built.rerunnable
        assert run_log.parse_log_text(built.text).summary["rerunnable"] is False


class MultipleInputTests:
    def test_eval_all_records_every_input_with_its_own_format(self) -> None:
        a_text, b_text = '{"a": 1}\n', "b: 2\n"
        entry = make_entry("a.json", a_text, "json", ".", output_text="{}\n", eval_all=True,
                           document_count=2,
                           inputs=(LogInput("a.json", a_text, "D:\\a.json"),
                                   LogInput("b.yaml", b_text, "D:\\b.yaml")))
        parsed = run_log.parse_log_text(run_log.build_log(entry).text)
        assert [i.name for i in parsed.inputs] == ["a.json", "b.yaml"]
        assert [i.format for i in parsed.inputs] == ["json", "yaml"]
        assert parsed.summary["eval_all"] is True and parsed.rerunnable
        texts = [run_log.restore_input_text(i) for i in parsed.inputs]
        assert python_of(texts[0], "json") == [{"a": 1}]
        assert python_of(texts[1], "yaml") == [{"b": 2}]

    def test_a_multi_document_yaml_input_keeps_every_document(self) -> None:
        text = "a: 1\n---\nb: 2\n---\n- 3\n"
        parsed = run_log.parse_log_text(run_log.build_log(make_entry("m.yaml", text, "yaml")).text)
        assert len(parsed.inputs[0].docs) == 3
        assert python_of(run_log.restore_input_text(parsed.inputs[0]), "yaml") == [
            {"a": 1}, {"b": 2}, [3]]

    def test_an_explicit_input_format_is_used_for_every_input(self) -> None:
        entry = make_entry("data", "a: 1\n", "yaml", input_selected="yaml")
        parsed = run_log.parse_log_text(run_log.build_log(entry).text)
        assert parsed.inputs[0].format == "yaml" and parsed.summary["input"]["selected"] == "yaml"


class LimitTests:
    def test_over_limit_inputs_are_omitted_and_cannot_be_rerun(self) -> None:
        text = json.dumps({"k": "x" * 200}) + "\n"
        built = run_log.build_log(make_entry("big.json", text, "json", ".k"), max_entry_bytes=100)
        assert built.inputs_omitted and not built.rerunnable
        parsed = run_log.parse_log_text(built.text)
        assert parsed.inputs[0].omitted and parsed.inputs[0].docs is None
        assert not parsed.rerunnable
        assert "x" * 50 not in built.text.split("\n---\n")[2]          # 本文は書かない

    def test_the_limit_is_inclusive(self) -> None:
        text = '{"a": 1}\n'
        size = len(text.encode())
        assert not run_log.build_log(make_entry("a.json", text, "json"),
                                     max_entry_bytes=size).inputs_omitted
        assert run_log.build_log(make_entry("a.json", text, "json"),
                                 max_entry_bytes=size - 1).inputs_omitted

    def test_an_over_limit_output_is_omitted_but_the_run_can_still_be_rerun(self) -> None:
        text = json.dumps({"k": "y" * 300}) + "\n"
        entry = make_entry("s.json", "{}\n", "json", ".", output_text=text)
        built = run_log.build_log(entry, max_entry_bytes=200)
        parsed = run_log.parse_log_text(built.text)
        assert built.output_omitted and parsed.result.omitted and parsed.result.docs is None
        assert parsed.rerunnable
        assert "y" * 50 not in built.text

    def test_the_default_limit_is_one_mib(self) -> None:
        assert run_log.DEFAULT_MAX_ENTRY_MIB == 1 and run_log.DEFAULT_MAX_FILES == 500


class ParseTests:
    def test_broken_text_is_reported_not_raised(self) -> None:
        parsed = run_log.parse_log_text("a: [unclosed\n")
        assert not parsed.ok and parsed.error and not parsed.rerunnable

    def test_a_yaml_file_that_is_not_a_log_is_reported(self) -> None:
        assert not run_log.parse_log_text("a: 1\n").ok

    def test_an_unknown_version_can_be_shown_but_not_rerun(self) -> None:
        built = run_log.build_log(make_entry("a.json", '{"a": 1}\n', "json"))
        future = built.text.replace("yaqpy_log: 1", "yaqpy_log: 99", 1)
        parsed = run_log.parse_log_text(future)
        assert parsed.ok and not parsed.known_version and not parsed.rerunnable

    def test_a_hand_edited_summary_that_says_not_rerunnable_is_respected(self) -> None:
        built = run_log.build_log(make_entry("a.json", '{"a": 1}\n', "json"))
        parsed = run_log.parse_log_text(built.text.replace("rerunnable: true",
                                                           "rerunnable: false", 1))
        assert parsed.ok and not parsed.rerunnable

    def test_restoring_an_unrecorded_input_fails(self) -> None:
        with pytest.raises(ValueError):
            run_log.restore_input_text(run_log.ParsedInput(name="x", omitted=True))


class DedupeKeyTests:
    def test_the_same_content_gives_the_same_key(self) -> None:
        a = make_entry("a.json", '{"a": 1}\n', "json", ".a")
        b = make_entry("a.json", '{"a": 1}\n', "json", ".a", elapsed_ms=99.0,
                       timestamp=datetime(2030, 1, 1))
        assert run_log.dedupe_key(a) == run_log.dedupe_key(b)

    @pytest.mark.parametrize("change", [
        {"expression": ".b"},
        {"input_selected": "json"},
        {"output_selected": "toon"},
        {"indent": 4},
        {"eval_all": True},
        {"allow_env": True},
        {"allow_file": True},
        {"inputs": (LogInput("other.json", '{"a": 1}\n'),)},
        {"inputs": (LogInput("a.json", '{"a": 2}\n'),)},
    ])
    def test_a_different_run_gives_a_different_key(self, change: dict) -> None:
        base = make_entry("a.json", '{"a": 1}\n', "json", ".a")
        other = LogEntry(**{**{f: getattr(base, f) for f in base.__slots__}, **change})
        assert run_log.dedupe_key(base) != run_log.dedupe_key(other)


class FileNameTests:
    def test_the_name_has_the_documented_shape(self) -> None:
        assert (run_log.log_file_name(NOW, "json", "yaml")
                == "0923-140512_json-to-yaml_convert-log.yaml")

    def test_a_second_file_in_the_same_second_gets_a_sequence(self) -> None:
        assert (run_log.log_file_name(NOW, "json", "yaml", 2)
                == "0923-140512-2_json-to-yaml_convert-log.yaml")

    @pytest.mark.parametrize("name, expected", [
        ("0923-140512_json-to-yaml_convert-log.yaml", ("0923", "140512", 1, "json", "yaml")),
        ("0923-140512-3_csv-to-props_convert-log.yaml", ("0923", "140512", 3, "csv", "props")),
    ])
    def test_parse(self, name: str, expected: tuple) -> None:
        assert run_log.parse_log_file_name(name) == expected

    @pytest.mark.parametrize("name", [
        "notes.yaml", "0923-140512_json-to-yaml.yaml", "0923-14051_json-to-yaml_convert-log.yaml",
        "0923-140512_JSON-to-yaml_convert-log.yaml", "x0923-140512_a-to-b_convert-log.yaml",
        "0923-140512_a-to-b_convert-log.yaml.bak",
    ])
    def test_other_files_are_not_logs(self, name: str) -> None:
        assert run_log.parse_log_file_name(name) is None

    def test_every_format_name_makes_a_parsable_file_name(self) -> None:
        from yaqpy.formats.registry import builtin_formats

        for name in builtin_formats().output_formats():
            parsed = run_log.parse_log_file_name(run_log.log_file_name(NOW, name, name))
            assert parsed is not None and parsed[3] == parsed[4] == name


class DefaultDirTests:
    def test_windows_uses_local_app_data(self) -> None:
        path = run_log.default_log_dir("win32", {"LOCALAPPDATA": "C:\\Users\\u\\AppData\\Local"})
        assert path == os.path.join("C:\\Users\\u\\AppData\\Local", "yaqpy", "logs")

    def test_windows_without_the_variable_falls_back_to_the_home(self) -> None:
        path = run_log.default_log_dir("win32", {"USERPROFILE": "C:\\Users\\u"})
        assert path == os.path.join("C:\\Users\\u", "AppData", "Local", "yaqpy", "logs")

    def test_macos_uses_library_logs(self) -> None:
        assert run_log.default_log_dir("darwin", {"HOME": "/Users/u"}) == os.path.join(
            "/Users/u", "Library", "Logs", "yaqpy")

    def test_linux_uses_xdg_state_home(self) -> None:
        assert run_log.default_log_dir("linux", {"XDG_STATE_HOME": "/s", "HOME": "/h"}
                                       ) == os.path.join("/s", "yaqpy", "logs")

    def test_linux_without_xdg_uses_local_state(self) -> None:
        assert run_log.default_log_dir("linux", {"HOME": "/h"}) == os.path.join(
            "/h", ".local", "state", "yaqpy", "logs")


def write_logs(root: Path, count: int, *, year: int = 2026, start_day: int = 1) -> list[Path]:
    paths = []
    for i in range(count):
        ts = datetime(year, 1, start_day + i // 24, i % 24, 0, 0)
        entry = make_entry("a.json", '{"a": 1}\n', "json", ".a", timestamp=ts)
        built = run_log.build_log(entry)
        from yaqpy.app.local import LocalFileSystem

        paths.append(Path(run_log.write_log(root, entry, built, LocalFileSystem().write_file)))
    return paths


class StorageTests:
    def test_write_creates_the_year_folder_and_the_documented_name(self, tmp_path: Path) -> None:
        entry = make_entry("a.json", '{"a": 1}\n', "json", ".a")
        built = run_log.build_log(entry)
        from yaqpy.app.local import LocalFileSystem

        path = Path(run_log.write_log(tmp_path, entry, built, LocalFileSystem().write_file))
        assert path == tmp_path / "2026" / "0923-140512_json-to-json_convert-log.yaml"
        assert path.read_text(encoding="utf-8") == built.text
        assert run_log.parse_log_text(path.read_text(encoding="utf-8")).rerunnable

    def test_a_second_write_in_the_same_second_does_not_overwrite(self, tmp_path: Path) -> None:
        first = write_logs(tmp_path, 1)[0]
        again = write_logs(tmp_path, 1)[0]
        assert first != again and again.name.startswith("0101-000000-2_")
        assert first.exists() and again.exists()

    def test_the_list_is_newest_first_and_built_from_names(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 3, year=2025)
        write_logs(tmp_path, 2, year=2026)
        files = run_log.list_log_files(tmp_path)
        assert [(f.year, f.hhmmss) for f in files] == [
            (2026, "010000"), (2026, "000000"), (2025, "020000"), (2025, "010000"),
            (2025, "000000")]
        top = files[0]
        assert (top.input_format, top.output_format) == ("json", "json") and top.size > 0
        assert top.timestamp_text == "2026-01-01 01:00:00"

    def test_the_list_ignores_files_that_are_not_logs(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 1)
        (tmp_path / "2026" / "notes.txt").write_text("mine", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("mine", encoding="utf-8")
        (tmp_path / "misc").mkdir()
        (tmp_path / "misc" / "0101-000000_a-to-b_convert-log.yaml").write_text("x", encoding="utf-8")
        assert len(run_log.list_log_files(tmp_path)) == 1

    def test_a_missing_folder_lists_nothing(self, tmp_path: Path) -> None:
        assert run_log.list_log_files(tmp_path / "nope") == []

    def test_prune_removes_the_oldest_beyond_the_limit(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 5)
        assert run_log.prune_logs(tmp_path, 3) == 2
        remaining = [f.hhmmss for f in run_log.list_log_files(tmp_path)]
        assert remaining == ["040000", "030000", "020000"]

    def test_prune_removes_old_years_first_and_the_empty_year_folder(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 2, year=2025)
        write_logs(tmp_path, 2, year=2026)
        assert run_log.prune_logs(tmp_path, 2) == 2
        assert not (tmp_path / "2025").exists() and (tmp_path / "2026").exists()

    def test_prune_never_touches_files_that_are_not_logs(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 3)
        mine = tmp_path / "2026" / "keep-me.txt"
        mine.write_text("mine", encoding="utf-8")
        run_log.prune_logs(tmp_path, 1)
        assert mine.exists() and len(run_log.list_log_files(tmp_path)) == 1

    def test_prune_within_the_limit_does_nothing(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 2)
        assert run_log.prune_logs(tmp_path, 2) == 0 and run_log.prune_logs(tmp_path, 0) == 0

    def test_delete_one_removes_only_that_log(self, tmp_path: Path) -> None:
        paths = write_logs(tmp_path, 2)
        assert run_log.delete_log(paths[0])
        assert not paths[0].exists() and paths[1].exists()

    def test_delete_refuses_a_file_that_is_not_a_log(self, tmp_path: Path) -> None:
        other = tmp_path / "2026" / "x.yaml"
        other.parent.mkdir(parents=True)
        other.write_text("mine", encoding="utf-8")
        assert not run_log.delete_log(other) and other.exists()

    def test_delete_all_removes_logs_only(self, tmp_path: Path) -> None:
        write_logs(tmp_path, 3)
        mine = tmp_path / "2026" / "keep-me.txt"
        mine.write_text("mine", encoding="utf-8")
        assert run_log.delete_all_logs(tmp_path) == 3
        assert mine.exists() and run_log.list_log_files(tmp_path) == []


class HeadTests:
    def test_the_head_gives_the_expression_and_input_names(self, tmp_path: Path) -> None:
        entry = make_entry("shop.json", '{"a": 1}\n', "json", ".a | . + 1")
        path = tmp_path / "x.yaml"
        path.write_text(run_log.build_log(entry).text, encoding="utf-8")
        head = run_log.read_head(path)
        assert head == run_log.LogHead(expression=".a | . + 1", input_names=("shop.json",),
                                       rerunnable=True)

    def test_only_the_beginning_of_a_huge_file_is_read(self, tmp_path: Path) -> None:
        big = json.dumps({"k": ["line %d" % i for i in range(20000)]}) + "\n"
        entry = make_entry("big.json", big, "json", ".k[0]", output_text="line 0\n")
        text = run_log.build_log(entry, max_entry_bytes=10**9).text
        assert len(text.encode()) > run_log.HEAD_READ_BYTES * 2
        path = tmp_path / "big.yaml"
        path.write_text(text, encoding="utf-8")
        head = run_log.read_head(path)
        assert head.expression == ".k[0]" and head.input_names == ("big.json",)

    def test_a_missing_or_broken_file_gives_an_empty_head(self, tmp_path: Path) -> None:
        assert run_log.read_head(tmp_path / "none.yaml") == run_log.LogHead()
        bad = tmp_path / "bad.yaml"
        bad.write_text("garbage: [", encoding="utf-8")
        assert run_log.read_head(bad) == run_log.LogHead()
