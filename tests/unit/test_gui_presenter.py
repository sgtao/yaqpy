"""Presenter のテスト（GUI 設計書 9-2 の T5〜T10・T15）。"""

from __future__ import annotations

import json
import unittest

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
FILES = {"/w/sample.yaml": SAMPLE, "/w/broken.yaml": BROKEN, "/w/data.json": '{"a": 1}'}


def make_presenter(environ: dict[str, str] | None = None) -> MainPresenter:
    fs = InMemoryFileSystem(dict(FILES))
    service = YqService(fs, StaticEnvironment(environ or {}))
    return MainPresenter(service=service, fs=fs, state=GuiState(),
                         size_of=lambda p: len(fs.files[p].encode("utf-8")))


class OpenTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_keeps_the_original_text(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/sample.yaml")
        self.assertTrue(vm.ok)
        self.assertEqual(vm.original_text, SAMPLE)
        self.assertEqual(p.state.document.name, "sample.yaml")
        self.assertEqual(p.state.query.expression, ".")

    async def test_open_missing_file_reports_an_error(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/nope.yaml")
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "intake")

    async def test_close_clears_the_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.close_document()
        self.assertFalse(p.state.document.is_loaded)


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_returns_the_whole_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        vm = await p.run()
        self.assertTrue(vm.ok)
        self.assertEqual(vm.input_format, "yaml")
        self.assertEqual(vm.output_format, "yaml")
        self.assertEqual(vm.document_count, 1)
        self.assertIn("# サーバー設定", vm.full_text)     # コメントが保たれている

    async def test_property_filter(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        vm = await p.run()
        self.assertEqual(vm.full_text, "8080\n")

    async def test_json_output(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "json"
        p.state.query.expression = ".server"
        vm = await p.run()
        self.assertEqual(vm.output_format, "json")
        self.assertEqual(json.loads(vm.full_text), {"port": 8080, "hosts": ["a", "b"]})

    async def test_json_input_is_detected_from_the_extension(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        vm = await p.run()
        self.assertEqual(vm.input_format, "json")

    async def test_select_expression(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".items[] | select(.price > 500)"
        vm = await p.run()
        self.assertIn("book", vm.full_text)
        self.assertNotIn("pen", vm.full_text)

    async def test_syntax_error_is_not_evaluated(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.("
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "expression_syntax")
        self.assertEqual(vm.full_text, "")

    async def test_broken_yaml_keeps_the_original(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertIn(vm.error.code, {"yaml_syntax", "format"})
        self.assertEqual(p.state.document.original_text, BROKEN)   # 原文は残っている

    async def test_run_without_a_document(self) -> None:
        p = make_presenter()
        vm = await p.run()
        self.assertEqual(vm.error.code, "no_document")


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_env_is_denied_by_default(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "security")
        self.assertEqual(vm.error.capability, "env")

    async def test_env_can_be_allowed_from_settings(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.settings.allow_env = True
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertEqual(vm.full_text, "x\n")


class CancelTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.limit, "cancelled")

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
            self.assertTrue(p.state.running)
            p.cancel()

        task = asyncio.create_task(canceller())
        vm = await p.run()
        await task
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.limit, "cancelled")
        self.assertFalse(p.state.running)


class TruncationTests(unittest.IsolatedAsyncioTestCase):
    async def test_display_is_cut_but_full_text_is_not(self) -> None:
        p = make_presenter()
        p.state.settings.max_display_lines = 3
        p.open_text("\n".join(f"- item{i}" for i in range(50)) + "\n", name="many.yaml")
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertEqual(vm.display_text.count("\n"), 3)
        self.assertEqual(vm.full_text.count("\n"), 50)
        self.assertEqual(vm.truncated_lines, 47)


class CandidateTests(unittest.IsolatedAsyncioTestCase):
    async def _ready(self) -> MainPresenter:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.run()
        return p

    async def test_candidates_are_built_after_a_run(self) -> None:
        p = await self._ready()
        vm = await p.build_candidates()
        expressions = [c.expression for c in vm.candidates]
        self.assertIn(".server.port", expressions)
        self.assertIn(".items[].name", expressions)
        self.assertFalse(vm.truncated)

    async def test_candidates_need_a_successful_run(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        await p.run()                                # 失敗する
        vm = await p.build_candidates()
        self.assertTrue(vm.is_empty)
        self.assertTrue(vm.note)

    async def test_candidates_follow_the_detected_format(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        await p.run()
        vm = await p.build_candidates()
        self.assertEqual([c.expression for c in vm.candidates], [".a"])

    async def test_a_document_without_properties_explains_itself(self) -> None:
        p = make_presenter()
        p.open_text("just a string\n", name="scalar.yaml")
        await p.run()
        vm = await p.build_candidates()
        self.assertTrue(vm.is_empty)
        self.assertTrue(vm.note)

    async def test_filter_is_case_insensitive(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        self.assertEqual([c.expression for c in p.filter_candidates("PORT")], [".server.port"])
        self.assertTrue(p.filter_candidates(""))     # 空なら全件

    async def test_filter_limit(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        self.assertEqual(len(p.filter_candidates("", limit=2)), 2)

    async def test_apply_replaces_the_expression(self) -> None:
        p = await self._ready()
        self.assertEqual(p.apply_candidate(".server.port"), ".server.port")
        self.assertEqual(p.state.query.expression, ".server.port")

    async def test_apply_append_joins_with_a_pipe(self) -> None:
        p = await self._ready()
        p.apply_candidate(".items[]")
        self.assertEqual(p.apply_candidate(".name", append=True), ".items[] | .name")

    async def test_append_on_the_identity_expression_replaces(self) -> None:
        p = await self._ready()                     # 開いた直後の式は "."
        self.assertEqual(p.apply_candidate(".server", append=True), ".server")

    async def test_applied_candidate_runs(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.apply_candidate(".items[] | select(.price > 500)")
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertIn("book", vm.full_text)

    async def test_candidates_are_cleared_when_the_document_closes(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.close_document()
        self.assertEqual(p.filter_candidates(), [])

    async def test_candidates_are_cleared_when_another_document_opens(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        await p.open_path("/w/data.json")
        self.assertEqual(p.filter_candidates(), [])


class ValidateTests(unittest.TestCase):
    def test_empty_expression_is_valid(self) -> None:
        self.assertTrue(make_presenter().validate("").valid)

    def test_broken_expression_reports_a_position(self) -> None:
        vm = make_presenter().validate(".server.(")
        self.assertFalse(vm.valid)
        self.assertTrue(vm.message)


if __name__ == "__main__":
    unittest.main()
