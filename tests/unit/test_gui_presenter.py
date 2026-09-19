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

        def pre_cancelled(options):          # noqa: ANN001, ANN202
            budget = original(options)
            budget.cancel()
            return budget

        p._service.new_budget = pre_cancelled          # type: ignore[method-assign]
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.limit, "cancelled")

    async def test_cancel_without_a_running_job_is_harmless(self) -> None:
        make_presenter().cancel()


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


class ValidateTests(unittest.TestCase):
    def test_empty_expression_is_valid(self) -> None:
        self.assertTrue(make_presenter().validate("").valid)

    def test_broken_expression_reports_a_position(self) -> None:
        vm = make_presenter().validate(".server.(")
        self.assertFalse(vm.valid)
        self.assertTrue(vm.message)


if __name__ == "__main__":
    unittest.main()
