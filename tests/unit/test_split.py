"""-s（分割出力）をライブラリ側から：ファイル名の決まり方と、書き込みの安全策。"""

from __future__ import annotations

import pytest
from yaqpy import Options
from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.ports import InMemoryFileSystem, SandboxFileSystem, StaticEnvironment
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService
from yaqpy.errors import FormatError, SecurityError, YqError
from yaqpy.options import SecurityPolicy

ALLOWED = Options(security=SecurityPolicy(allow_file=True))

DOCS = "a: one\n---\na: two\n"


def split(expression: str, *, fs: object | None = None, text: str = DOCS, options: Options | None = None,
          mode: EvalMode = EvalMode.STREAM, **request: object) -> InMemoryFileSystem:
    files = fs if fs is not None else InMemoryFileSystem()
    service = YqService(files, StaticEnvironment({}))  # type: ignore[arg-type]
    service.evaluate(EvaluateRequest(
        expression=request.pop("main", "."), inputs=(InputSource("<text>", text),), mode=mode,  # type: ignore[arg-type]
        options=options or ALLOWED, split_expression=expression, **request), MemorySink())  # type: ignore[arg-type]
    return files  # type: ignore[return-value]


class SplitTests:
    def test_names_come_from_the_expression(self) -> None:
        fs = split(".a")
        assert fs.written == {"one.yml": "a: one\n", "two.yml": "---\na: two\n"}

    def test_index_counts_the_results(self) -> None:
        fs = split('"part-" + $index')
        assert sorted(fs.written) == ["part-0.yml", "part-1.yml"]

    def test_an_existing_extension_is_kept(self) -> None:
        assert sorted(split('.a + ".txt"').written) == ["one.txt", "two.txt"]
        assert sorted(split('.a + ".tar.gz"').written) == ["one.tar.gz", "two.tar.gz"]

    def test_a_dot_in_the_middle_is_not_an_extension(self) -> None:
        assert sorted(split('"v1.2-" + .a').written) == ["v1.2-one.yml", "v1.2-two.yml"]

    def test_no_name_gives_a_file_called_dot_extension(self) -> None:
        assert sorted(split(".zzz | select(. != null)").written) == [".yml"]

    @pytest.mark.parametrize("name", ('"../x"', '"a/../../x"', '"..\\x"', '".."'))
    def test_dot_dot_is_refused_and_nothing_is_written(self, name) -> None:
        fs = InMemoryFileSystem()
        with pytest.raises(FormatError):
            split(name, fs=fs)
        assert fs.written == {}

    def test_two_dots_inside_a_name_are_not_a_parent_directory(self) -> None:
        # "a..b" ends in ".b", which counts as its extension
        assert sorted(split('"a..b"').written) == ["a..b"]

    def test_the_sandbox_file_system_refuses(self) -> None:
        with pytest.raises(SecurityError):
            split(".a", fs=SandboxFileSystem())

    def test_it_is_refused_when_file_operations_are_disabled(self) -> None:
        with pytest.raises(SecurityError) as raised:
            split(".a", options=Options())        # the library default is SecurityPolicy.strict()
        assert str(raised.value) == "file operations have been disabled"

    def test_in_place_is_refused(self) -> None:
        with pytest.raises(YqError) as raised:
            split(".a", in_place=True)
        assert str(raised.value) == "write in place cannot be used with split file"

    def test_a_bad_expression(self) -> None:
        with pytest.raises(YqError) as raised:
            split("!!!")
        assert str(raised.value).startswith("bad split document expression:")

    def test_output_format_decides_the_extension(self) -> None:
        options = Options(output_format="json", indent=0, security=SecurityPolicy(allow_file=True))
        fs = split(".a", options=options, output_format="json")
        assert fs.written == {"one.json": '{"a":"one"}\n', "two.json": '{"a":"two"}\n'}

    def test_eval_all(self) -> None:
        fs = split(".", main=".[] | .a", mode=EvalMode.ALL, text="[{a: one}, {a: two}]")
        assert sorted(fs.written) == ["one.yml", "two.yml"]
