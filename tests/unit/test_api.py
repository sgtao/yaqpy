"""Public API and service tests (design doc 10, 11)."""

from __future__ import annotations

import concurrent.futures

import pytest
import yaqpy
from yaqpy import Limits, Options, SecurityPolicy, Yq
from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.printer import InPlaceSink, MemorySink
from yaqpy.app.service import YqService
from yaqpy.errors import EvaluationLimitError, ExpressionSyntaxError, FormatError, SecurityError

SAMPLE = "# サーバー設定\nserver:\n  port: 8080   # 開発用\n  hosts: [a, b]\n"


class FunctionApiTests:
    def test_evaluate_preserves_comments(self) -> None:
        out = yaqpy.evaluate(".server.port = 9090", SAMPLE)
        assert out == "# サーバー設定\nserver:\n  port: 9090 # 開発用\n  hosts: [a, b]\n"

    def test_evaluate_scalar_unwrapped(self) -> None:
        assert yaqpy.evaluate(".server.port", SAMPLE) == "8080\n"

    def test_query_and_update(self) -> None:
        assert yaqpy.query(".server.hosts[]", {"server": {"hosts": ["a", "b"]}}) == ["a", "b"]
        data = {"a": 1}
        assert yaqpy.update(".b = .a + 1", data) == {"a": 1, "b": 2}
        assert data == {"a": 1}, "input must not be mutated"

    def test_json_output(self) -> None:
        yq = Yq(Options(output_format="json", indent=0))
        expr = yq.compile(".server")
        assert yq.evaluate(expr, SAMPLE) == '{"port":8080,"hosts":["a","b"]}\n'

    def test_evaluate_all(self) -> None:
        out = yaqpy.evaluate_all("select(fi == 0) * select(fi == 1)", ["a: 1\n", "b: 2\n"])
        assert out == "a: 1\nb: 2\n"

    def test_null_input(self) -> None:
        assert yaqpy.evaluate(".a.b = 1") == "a:\n  b: 1\n"

    def test_syntax_error(self) -> None:
        with pytest.raises(ExpressionSyntaxError):
            yaqpy.compile(".a |")

    def test_format_error(self) -> None:
        with pytest.raises(FormatError):
            yaqpy.evaluate(".", "a: [1\n")

    def test_env_denied_by_default(self) -> None:
        with pytest.raises(SecurityError):
            yaqpy.evaluate('env(HOME)')

    def test_env_allowed(self) -> None:
        yq = Yq(Options(security=SecurityPolicy(allow_env=True)), environ={"NAME": "x"})
        assert yq.evaluate("strenv(NAME)") == "x\n"

    def test_step_limit(self) -> None:
        options = Options(limits=Limits(max_steps=5))
        with pytest.raises(EvaluationLimitError):
            yaqpy.evaluate("[.[] | . + 1]", "[1, 2, 3, 4, 5]\n", options=options)

    def test_load_and_dump(self) -> None:
        docs = yaqpy.load("a: 1\n---\nb: 2\n")
        assert len(docs) == 2
        assert yaqpy.dump(docs) == "a: 1\n---\nb: 2\n"
        assert yaqpy.dump(docs, format="json", options=Options(indent=0)) == '{"a":1}\n{"b":2}\n'


class ServiceTests:
    def test_in_place_write(self) -> None:
        fs = InMemoryFileSystem({"f.yml": "a: 1\n"})
        service = YqService(fs, StaticEnvironment())
        request = EvaluateRequest(expression=".a = 2", inputs=(InputSource("f.yml"),), in_place=True)
        service.evaluate(request, InPlaceSink("f.yml"))
        assert fs.files["f.yml"] == "a: 2\n"

    def test_missing_file(self) -> None:
        service = YqService(InMemoryFileSystem(), StaticEnvironment())
        request = EvaluateRequest(expression=".", inputs=(InputSource("nope.yml"),))
        with pytest.raises(FormatError):
            service.evaluate(request, MemorySink())

    def test_stream_vs_all(self) -> None:
        fs = InMemoryFileSystem({"a.yml": "x: 1\n---\nx: 2\n"})
        service = YqService(fs, StaticEnvironment())
        stream = service.evaluate(
            EvaluateRequest(expression="[.x]", inputs=(InputSource("a.yml"),)), MemorySink())
        # like Go: a collected node has no parent, so no document separator is printed
        assert stream.output == "- 1\n- 2\n"
        scalars = service.evaluate(
            EvaluateRequest(expression=".x", inputs=(InputSource("a.yml"),)), MemorySink())
        assert scalars.output == "1\n---\n2\n"
        together = service.evaluate(
            EvaluateRequest(expression="[.x]", inputs=(InputSource("a.yml"),), mode=EvalMode.ALL),
            MemorySink())
        assert together.output == "- 1\n- 2\n"

    def test_printed_anything(self) -> None:
        service = YqService(InMemoryFileSystem({"a.yml": "x: false\n"}), StaticEnvironment())
        result = service.evaluate(
            EvaluateRequest(expression=".x", inputs=(InputSource("a.yml"),)), MemorySink())
        assert not result.printed_anything

    def test_validate_expression(self) -> None:
        service = YqService(InMemoryFileSystem(), StaticEnvironment())
        assert service.validate_expression(".a").valid
        info = service.validate_expression("(.a")
        assert not info.valid


class ConcurrencyTests:
    def test_different_options_in_parallel(self) -> None:
        yaml_yq = Yq(Options(output_format="yaml"))
        json_yq = Yq(Options(output_format="json", indent=0))

        def work(i: int) -> tuple[str, str]:
            text = f"a: {i}\n"
            return yaml_yq.evaluate(".a + 1", text), json_yq.evaluate(".", text)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(work, range(50)))
        for i, (y, j) in enumerate(results):
            assert y == f"{i + 1}\n"
            assert j == f'{{"a":{i}}}\n'


class ServiceBudgetTests:
    """改修 B / C: 外から渡した StepBudget と、解決済み形式の報告。"""

    def _service(self) -> YqService:
        return YqService(InMemoryFileSystem(), StaticEnvironment())

    def _request(self, text: str = "a: 1\n", name: str = "<text>") -> EvaluateRequest:
        return EvaluateRequest(
            expression=".",
            inputs=(InputSource(name, text),),
            options=Options(input_format="auto", output_format="auto"),
            input_format="auto",
            output_format="auto",
        )

    def test_external_budget_can_cancel(self) -> None:
        service = self._service()
        options = Options()
        budget = service.new_budget(options)
        budget.cancel()                      # 走り出す前に中止しておく（決定的に再現できる）
        with pytest.raises(EvaluationLimitError) as ctx:
            service.evaluate(self._request(), MemorySink(), budget=budget)
        assert ctx.value.limit == "cancelled"

    def test_budget_is_optional(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(), MemorySink())
        assert result.output == "a: 1\n"

    def test_result_reports_resolved_formats(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(name="config.json", text='{"a":1}'),
                                  MemorySink())
        assert result.input_format == "json"
        assert result.output_format == "json"

    def test_auto_falls_back_to_yaml_for_unknown_extension(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(name="config.conf"), MemorySink())
        assert result.input_format == "yaml"
