"""配列の演算子（reverse・shuffle・first・filter ほか）。Go 版のシナリオが見ない境界と、エラー文を固定する。"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Any

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


class ReverseTests(unittest.TestCase):
    def test_reverses_and_keeps_the_original(self) -> None:
        self.assertEqual(run("reverse", "[1, 2, 3]"), [3, 2, 1])
        self.assertEqual(run("[.[] | . * 2] | reverse", "[1, 2]"), [4, 2])

    def test_empty_array(self) -> None:
        self.assertEqual(run("reverse", "[]"), [])

    def test_only_arrays(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            run("reverse", "{a: 1}")
        self.assertIn("is not an array (it's a !!map)", str(raised.exception))


class ShuffleTests(unittest.TestCase):
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
        self.assertEqual(sorted(shuffled), [1, 2, 3, 4, 5, 6, 7, 8])

    def test_the_clock_is_the_seed(self) -> None:
        same = [self._shuffle(self._service(7), "[1, 2, 3, 4, 5, 6, 7, 8]") for _ in range(2)]
        self.assertEqual(same[0], same[1])
        others = {tuple(self._shuffle(self._service(s), "[1, 2, 3, 4, 5, 6, 7, 8]"))
                  for s in range(20)}
        self.assertGreater(len(others), 1)

    def test_keys_stay_in_order(self) -> None:
        paths = yaqpy.evaluate("shuffle | .[] | path | .[0]", "[a, b, c, d, e]")
        self.assertEqual(paths.split(), ["0", "1", "2", "3", "4"])

    def test_only_arrays(self) -> None:
        with self.assertRaises(EvaluationError):
            run("shuffle", "a: 1")


class FirstTests(unittest.TestCase):
    def test_without_a_condition_it_is_the_first_child(self) -> None:
        self.assertEqual(run("first", "[7, 8, 9]"), 7)
        # Go 版と同じ：マップでは content[0]（最初のキー）が返る
        self.assertEqual(run("first", "{a: 1, b: 2}"), "a")

    def test_empty_array_gives_nothing(self) -> None:
        self.assertEqual(yaqpy.evaluate("first", "[]"), "")

    def test_no_match_gives_nothing(self) -> None:
        self.assertEqual(yaqpy.evaluate("first(. > 5)", "[1, 2]"), "")

    def test_stops_at_the_first_match(self) -> None:
        self.assertEqual(run("first(. > 1)", "[1, 2, 3]"), 2)


class FilterTests(unittest.TestCase):
    def test_keeps_the_matching_items(self) -> None:
        self.assertEqual(run("filter(. > 1)", "[1, 2, 3]"), [2, 3])

    def test_on_a_map_it_gives_a_list_of_values(self) -> None:
        self.assertEqual(run("filter(. > 1)", "{a: 1, b: 2, c: 3}"), [2, 3])

    def test_nothing_matches(self) -> None:
        self.assertEqual(run("filter(. > 9)", "[1, 2]"), [])


class UniqueTests(unittest.TestCase):
    def test_keeps_the_first_of_each_and_the_order(self) -> None:
        self.assertEqual(run("unique", "[3, 1, 3, 2, 1]"), [3, 1, 2])

    def test_containers_are_compared_by_content(self) -> None:
        self.assertEqual(run("unique", "[{a: 1}, {a: 2}, {a: 1}]"), [{"a": 1}, {"a": 2}])

    def test_unique_by_an_expression(self) -> None:
        text = "[{n: a, v: 1}, {n: b, v: 2}, {n: a, v: 3}]"
        self.assertEqual(run("unique_by(.n)", text), [{"n": "a", "v": 1}, {"n": "b", "v": 2}])

    def test_missing_key_counts_as_null(self) -> None:
        self.assertEqual(run("unique_by(.x)", "[{a: 1}, {a: 2}]"), [{"a": 1}])

    def test_only_arrays(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            run("unique", "a: 1")
        self.assertEqual(str(raised.exception), "only arrays are supported for unique")


class GroupByTests(unittest.TestCase):
    def test_groups_keep_first_appearance_order(self) -> None:
        text = "[{k: b, v: 1}, {k: a, v: 2}, {k: b, v: 3}]"
        self.assertEqual(run("group_by(.k)", text),
                         [[{"k": "b", "v": 1}, {"k": "b", "v": 3}], [{"k": "a", "v": 2}]])

    def test_only_arrays(self) -> None:
        with self.assertRaises(EvaluationError):
            run("group_by(.a)", "a: 1")


class FlattenTests(unittest.TestCase):
    def test_flattens_all_levels(self) -> None:
        self.assertEqual(run("flatten", "[1, [2, [3, [4]]]]"), [1, 2, 3, 4])

    def test_flattens_to_a_depth(self) -> None:
        self.assertEqual(run("flatten(1)", "[1, [2, [3]]]"), [1, 2, [3]])
        self.assertEqual(run("flatten(0)", "[1, [2]]"), [1, [2]])

    def test_only_arrays(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            run("flatten", "a: 1")
        self.assertEqual(str(raised.exception), "only arrays are supported for flatten")


class PivotTests(unittest.TestCase):
    def test_rows_of_different_length_are_padded_with_null(self) -> None:
        self.assertEqual(run("pivot", "[[1, 2, 3], [4]]"), [[1, 4], [2, None], [3, None]])

    def test_maps_become_columns(self) -> None:
        self.assertEqual(run("pivot", "[{a: 1, b: 2}, {b: 3, c: 4}]"),
                         {"a": [1, None], "b": [2, 3], "c": [None, 4]})

    def test_mixed_elements_are_refused(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            run("pivot", "[[1], {a: 1}]")
        self.assertEqual(str(raised.exception),
                         "sequence contains elements of !!seq and !!map types")

    def test_scalars_are_refused(self) -> None:
        with self.assertRaises(EvaluationError) as raised:
            run("pivot", "[1, 2]")
        self.assertIn("can only pivot elements of !!seq or !!map types", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
