"""The comparison of a result with the target's JSON Schema (missing / extra / type / value)."""

from __future__ import annotations

import unittest

from yaqpy.recipes.conform import EXTRA, MISSING, RANGE, SIZE, TYPE, VALUE, check

SCHEMA = {
    "type": "object",
    "required": ["model", "messages"],
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "n": {"type": "integer"},
        "stop": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}, "maxItems": 4}]},
        "messages": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/message"}},
    },
    "$defs": {
        "message": {
            "type": "object",
            "required": ["role", "content"],
            "properties": {
                "role": {"enum": ["system", "user", "assistant"]},
                "content": {"oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "object", "required": ["type"],
                                                "properties": {"type": {"const": "text"}}}},
                ]},
            },
        },
    },
}


def kinds(data: object) -> list[tuple[str, str]]:
    return [(i.path, i.kind) for i in check(data, SCHEMA)]


class ConformTests(unittest.TestCase):
    def test_a_matching_result_has_no_issues(self) -> None:
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "hi"}],
                                "temperature": 0.5, "n": 2, "stop": ["a"]}), [])

    def test_missing_required_keys(self) -> None:
        self.assertEqual(kinds({"messages": [{"role": "user", "content": "x"}]}), [(".model", MISSING)])
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user"}]}),
                         [(".messages[0].content", MISSING)])

    def test_extra_keys_where_the_schema_is_closed(self) -> None:
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "x"}],
                                "max_tokens": 5}), [(".max_tokens", EXTRA)])

    def test_open_objects_allow_extra_keys(self) -> None:
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "x", "name": "n"}]}), [])

    def test_wrong_types(self) -> None:
        self.assertEqual(kinds({"model": 5, "messages": [{"role": "user", "content": "x"}]}),
                         [(".model", TYPE)])
        self.assertEqual(kinds({"model": "m", "messages": "hi"}), [(".messages", TYPE)])

    def test_booleans_are_not_numbers_and_whole_floats_are_integers(self) -> None:
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": True}),
                         [(".n", TYPE)])
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": 2.0}), [])
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": 2.5}),
                         [(".n", TYPE)])

    def test_values_range_and_size(self) -> None:
        base = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
        self.assertEqual(kinds({**base, "temperature": 3}), [(".temperature", RANGE)])
        self.assertEqual(kinds({**base, "messages": []}), [(".messages", SIZE)])
        self.assertEqual(kinds({**base, "stop": list("abcde")}), [(".stop", SIZE)])
        self.assertEqual(kinds({"model": "m", "messages": [{"role": "model", "content": "x"}]}),
                         [(".messages[0].role", VALUE)])

    def test_the_closest_alternative_explains_a_mismatch(self) -> None:
        got = check({"model": "m", "messages": [{"role": "user", "content": [{"type": "image"}]}]}, SCHEMA)
        self.assertEqual([(i.path, i.kind) for i in got], [(".messages[0].content[0].type", VALUE)])

    def test_a_type_list_and_null(self) -> None:
        schema = {"type": ["string", "null"]}
        self.assertEqual(check(None, schema), [])
        self.assertEqual(check("a", schema), [])
        self.assertEqual([i.kind for i in check(1, schema)], [TYPE])

    def test_unknown_references_are_ignored_not_fatal(self) -> None:
        self.assertEqual(check({"a": 1}, {"properties": {"a": {"$ref": "https://example.com/x"}}}), [])
        self.assertEqual(check({"a": 1}, {"properties": {"a": {"$ref": "#/$defs/none"}}}), [])

    def test_a_reference_loop_stops(self) -> None:
        schema = {"$defs": {"a": {"$ref": "#/$defs/a"}}, "properties": {"x": {"$ref": "#/$defs/a"}}}
        self.assertEqual(check({"x": 1}, schema), [])

    def test_str_of_an_issue_names_the_path(self) -> None:
        (issue,) = check({"messages": [{"role": "user", "content": "x"}]}, SCHEMA)
        self.assertEqual(str(issue), ".model: required, but the result has no such key")


if __name__ == "__main__":
    unittest.main()
