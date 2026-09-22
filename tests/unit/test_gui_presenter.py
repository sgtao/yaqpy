"""Presenter のテスト（GUI 設計書 9-2 の T5〜T10・T15）。"""

from __future__ import annotations

import json

from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

SAMPLE = (
    "# サーバー設定\n"
    "server:\n"
    "  port: 8080 # 開発用\n"
    "  hosts: [a, b]\n"
    "items:\n"
    "  - name: pen\n"
    "    price: 120\n"
    "  - name: book\n"
    "    price: 980\n"
)
BROKEN = "a: [1\n"
FILES = {"/w/sample.yaml": SAMPLE, "/w/broken.yaml": BROKEN, "/w/data.json": '{"a": 1}',
        "/w/other.yaml": "b: 2\n"}


def make_presenter(environ: dict[str, str] | None = None) -> MainPresenter:
    fs = InMemoryFileSystem(dict(FILES))
    service = YqService(fs, StaticEnvironment(environ or {}))
    return MainPresenter(service=service, fs=fs, state=GuiState(),
                         size_of=lambda p: len(fs.files[p].encode("utf-8")))


class OpenTests:
    async def test_open_keeps_the_original_text(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/sample.yaml")
        assert vm.ok
        assert vm.original_text == SAMPLE
        assert p.state.document.name == "sample.yaml"
        assert p.state.query.expression == "."

    async def test_open_missing_file_reports_an_error(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/nope.yaml")
        assert not vm.ok
        assert vm.error.code == "intake"

    async def test_close_clears_the_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.close_document()
        assert not p.state.document.is_loaded


class MultiDocumentTests:
    """複数ファイルを開いておける（U3）。"""

    async def test_add_path_keeps_the_previous_document_open(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        vm = await p.add_path("/w/other.yaml")
        assert vm.ok
        assert [d.name for d in p.state.documents] == ["sample.yaml", "other.yaml"]
        assert p.state.active_index == 1
        assert p.state.document.name == "other.yaml"

    async def test_add_path_keeps_the_expression(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        await p.add_path("/w/other.yaml")
        assert p.state.query.expression == ".server.port"

    async def test_add_path_reports_a_missing_file_without_closing_anything(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        vm = await p.add_path("/w/nope.yaml")
        assert not vm.ok
        assert len(p.state.documents) == 1

    async def test_select_document_switches_the_active_one(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        p.select_document(0)
        assert p.state.document.name == "sample.yaml"

    async def test_select_document_ignores_an_out_of_range_index(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.select_document(5)
        assert p.state.active_index == 0

    async def test_close_document_at_removes_just_that_one(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        p.close_document_at(0)
        assert [d.name for d in p.state.documents] == ["other.yaml"]
        assert p.state.document.name == "other.yaml"

    async def test_close_document_at_the_last_one_clears_everything(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.close_document_at(0)
        assert p.state.documents == []
        assert not p.state.document.is_loaded

    async def test_closing_down_to_one_document_turns_off_eval_all(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        p.state.eval_all = True
        p.close_document_at(1)
        assert not p.state.eval_all

    async def test_opening_a_new_file_replaces_the_whole_list(self) -> None:
        """既存の「ファイルを開く」は今までどおり一覧を作り直す。"""
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        await p.open_path("/w/data.json")
        assert [d.name for d in p.state.documents] == ["data.json"]


class EvalAllTests:
    """CLI の ``eval-all`` に相当する、複数文書をまとめた評価（U3）。"""

    async def _with_two_documents(self) -> "MainPresenter":
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        p.state.eval_all = True
        return p

    async def test_a_single_document_ignores_eval_all(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.eval_all = True                # 1 件しかないので効かない
        vm = await p.run()
        assert vm.ok
        assert vm.document_count == 1

    async def test_evaluates_every_open_document_together(self) -> None:
        p = await self._with_two_documents()
        p.state.query.expression = "select(fi == 0) * select(fi == 1)"
        vm = await p.run()
        assert vm.ok, str(vm.error)
        assert vm.document_count == 2
        # sample.yaml と other.yaml の内容が、1 通の文書に合体して出る
        assert "port: 8080" in vm.full_text
        assert "b: 2" in vm.full_text
        assert vm.full_text.count("---") == 0          # 別々の文書としては出ない

    async def test_fi_cannot_distinguish_files_without_eval_all(self) -> None:
        """比較として：まとめない（既定）と fi は常に 0 で、越境した select は当たらない。"""
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.add_path("/w/other.yaml")
        p.state.eval_all = False
        p.state.query.expression = "select(fi == 0) * select(fi == 1)"
        vm = await p.run()
        assert vm.ok
        assert vm.full_text == ""            # active な other.yaml (fi=0) 単体では何も一致しない


class RunTests:
    async def test_identity_returns_the_whole_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        vm = await p.run()
        assert vm.ok
        assert vm.input_format == "yaml"
        assert vm.output_format == "yaml"
        assert vm.document_count == 1
        assert "# サーバー設定" in vm.full_text     # コメントが保たれている

    async def test_property_filter(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        vm = await p.run()
        assert vm.full_text == "8080\n"

    async def test_json_output(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "json"
        p.state.query.expression = ".server"
        vm = await p.run()
        assert vm.output_format == "json"
        assert json.loads(vm.full_text) == {"port": 8080, "hosts": ["a", "b"]}

    async def test_json_input_is_detected_from_the_extension(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        vm = await p.run()
        assert vm.input_format == "json"

    async def test_select_expression(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".items[] | select(.price > 500)"
        vm = await p.run()
        assert "book" in vm.full_text
        assert "pen" not in vm.full_text

    async def test_syntax_error_is_not_evaluated(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.("
        vm = await p.run()
        assert not vm.ok
        assert vm.error.code == "expression_syntax"
        assert vm.full_text == ""

    async def test_broken_yaml_keeps_the_original(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        vm = await p.run()
        assert not vm.ok
        assert vm.error.code in {"yaml_syntax", "format"}
        assert p.state.document.original_text == BROKEN   # 原文は残っている

    async def test_run_without_a_document(self) -> None:
        p = make_presenter()
        vm = await p.run()
        assert vm.error.code == "no_document"


class SecurityTests:
    async def test_env_is_denied_by_default(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        assert not vm.ok
        assert vm.error.code == "security"
        assert vm.error.capability == "env"

    async def test_env_can_be_allowed_from_settings(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.settings.allow_env = True
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        assert vm.ok, str(vm.error)
        assert vm.full_text == "x\n"


class CancelTests:
    async def test_cancelled_budget_becomes_an_error(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        original = p._service.new_budget

        def pre_cancelled(options):
            budget = original(options)
            budget.cancel()
            return budget

        p._service.new_budget = pre_cancelled          # type: ignore[method-assign]
        vm = await p.run()
        assert not vm.ok
        assert vm.error.limit == "cancelled"

    async def test_cancel_without_a_running_job_is_harmless(self) -> None:
        make_presenter().cancel()

    async def test_cancel_interrupts_a_running_evaluation(self) -> None:
        """実行中の評価を別タスクから止められる（G-NFR-02）。

        3 重の直積は数十秒かかる重さなので、0.2 秒後の中止は必ず「走行中」に届く。
        効かなかった場合は 10 秒のタイムアウトで limit が変わり、下の検査で落ちる。
        """
        import asyncio

        fs = InMemoryFileSystem({"/w/big.yaml": "".join(f"- id: {i}\n" for i in range(400))})
        p = MainPresenter(service=YqService(fs, StaticEnvironment()), fs=fs, state=GuiState(),
                          size_of=lambda path: 1)
        p.state.settings.timeout_seconds = 10.0
        await p.open_path("/w/big.yaml")
        p.state.query.expression = "[.[] as $a | .[] as $b | .[] as $c | $a.id] | length"

        async def canceller() -> None:
            await asyncio.sleep(0.2)
            assert p.state.running
            p.cancel()

        task = asyncio.create_task(canceller())
        vm = await p.run()
        await task
        assert not vm.ok
        assert vm.error.limit == "cancelled"
        assert not p.state.running


class TruncationTests:
    async def test_display_is_cut_but_full_text_is_not(self) -> None:
        p = make_presenter()
        p.state.settings.max_display_lines = 3
        p.open_text("\n".join(f"- item{i}" for i in range(50)) + "\n", name="many.yaml")
        vm = await p.run()
        assert vm.ok, str(vm.error)
        assert vm.display_text.count("\n") == 3
        assert vm.full_text.count("\n") == 50
        assert vm.truncated_lines == 47


class CandidateTests:
    async def _ready(self) -> MainPresenter:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.run()
        return p

    async def test_candidates_are_built_after_a_run(self) -> None:
        p = await self._ready()
        vm = await p.build_candidates()
        expressions = [c.expression for c in vm.candidates]
        assert ".server.port" in expressions
        assert ".items[].name" in expressions
        assert not vm.truncated

    async def test_candidates_need_a_successful_run(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        await p.run()                                # 失敗する
        vm = await p.build_candidates()
        assert vm.is_empty
        assert vm.note

    async def test_candidates_follow_the_detected_format(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        await p.run()
        vm = await p.build_candidates()
        assert [c.expression for c in vm.candidates] == [".a"]

    async def test_candidates_come_back_after_fixing_the_input_format(self) -> None:
        """拡張子と中身が食い違って読めなかった文書を、入力形式の指定で救えること。"""
        fs = InMemoryFileSystem({"/w/data.json": "a: 1\n"})      # 中身は YAML
        p = MainPresenter(service=YqService(fs, StaticEnvironment()), fs=fs, state=GuiState(),
                          size_of=lambda path: 5)
        await p.open_path("/w/data.json")
        vm = await p.run()                                        # auto → json として読んで失敗
        assert not vm.ok
        assert (await p.build_candidates()).is_empty

        p.state.query.input_format = "yaml"
        assert (await p.run()).ok
        after = await p.build_candidates()
        assert [c.expression for c in after.candidates] == [".a"]

    async def test_a_document_without_properties_explains_itself(self) -> None:
        p = make_presenter()
        p.open_text("just a string\n", name="scalar.yaml")
        await p.run()
        vm = await p.build_candidates()
        assert vm.is_empty
        assert vm.note

    async def test_filter_is_case_insensitive(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        assert [c.expression for c in p.filter_candidates("PORT")] == [".server.port"]
        assert p.filter_candidates("")     # 空なら全件

    async def test_filter_limit(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        assert len(p.filter_candidates("", limit=2)) == 2

    async def test_apply_replaces_the_expression(self) -> None:
        p = await self._ready()
        assert p.apply_candidate(".server.port") == ".server.port"
        assert p.state.query.expression == ".server.port"

    async def test_apply_append_joins_with_a_pipe(self) -> None:
        p = await self._ready()
        p.apply_candidate(".items[]")
        assert p.apply_candidate(".name", append=True) == ".items[] | .name"

    async def test_append_does_not_duplicate_the_selected_candidate(self) -> None:
        p = await self._ready()
        p.apply_candidate(".items[]")                 # 選ぶと式欄が置き換わる
        assert p.apply_candidate(".items[]", append=True) == ".items[]"
        p.apply_candidate(".items[] | .name")
        assert p.apply_candidate(".name", append=True) == ".items[] | .name"

    async def test_append_on_the_identity_expression_replaces(self) -> None:
        p = await self._ready()                     # 開いた直後の式は "."
        assert p.apply_candidate(".server", append=True) == ".server"

    async def test_applied_candidate_runs(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.apply_candidate(".items[] | select(.price > 500)")
        vm = await p.run()
        assert vm.ok, str(vm.error)
        assert "book" in vm.full_text

    async def test_candidates_are_cleared_when_the_document_closes(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.close_document()
        assert p.filter_candidates() == []

    async def test_candidates_are_cleared_when_another_document_opens(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        await p.open_path("/w/data.json")
        assert p.filter_candidates() == []


class SaveTests:
    async def _ready(self) -> MainPresenter:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        await p.run()
        return p

    async def test_saves_the_result(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/out.yaml")
        assert vm.ok, str(vm.error)
        assert p._fs.written["/w/out.yaml"] == "8080\n"
        assert vm.byte_size == len(b"8080\n")

    async def test_saves_the_full_text_not_the_display_text(self) -> None:
        """リスク R8：表示を丸めても保存内容は全量であること。"""
        p = make_presenter()
        p.state.settings.max_display_lines = 3
        p.open_text("\n".join(f"- item{i}" for i in range(50)) + "\n", name="many.yaml")
        run = await p.run()
        assert run.display_text.count("\n") == 3
        await p.save("/w/all.yaml")
        assert p._fs.written["/w/all.yaml"] == run.full_text
        assert p._fs.written["/w/all.yaml"].count("\n") == 50

    async def test_refuses_to_overwrite_the_source_without_confirmation(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/sample.yaml")
        assert not vm.ok
        assert vm.needs_overwrite_confirmation
        assert "/w/sample.yaml" not in p._fs.written     # 書いていない

    async def test_overwrites_the_source_only_when_confirmed(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/sample.yaml", confirmed=True)
        assert vm.ok
        assert p._fs.written["/w/sample.yaml"] == "8080\n"

    async def test_overwriting_backs_up_the_original_content_first(self) -> None:
        """G4 の緩和（U2）：上書きの直前に元の内容を .bak として残す。"""
        p = await self._ready()
        vm = await p.save("/w/sample.yaml", confirmed=True)
        assert vm.ok
        assert vm.backup_path == "/w/sample.yaml.bak"
        assert p._fs.files["/w/sample.yaml.bak"] == SAMPLE     # 上書き前の中身
        assert p._fs.files["/w/sample.yaml"] == "8080\n"       # 新しい中身

    async def test_saving_elsewhere_makes_no_backup(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/out.yaml")
        assert vm.ok
        assert vm.backup_path == ""
        assert "/w/out.yaml.bak" not in p._fs.files

    async def test_backup_failure_leaves_the_source_untouched(self) -> None:
        """バックアップが作れなければ、元のファイルは書き換えない。"""

        class _FailingBackupFs(InMemoryFileSystem):
            def atomic_write(self, path: str, text: str) -> None:
                if path.endswith(".bak"):
                    raise OSError("disk full")
                super().atomic_write(path, text)

        fs = _FailingBackupFs(dict(FILES))
        service = YqService(fs, StaticEnvironment({}))
        p = MainPresenter(service=service, fs=fs, state=GuiState(),
                          size_of=lambda path: len(fs.files[path].encode("utf-8")))
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        await p.run()
        vm = await p.save("/w/sample.yaml", confirmed=True)
        assert not vm.ok
        assert fs.files["/w/sample.yaml"] == SAMPLE            # 書き換わっていない

    async def test_runs_again_when_there_is_no_fresh_result(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")        # run() していない
        vm = await p.save("/w/out.yaml")
        assert vm.ok, str(vm.error)
        assert "# サーバー設定" in p._fs.written["/w/out.yaml"]

    async def test_a_failed_run_leaves_nothing_stale_to_save(self) -> None:
        """不変条件 S2：画面に結果が無いのに、古い結果が保存されてはならない。"""
        p = await self._ready()                     # .server.port → 8080 の結果がある
        p.state.query.expression = ".server.("
        assert not (await p.run()).ok
        assert p.last_run is None
        vm = await p.save("/w/out.yaml")
        assert not vm.ok
        assert vm.error.code == "expression_syntax"
        assert "/w/out.yaml" not in p._fs.written

    async def test_save_failure_is_reported(self) -> None:
        p = await self._ready()

        def broken(path: str, text: str) -> None:
            raise PermissionError(13, "Permission denied")

        p._fs.atomic_write = broken             # type: ignore[method-assign]
        vm = await p.save("/w/out.yaml")
        assert not vm.ok
        assert vm.error.code == "io"

    async def test_save_without_a_document(self) -> None:
        p = make_presenter()
        vm = await p.save("/w/out.yaml")
        assert not vm.ok
        assert vm.error.code == "no_document"


class DefaultSaveNameTests:
    async def test_follows_the_output_format(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "json"
        await p.run()
        assert p.default_save_name() == "sample.json"

    async def test_properties_extension(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "props"
        await p.run()
        assert p.default_save_name() == "sample.properties"

    async def test_pasted_text_gets_a_generic_name(self) -> None:
        p = make_presenter()
        p.open_text("a: 1\n")
        await p.run()
        assert p.default_save_name() == "output.yaml"


class ValidateTests:
    def test_empty_expression_is_valid(self) -> None:
        assert make_presenter().validate("").valid

    def test_broken_expression_reports_a_position(self) -> None:
        vm = make_presenter().validate(".server.(")
        assert not vm.valid
        assert vm.message
