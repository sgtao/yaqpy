"""Public API and service tests (design doc 10, 11)."""

from __future__ import annotations

import concurrent.futures
import unittest

import pyyq
from pyyq import Limits, Options, SecurityPolicy, Yq
from pyyq.app.dto import EvalMode, EvaluateRequest, InputSource
from pyyq.app.ports import InMemoryFileSystem, StaticEnvironment
from pyyq.app.printer import InPlaceSink, MemorySink
from pyyq.app.service import YqService
from pyyq.errors import EvaluationLimitError, ExpressionSyntaxError, FormatError, SecurityError

SAMPLE = "# サーバー設定\nserver:\n  port: 8080   # 開発用\n  hosts: [a, b]\n"


class FunctionApiTests(unittest.TestCase):
    def test_evaluate_preserves_comments(self) -> None:
        out = pyyq.evaluate(".server.port = 9090", SAMPLE)
        self.assertEqual(out, "# サーバー設定\nserver:\n  port: 9090 # 開発用\n  hosts: [a, b]\n")

    def test_evaluate_scalar_unwrapped(self) -> None:
        self.assertEqual(pyyq.evaluate(".server.port", SAMPLE), "8080\n")

    def test_query_and_update(self) -> None:
        self.assertEqual(pyyq.query(".server.hosts[]", {"server": {"hosts": ["a", "b"]}}), ["a", "b"])
        data = {"a": 1}
        self.assertEqual(pyyq.update(".b = .a + 1", data), {"a": 1, "b": 2})
        self.assertEqual(data, {"a": 1}, "input must not be mutated")

    def test_json_output(self) -> None:
        yq = Yq(Options(output_format="json", indent=0))
        expr = yq.compile(".server")
        self.assertEqual(yq.evaluate(expr, SAMPLE), '{"port":8080,"hosts":["a","b"]}\n')

    def test_evaluate_all(self) -> None:
        out = pyyq.evaluate_all("select(fi == 0) * select(fi == 1)", ["a: 1\n", "b: 2\n"])
        self.assertEqual(out, "a: 1\nb: 2\n")

    def test_null_input(self) -> None:
        self.assertEqual(pyyq.evaluate(".a.b = 1"), "a:\n  b: 1\n")

    def test_syntax_error(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            pyyq.compile(".a |")

    def test_format_error(self) -> None:
        with self.assertRaises(FormatError):
            pyyq.evaluate(".", "a: [1\n")

    def test_env_denied_by_default(self) -> None:
        with self.assertRaises(SecurityError):
            pyyq.evaluate('env(HOME)')

    def test_env_allowed(self) -> None:
        yq = Yq(Options(security=SecurityPolicy(allow_env=True)), environ={"NAME": "x"})
        self.assertEqual(yq.evaluate("strenv(NAME)"), "x\n")

    def test_step_limit(self) -> None:
        options = Options(limits=Limits(max_steps=5))
        with self.assertRaises(EvaluationLimitError):
            pyyq.evaluate("[.[] | . + 1]", "[1, 2, 3, 4, 5]\n", options=options)

    def test_load_and_dump(self) -> None:
        docs = pyyq.load("a: 1\n---\nb: 2\n")
        self.assertEqual(len(docs), 2)
        self.assertEqual(pyyq.dump(docs), "a: 1\n---\nb: 2\n")
        self.assertEqual(pyyq.dump(docs, format="json", options=Options(indent=0)),
                         '{"a":1}\n{"b":2}\n')


class ServiceTests(unittest.TestCase):
    def test_in_place_write(self) -> None:
        fs = InMemoryFileSystem({"f.yml": "a: 1\n"})
        service = YqService(fs, StaticEnvironment())
        request = EvaluateRequest(expression=".a = 2", inputs=(InputSource("f.yml"),), in_place=True)
        service.evaluate(request, InPlaceSink("f.yml"))
        self.assertEqual(fs.files["f.yml"], "a: 2\n")

    def test_missing_file(self) -> None:
        service = YqService(InMemoryFileSystem(), StaticEnvironment())
        request = EvaluateRequest(expression=".", inputs=(InputSource("nope.yml"),))
        with self.assertRaises(FormatError):
            service.evaluate(request, MemorySink())

    def test_stream_vs_all(self) -> None:
        fs = InMemoryFileSystem({"a.yml": "x: 1\n---\nx: 2\n"})
        service = YqService(fs, StaticEnvironment())
        stream = service.evaluate(
            EvaluateRequest(expression="[.x]", inputs=(InputSource("a.yml"),)), MemorySink())
        # like Go: a collected node has no parent, so no document separator is printed
        self.assertEqual(stream.output, "- 1\n- 2\n")
        scalars = service.evaluate(
            EvaluateRequest(expression=".x", inputs=(InputSource("a.yml"),)), MemorySink())
        self.assertEqual(scalars.output, "1\n---\n2\n")
        together = service.evaluate(
            EvaluateRequest(expression="[.x]", inputs=(InputSource("a.yml"),), mode=EvalMode.ALL),
            MemorySink())
        self.assertEqual(together.output, "- 1\n- 2\n")

    def test_printed_anything(self) -> None:
        service = YqService(InMemoryFileSystem({"a.yml": "x: false\n"}), StaticEnvironment())
        result = service.evaluate(
            EvaluateRequest(expression=".x", inputs=(InputSource("a.yml"),)), MemorySink())
        self.assertFalse(result.printed_anything)

    def test_validate_expression(self) -> None:
        service = YqService(InMemoryFileSystem(), StaticEnvironment())
        self.assertTrue(service.validate_expression(".a").valid)
        info = service.validate_expression("(.a")
        self.assertFalse(info.valid)


class ConcurrencyTests(unittest.TestCase):
    def test_different_options_in_parallel(self) -> None:
        yaml_yq = Yq(Options(output_format="yaml"))
        json_yq = Yq(Options(output_format="json", indent=0))

        def work(i: int) -> tuple[str, str]:
            text = f"a: {i}\n"
            return yaml_yq.evaluate(".a + 1", text), json_yq.evaluate(".", text)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(work, range(50)))
        for i, (y, j) in enumerate(results):
            self.assertEqual(y, f"{i + 1}\n")
            self.assertEqual(j, f'{{"a":{i}}}\n')


if __name__ == "__main__":
    unittest.main()
