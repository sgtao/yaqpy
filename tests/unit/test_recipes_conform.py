"""The comparison of a result with the target's JSON Schema (missing / extra / type / value)."""

from __future__ import annotations

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


class ConformTests:
    def test_a_matching_result_has_no_issues(self) -> None:
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "hi"}],
                      "temperature": 0.5, "n": 2, "stop": ["a"]}) == []

    def test_missing_required_keys(self) -> None:
        assert kinds({"messages": [{"role": "user", "content": "x"}]}) == [(".model", MISSING)]
        assert kinds({"model": "m", "messages": [{"role": "user"}]}) == [(".messages[0].content", MISSING)]

    def test_extra_keys_where_the_schema_is_closed(self) -> None:
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "x"}],
                      "max_tokens": 5}) == [(".max_tokens", EXTRA)]

    def test_open_objects_allow_extra_keys(self) -> None:
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "x", "name": "n"}]}) == []

    def test_wrong_types(self) -> None:
        assert kinds({"model": 5, "messages": [{"role": "user", "content": "x"}]}) == [(".model", TYPE)]
        assert kinds({"model": "m", "messages": "hi"}) == [(".messages", TYPE)]

    def test_booleans_are_not_numbers_and_whole_floats_are_integers(self) -> None:
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": True}) == [(".n", TYPE)]
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": 2.0}) == []
        assert kinds({"model": "m", "messages": [{"role": "user", "content": "x"}], "n": 2.5}) == [(".n", TYPE)]

    def test_values_range_and_size(self) -> None:
        base = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
        assert kinds({**base, "temperature": 3}) == [(".temperature", RANGE)]
        assert kinds({**base, "messages": []}) == [(".messages", SIZE)]
        assert kinds({**base, "stop": list("abcde")}) == [(".stop", SIZE)]
        assert kinds({"model": "m", "messages": [{"role": "model", "content": "x"}]}) == [(".messages[0].role", VALUE)]

    def test_the_closest_alternative_explains_a_mismatch(self) -> None:
        got = check({"model": "m", "messages": [{"role": "user", "content": [{"type": "image"}]}]}, SCHEMA)
        assert [(i.path, i.kind) for i in got] == [(".messages[0].content[0].type", VALUE)]

    def test_a_type_list_and_null(self) -> None:
        schema = {"type": ["string", "null"]}
        assert check(None, schema) == []
        assert check("a", schema) == []
        assert [i.kind for i in check(1, schema)] == [TYPE]

    def test_unknown_references_are_ignored_not_fatal(self) -> None:
        assert check({"a": 1}, {"properties": {"a": {"$ref": "https://example.com/x"}}}) == []
        assert check({"a": 1}, {"properties": {"a": {"$ref": "#/$defs/none"}}}) == []

    def test_a_reference_loop_stops(self) -> None:
        schema = {"$defs": {"a": {"$ref": "#/$defs/a"}}, "properties": {"x": {"$ref": "#/$defs/a"}}}
        assert check({"x": 1}, schema) == []

    def test_str_of_an_issue_names_the_path(self) -> None:
        (issue,) = check({"messages": [{"role": "user", "content": "x"}]}, SCHEMA)
        assert str(issue) == ".model: required, but the result has no such key"
