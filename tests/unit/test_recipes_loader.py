"""Recipe metadata: path patterns, and reading a recipe with its metadata."""

from __future__ import annotations

import json

import pytest
from yaqpy.errors import RecipeError
from yaqpy.recipes import build_recipe
from yaqpy.recipes.paths import find_matches, find_unlisted, parse_pattern

DATA = {
    "model": "m",
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {}}]},
        {"role": "assistant", "content": "b", "tool_calls": []},
    ],
    "stream": True,
    "generationConfig": {"temperature": 1, "topK": 3},
}


class PathPatternTests:
    def matches(self, pattern: str) -> list[str]:
        return find_matches(DATA, parse_pattern(pattern))

    def test_keys_and_any_item(self) -> None:
        assert self.matches(".model") == [".model"]
        assert self.matches(".messages[].role") == [".messages[0].role", ".messages[1].role"]

    def test_a_key_that_is_absent_matches_nothing(self) -> None:
        assert self.matches(".messages[].name") == []
        assert self.matches(".nothing.here") == []

    def test_filter_equal_and_not_equal(self) -> None:
        assert self.matches(".messages[].content[type=text].text") == [".messages[0].content[0].text"]
        assert self.matches(".messages[].content[type!=text]") == [".messages[0].content[1]"]

    def test_not_equal_counts_a_missing_key_as_different(self) -> None:
        assert find_matches({"x": [{"a": 1}, {"b": 2}]}, parse_pattern(".x[a!=1]")) == [".x[1]"]

    def test_the_root(self) -> None:
        assert find_matches(DATA, parse_pattern(".")) == ["."]

    def test_bad_patterns(self) -> None:
        for bad in ("a.b", ".a[", ".a[oops]", ".a..b"):
            with pytest.raises(ValueError):
                parse_pattern(bad)


class UnlistedTests:
    def unlisted(self, *patterns: str) -> list[str]:
        return find_unlisted(DATA, [parse_pattern(p) for p in patterns])

    def test_reports_the_top_most_uncovered_path(self) -> None:
        assert self.unlisted(".model", ".messages", ".generationConfig.temperature") == [".stream", ".generationConfig.topK"]

    def test_a_listed_path_covers_everything_below_it(self) -> None:
        assert self.unlisted(".model", ".messages", ".stream", ".generationConfig") == []

    def test_a_declared_drop_counts_as_listed(self) -> None:
        assert self.unlisted(".model", ".messages", ".stream", ".generationConfig.temperature",
                             ".generationConfig.topK") == []

    def test_the_beginning_of_a_longer_pattern_lets_the_walk_go_on(self) -> None:
        assert self.unlisted(".model", ".messages", ".stream", ".generationConfig.temperature") == [".generationConfig.topK"]


class BuildRecipeTests:
    def build(self, metadata: str | None, expression: str | None = ".a", **kw) -> object:
        return build_recipe(name="r", expression=expression, metadata=metadata, origin="test", **kw)

    def test_an_expression_alone_is_a_recipe(self) -> None:
        recipe = self.build(None, ".a\r\n| .b")
        assert (recipe.name, recipe.expression, recipe.input_format, recipe.can_report_drops) == ("r", ".a\n| .b", "json", False)

    def test_full_metadata(self) -> None:
        recipe = self.build("""
name: full
title: Full
description: d
input: {format: yaml, api: a}
output: {format: json, api: b}
prune: [nulls, empties]
carries: [.a, ".b[]"]
drops:
  - {path: .c, reason: not needed}
adds:
  - {path: .d, reason: required, unless: [.d, .e]}
notes: [n1]
tests:
  - {name: t, input: {a: 1}, expected: {b: 1}}
""")
        assert (recipe.name, recipe.input_format, recipe.output_format, recipe.prune) == ("full", "yaml", "json", ("nulls", "empties"))
        assert recipe.carries == (".a", ".b[]")
        assert (recipe.drops[0].path, recipe.drops[0].reason) == (".c", "not needed")
        assert recipe.adds[0].unless == (".d", ".e")
        assert (recipe.tests[0].name, recipe.tests[0].input, recipe.tests[0].expected) == ("t", {"a": 1}, {"b": 1})
        assert recipe.can_report_drops

    def test_the_target_schema_can_be_a_file_next_to_the_recipe(self) -> None:
        recipe = self.build("target_schema: s.json", read_related=lambda name: json.dumps({"type": "object", "n": name}))
        assert recipe.target_schema == {"type": "object", "n": "s.json"}

    def test_the_target_schema_can_be_inline(self) -> None:
        recipe = self.build("target_schema: {type: object}")
        assert recipe.target_schema == {"type": "object"}

    def test_a_metadata_only_recipe_reads_its_expression_from_the_metadata(self) -> None:
        assert self.build("expression: .x | .y", expression=None).expression == ".x | .y"
        recipe = self.build("expression_file: e.yaqpy", expression=None, read_related=lambda name: ".from " + name)
        assert recipe.expression == ".from e.yaqpy"

    def assertRejected(self, metadata: str, fragment: str) -> None:
        with pytest.raises(RecipeError) as raised:
            self.build(metadata)
        assert fragment in str(raised.value)

    def test_typos_and_bad_shapes_are_errors_not_silently_ignored(self) -> None:
        self.assertRejected("drop: []", "unknown key in the metadata: drop")
        self.assertRejected("prune: [null]", "'prune' must be a list of text")
        self.assertRejected("prune: [null_]", "'prune' takes nulls and empties")
        self.assertRejected("carries: .a", "'carries' must be a list")
        self.assertRejected("drops: [{reason: x}]", "needs a 'path'")
        self.assertRejected("drops: [{path: a}]", "starts with '.'")
        self.assertRejected("tests: [{input: {}}]", "needs 'input' and 'expected'")
        self.assertRejected("input: {formatt: json}", "unknown key in 'input'")
        self.assertRejected("version: one", "'version' must be an integer")
        self.assertRejected("- a", "must be a mapping")
        self.assertRejected("a: [", "cannot read the metadata")

    def test_no_expression_anywhere(self) -> None:
        with pytest.raises(RecipeError):
            self.build("name: x", expression=None)
