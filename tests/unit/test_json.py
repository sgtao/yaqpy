"""JSON の読み取りの回帰テスト：空のオブジェクト ``{}`` と空の配列 ``[]`` を取り違えない。"""

from __future__ import annotations

import json

import yaqpy
from yaqpy import Options


def run(text: str, output_format: str = "json") -> str:
    return yaqpy.evaluate(".", text, options=Options(input_format="json", output_format=output_format,
                                                     indent=0))


class EmptyContainerTests:
    def test_empty_object_stays_an_object(self) -> None:
        assert run("{}") == "{}\n"

    def test_empty_array_stays_an_array(self) -> None:
        assert run("[]") == "[]\n"

    def test_nested_empty_containers(self) -> None:
        text = '{"a":{},"b":[],"c":[{}],"d":[[]],"e":{"x":[1,{"y":{}}]}}'
        assert json.loads(run(text)) == json.loads(text)

    def test_yaml_output(self) -> None:
        assert run('{"a":{},"b":[]}', "yaml") == "a: {}\nb: []\n"

    def test_the_kind_is_right(self) -> None:
        options = Options(input_format="json", output_format="yaml")
        assert yaqpy.evaluate("kind", "{}", options=options) == "map\n"
        assert yaqpy.evaluate("kind", "[]", options=options) == "seq\n"
        assert yaqpy.evaluate('.a | kind', '{"a":{}}', options=options) == "map\n"

    def test_object_with_keys_is_unchanged(self) -> None:
        assert json.loads(run('{"a":1,"b":[1,2],"c":{"d":null}}')) == {"a": 1, "b": [1, 2], "c": {"d": None}}
