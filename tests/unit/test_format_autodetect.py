"""YqService resolving "auto" from content when the input's name gives no answer.

The extension always wins first (unchanged); content is read only when it does not, and only once
even though both the guess and the actual decode need that same text - this matters most for stdin,
which can only be read a single time.
"""

from __future__ import annotations

import pytest
from yaqpy import Options
from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService


class CountingFileSystem(InMemoryFileSystem):
    """The same test double, plus a tally of how many times each read actually happened."""

    def __init__(self, files: dict[str, str] | None = None, stdin: str = "") -> None:
        super().__init__(files, stdin)
        self.text_reads: dict[str, int] = {}
        self.stdin_reads = 0

    def read_text(self, path: str) -> str:
        self.text_reads[path] = self.text_reads.get(path, 0) + 1
        return super().read_text(path)

    def read_stdin(self) -> str:
        self.stdin_reads += 1
        return super().read_stdin()


AUTO = Options(input_format="auto", output_format="json", indent=0)


def run(fs: InMemoryFileSystem, name: str, *, options: Options = AUTO) -> tuple[str, str, str]:
    service = YqService(fs, StaticEnvironment({}))
    request = EvaluateRequest(expression=".", inputs=(InputSource(name),), mode=EvalMode.STREAM,
                              options=options)
    result = service.evaluate(request, MemorySink())
    return result.output or "", result.input_format, result.output_format


class ContentDrivesTheGuessTests:
    def test_json_content_behind_an_unknown_extension(self) -> None:
        fs = InMemoryFileSystem({"a.log": '{"x": 1}'})
        out, in_fmt, _ = run(fs, "a.log")
        assert (out, in_fmt) == ('{"x":1}\n', "json")

    def test_toml_content_with_no_extension_at_all(self) -> None:
        fs = InMemoryFileSystem({"a": 'name = "yaqpy"\n'})
        out, in_fmt, _ = run(fs, "a")
        assert (out, in_fmt) == ('{"name":"yaqpy"}\n', "toml")

    def test_csv_content_via_stdin_which_has_no_name_to_go_by(self) -> None:
        fs = InMemoryFileSystem(stdin="name,age\nAlice,30\n")
        out, in_fmt, _ = run(fs, "-")
        assert (out, in_fmt) == ('[{"name":"Alice","age":30}]\n', "csv")

    def test_ordinary_yaml_content_falls_back_to_yaml_as_always(self) -> None:
        fs = InMemoryFileSystem({"a": "x: 1\ny: 2\n"})
        out, in_fmt, _ = run(fs, "a")
        assert (out, in_fmt) == ('{"x":1,"y":2}\n', "yaml")


class ExtensionStillWinsTests:
    """No content read at all when the extension already names a format - the fast path."""

    def test_a_json_file_is_never_sniffed_even_if_its_content_looks_like_toml(self) -> None:
        fs = CountingFileSystem({"a.json": 'name = "not actually json"'})
        # this would fail to decode as json if content were ever consulted for the *format choice*;
        # here it fails to decode as *json content* instead, proving json (not toml) was picked
        with pytest.raises(Exception, match="json|JSON"):
            run(fs, "a.json")

    def test_a_recognised_extension_costs_no_extra_read(self) -> None:
        fs = CountingFileSystem({"a.json": '{"x": 1}'})
        run(fs, "a.json")
        assert fs.text_reads == {"a.json": 1}


class SingleReadTests:
    def test_stdin_is_read_exactly_once_although_it_is_both_sniffed_and_decoded(self) -> None:
        fs = CountingFileSystem(stdin='{"a": 1}')
        run(fs, "-")
        assert fs.stdin_reads == 1

    def test_a_sniffed_file_is_read_exactly_once_too(self) -> None:
        fs = CountingFileSystem({"a.log": '{"a": 1}'})
        run(fs, "a.log")
        assert fs.text_reads == {"a.log": 1}

    def test_pre_read_text_from_the_caller_is_reused_not_re_read(self) -> None:
        """The GUI's path: InputSource already carries the text, so nothing is read at all."""
        fs = CountingFileSystem()
        service = YqService(fs, StaticEnvironment({}))
        request = EvaluateRequest(expression=".", inputs=(InputSource("<text>", '{"a": 1}'),),
                                  mode=EvalMode.STREAM, options=AUTO)
        result = service.evaluate(request, MemorySink())
        assert (result.output, result.input_format) == ('{"a":1}\n', "json")
        assert fs.text_reads == {} and fs.stdin_reads == 0


class NoInputTests:
    def test_null_input_never_reads_anything_and_defaults_to_yaml(self) -> None:
        fs = CountingFileSystem()
        service = YqService(fs, StaticEnvironment({}))
        request = EvaluateRequest(expression='"hi"', inputs=(), mode=EvalMode.STREAM,
                                  options=Options(input_format="auto", null_input=True))
        result = service.evaluate(request, MemorySink())
        assert (result.input_format, fs.text_reads, fs.stdin_reads) == ("yaml", {}, 0)


if __name__ == "__main__":
    pytest.main([__file__])
