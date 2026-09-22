"""prune_null / prune_empty (yaqpy extensions): what goes, what stays, and where they aim."""

from __future__ import annotations

import json
from typing import Any

import yaqpy
from yaqpy import Options


def run(expression: str, text: str) -> Any:
    options = Options(input_format="json", output_format="json", indent=0)
    return json.loads(yaqpy.evaluate(expression, text, options=options))


class PruneNullTests:
    def test_removes_null_map_values_at_every_depth(self) -> None:
        got = run("prune_null", '{"a": null, "b": {"c": null, "d": 1}, "e": [{"f": null, "g": 2}]}')
        assert got == {"b": {"d": 1}, "e": [{"g": 2}]}

    def test_keeps_sequence_items_because_positions_matter(self) -> None:
        assert run("prune_null", '{"a": [null, 1, null]}') == {"a": [None, 1, None]}

    def test_keeps_false_zero_and_empty_string(self) -> None:
        got = run("prune_null", '{"a": false, "b": 0, "c": "", "d": null}')
        assert got == {"a": False, "b": 0, "c": ""}

    def test_keeps_empty_containers(self) -> None:
        assert run("prune_null", '{"a": {}, "b": []}') == {"a": {}, "b": []}

    def test_can_be_aimed_at_one_part(self) -> None:
        text = '{"cfg": {"t": null, "p": 1}, "schema": {"default": null}}'
        assert run(".cfg | prune_null | parent", text) == {"cfg": {"p": 1}, "schema": {"default": None}}

    def test_name_without_underscore_is_accepted(self) -> None:
        assert run("prunenull", '{"a": null}') == {}


class PruneEmptyTests:
    def test_removes_empty_maps_and_arrays(self) -> None:
        assert run("prune_empty", '{"a": {}, "b": [], "c": 1}') == {"c": 1}

    def test_cascades_from_the_inside_out(self) -> None:
        assert run("prune_empty", '{"a": {"b": {"c": {}}}, "d": 1}') == {"d": 1}

    def test_keeps_the_root_even_when_it_ends_up_empty(self) -> None:
        assert run("prune_empty", '{"a": {}}') == {}

    def test_keeps_null_and_empty_strings(self) -> None:
        assert run("prune_empty", '{"a": null, "b": ""}') == {"a": None, "b": ""}

    def test_does_not_remove_empty_items_of_a_sequence(self) -> None:
        assert run("prune_empty", '{"a": [{}, 1]}') == {"a": [{}, 1]}

    def test_null_then_empty_cleans_a_conversion_leftover(self) -> None:
        got = run("prune_null | prune_empty", '{"generationConfig": {"temperature": null}, "x": 1}')
        assert got == {"x": 1}
