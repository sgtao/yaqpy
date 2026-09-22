"""配列の演算子（reverse・shuffle・first・filter ほか）。Go 版のシナリオが見ない境界と、エラー文を固定する。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
import yaqpy
from yaqpy import EvaluationError, Options
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService

JSON = Options(output_format="json", indent=0)


def run(expression: str, text: str, input_format: str = "yaml") -> Any:
    options = Options(input_format=input_format, output_format="json", indent=0)
    out = yaqpy.evaluate(expression, text, options=options)
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    return lines[0] if len(lines) == 1 else lines


class ReverseTests:
    def test_reverses_and_keeps_the_original(self) -> None:
        assert run("reverse", "[1, 2, 3]") == [3, 2, 1]
        assert run("[.[] | . * 2] | reverse", "[1, 2]") == [4, 2]

    def test_empty_array(self) -> None:
        assert run("reverse", "[]") == []

    def test_only_arrays(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("reverse", "{a: 1}")
        assert "is not an array (it's a !!map)" in str(raised.value)


class ShuffleTests:
    def _service(self, seconds: int) -> YqService:
        moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return YqService(InMemoryFileSystem(), StaticEnvironment({}), clock=lambda: moment)

    def _shuffle(self, service: YqService, text: str) -> list[Any]:
        from yaqpy.core.model.convert import to_python
        from yaqpy.formats.yaml.codec import YamlDecoder

        nodes = YamlDecoder(Options()).decode_documents(text, filename="x.yml", file_index=0)
        return to_python(service.evaluate_nodes("shuffle", nodes)[0])

    def test_is_a_permutation(self) -> None:
        shuffled = self._shuffle(self._service(1), "[1, 2, 3, 4, 5, 6, 7, 8]")
        assert sorted(shuffled) == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_the_clock_is_the_seed(self) -> None:
        same = [self._shuffle(self._service(7), "[1, 2, 3, 4, 5, 6, 7, 8]") for _ in range(2)]
        assert same[0] == same[1]
        others = {tuple(self._shuffle(self._service(s), "[1, 2, 3, 4, 5, 6, 7, 8]"))
                  for s in range(20)}
        assert len(others) > 1

    def test_keys_stay_in_order(self) -> None:
        paths = yaqpy.evaluate("shuffle | .[] | path | .[0]", "[a, b, c, d, e]")
        assert paths.split() == ["0", "1", "2", "3", "4"]

    def test_only_arrays(self) -> None:
        with pytest.raises(EvaluationError):
            run("shuffle", "a: 1")


class FirstTests:
    def test_without_a_condition_it_is_the_first_child(self) -> None:
        assert run("first", "[7, 8, 9]") == 7
        # Go 版と同じ：マップでは content[0]（最初のキー）が返る
        assert run("first", "{a: 1, b: 2}") == "a"

    def test_empty_array_gives_nothing(self) -> None:
        assert yaqpy.evaluate("first", "[]") == ""

    def test_no_match_gives_nothing(self) -> None:
        assert yaqpy.evaluate("first(. > 5)", "[1, 2]") == ""

    def test_stops_at_the_first_match(self) -> None:
        assert run("first(. > 1)", "[1, 2, 3]") == 2


class FilterTests:
    def test_keeps_the_matching_items(self) -> None:
        assert run("filter(. > 1)", "[1, 2, 3]") == [2, 3]

    def test_on_a_map_it_gives_a_list_of_values(self) -> None:
        assert run("filter(. > 1)", "{a: 1, b: 2, c: 3}") == [2, 3]

    def test_nothing_matches(self) -> None:
        assert run("filter(. > 9)", "[1, 2]") == []


class UniqueTests:
    def test_keeps_the_first_of_each_and_the_order(self) -> None:
        assert run("unique", "[3, 1, 3, 2, 1]") == [3, 1, 2]

    def test_containers_are_compared_by_content(self) -> None:
        assert run("unique", "[{a: 1}, {a: 2}, {a: 1}]") == [{"a": 1}, {"a": 2}]

    def test_unique_by_an_expression(self) -> None:
        text = "[{n: a, v: 1}, {n: b, v: 2}, {n: a, v: 3}]"
        assert run("unique_by(.n)", text) == [{"n": "a", "v": 1}, {"n": "b", "v": 2}]

    def test_missing_key_counts_as_null(self) -> None:
        assert run("unique_by(.x)", "[{a: 1}, {a: 2}]") == [{"a": 1}]

    def test_only_arrays(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("unique", "a: 1")
        assert str(raised.value) == "only arrays are supported for unique"


class GroupByTests:
    def test_groups_keep_first_appearance_order(self) -> None:
        text = "[{k: b, v: 1}, {k: a, v: 2}, {k: b, v: 3}]"
        assert run("group_by(.k)", text) == [[{"k": "b", "v": 1}, {"k": "b", "v": 3}], [{"k": "a", "v": 2}]]

    def test_only_arrays(self) -> None:
        with pytest.raises(EvaluationError):
            run("group_by(.a)", "a: 1")


class FlattenTests:
    def test_flattens_all_levels(self) -> None:
        assert run("flatten", "[1, [2, [3, [4]]]]") == [1, 2, 3, 4]

    def test_flattens_to_a_depth(self) -> None:
        assert run("flatten(1)", "[1, [2, [3]]]") == [1, 2, [3]]
        assert run("flatten(0)", "[1, [2]]") == [1, [2]]

    def test_only_arrays(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("flatten", "a: 1")
        assert str(raised.value) == "only arrays are supported for flatten"


class PivotTests:
    def test_rows_of_different_length_are_padded_with_null(self) -> None:
        assert run("pivot", "[[1, 2, 3], [4]]") == [[1, 4], [2, None], [3, None]]

    def test_maps_become_columns(self) -> None:
        assert run("pivot", "[{a: 1, b: 2}, {b: 3, c: 4}]") == {"a": [1, None], "b": [2, 3], "c": [None, 4]}

    def test_mixed_elements_are_refused(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("pivot", "[[1], {a: 1}]")
        assert str(raised.value) == "sequence contains elements of !!seq and !!map types"

    def test_scalars_are_refused(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("pivot", "[1, 2]")
        assert "can only pivot elements of !!seq or !!map types" in str(raised.value)


class PickOmitTests:
    def test_pick_keeps_the_order_of_the_request(self) -> None:
        assert list(run('pick(["c", "a"])', "{a: 1, b: 2, c: 3}")) == ["c", "a"]

    def test_pick_ignores_missing_keys(self) -> None:
        assert run('pick(["a", "zzz"])', "{a: 1}") == {"a": 1}

    def test_pick_from_an_array_by_index(self) -> None:
        assert run("pick([2, 0, 9, -1])", "[a, b, c]") == ["c", "a"]

    def test_pick_needs_integer_indices_for_arrays(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run('pick(["x"])', "[a, b]")
        assert str(raised.value) == "cannot index array with x"

    def test_pick_from_a_scalar_is_an_error(self) -> None:
        with pytest.raises(EvaluationError):
            run('pick(["a"])', "3")

    def test_omit_drops_keys_and_indices(self) -> None:
        assert run('omit(["b"])', "{a: 1, b: 2, c: 3}") == {"a": 1, "c": 3}
        assert run("omit([0, 2])", "[a, b, c, d]") == ["b", "d"]

    def test_omit_nothing_or_from_a_scalar_changes_nothing(self) -> None:
        assert run("omit([])", "{a: 1}") == {"a": 1}
        assert run('omit(["a"])', "3") == 3

    def test_paths_are_renumbered_after_omit(self) -> None:
        paths = yaqpy.evaluate("omit([0]) | .[] | path | .[0]", "[a, b, c]")
        assert paths.split() == ["0", "1"]


class SortKeysTests:
    def test_sorts_in_place(self) -> None:
        assert list(run("sort_keys(.)", "{b: 1, a: 2, C: 3}")) == ["C", "a", "b"]

    def test_sorts_a_nested_map_only(self) -> None:
        out = run("sort_keys(.x)", "{z: 1, x: {b: 1, a: 2}}")
        assert list(out) == ["z", "x"]
        assert list(out["x"]) == ["a", "b"]

    def test_deep_with_recursive_descent(self) -> None:
        out = run("sort_keys(..)", "{b: {d: 1, c: 2}, a: 3}")
        assert list(out) == ["a", "b"]
        assert list(out["b"]) == ["c", "d"]


class WithReduceTests:
    def test_with_updates_relative_to_the_path(self) -> None:
        assert run('with(.a; .b = 1 | .c = "x")', "a: {}") == {"a": {"b": 1, "c": "x"}}

    def test_with_needs_a_block(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run(".a |= with(.b)", "a: {b: 1}")
        assert "with must be given a block (;)" in str(raised.value)

    def test_reduce_sums(self) -> None:
        assert run(".[] as $x ireduce (0; . + $x)", "[1, 2, 3, 4]") == 10

    def test_reduce_does_not_leak_its_variable(self) -> None:
        # an unset variable gives no result
        assert yaqpy.evaluate(".[] as $x ireduce (0; . + $x) | $x", "[1, 2]") == ""

    def test_reduce_needs_a_variable_assignment(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run(".[] ireduce (0; . + 1)", "[1]")
        assert "reduce must be given a variables assignment" in str(raised.value)

    def test_array_to_map(self) -> None:
        assert run("array_to_map", "[a, b]") == {"0": "a", "1": "b"}


class ContainsTests:
    def test_string_and_list_and_map(self) -> None:
        assert run('contains("ell")', "hello") is True
        assert run("contains([2, 3])", "[1, 2, 3]") is True
        assert run('contains({"a": 1})', "{a: 1, b: 2}") is True
        assert run('contains({"a": 9})', "{a: 1, b: 2}") is False

    def test_kinds_must_match(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            run("contains([1])", "hello")
        assert str(raised.value) == "!!seq cannot check contained in !!str"

    def test_tags_must_match_for_scalars(self) -> None:
        assert run("contains(1)", "1.0") is False
