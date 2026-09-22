"""The report of a conversion: declared drops, unhandled input, added items, issues."""

from __future__ import annotations

from yaqpy.recipes import AddRule, DropRule, Recipe
from yaqpy.recipes.analysis import NOT_HANDLED, analyse

SOURCE = {
    "model": "gpt-4o",
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "image_url", "image_url": {}}]},
        {"role": "assistant", "content": "b", "tool_calls": [{"id": "x"}]},
    ],
    "stream": True,
    "mystery": 1,
}
RESULT = {"contents": [{"role": "user", "parts": [{"text": "a"}]}], "max_tokens": 4096}


def recipe(**kw) -> Recipe:
    defaults = dict(
        name="r", expression=".",
        carries=(".messages",),
        drops=(DropRule(".model", "goes in the URL"), DropRule(".stream", "other endpoint"),
               DropRule(".messages[].content[type!=text]", "text only"),
               DropRule(".messages[].tool_calls", "history is not converted"),
               DropRule(".not_there", "never in the input")),
    )
    defaults.update(kw)
    return Recipe(**defaults)


class DroppedTests:
    def test_declared_drops_are_listed_only_when_the_input_has_them(self) -> None:
        report = analyse(recipe(), SOURCE, RESULT)
        declared = {d.path: d for d in report.dropped if d.declared}
        assert sorted(declared) == [".messages[].content[type!=text]", ".messages[].tool_calls",
                                  ".model", ".stream"]
        assert declared[".model"].reason == "goes in the URL"
        assert declared[".messages[].content[type!=text]"].where == (".messages[0].content[1]",)

    def test_what_neither_carries_nor_drops_mention_is_not_handled(self) -> None:
        report = analyse(recipe(), SOURCE, RESULT)
        assert [(d.path, d.reason) for d in report.not_handled] == [(".mystery", NOT_HANDLED)]
        assert not report.clean

    def test_a_recipe_without_carries_or_drops_is_not_checked_for_them(self) -> None:
        report = analyse(Recipe(name="bare", expression="."), SOURCE, RESULT)
        assert (report.dropped, report.checked_drops) == ((), False)


class AddedTests:
    ADDS = (AddRule(".max_tokens", "required by the target", unless=(".max_tokens", ".max_completion_tokens")),)

    def test_reported_when_the_input_gave_nothing(self) -> None:
        report = analyse(recipe(adds=self.ADDS), SOURCE, RESULT)
        assert [(a.path, a.value, a.reason) for a in report.added] == [(".max_tokens", 4096, "required by the target")]

    def test_not_reported_when_the_input_gave_the_value(self) -> None:
        source = {**SOURCE, "max_completion_tokens": 4096}
        assert analyse(recipe(adds=self.ADDS), source, RESULT).added == ()


class SchemaAndChangesTests:
    def test_issues_come_from_the_target_schema(self) -> None:
        schema = {"type": "object", "required": ["contents", "model"], "additionalProperties": False,
                  "properties": {"contents": {"type": "array"}}}
        report = analyse(recipe(target_schema=schema), SOURCE, RESULT)
        assert [(i.path, i.kind) for i in report.issues] == [(".model", "missing"), (".max_tokens", "extra")]
        assert report.checked_schema

    def test_no_schema_no_issues(self) -> None:
        report = analyse(recipe(), SOURCE, RESULT)
        assert (report.issues, report.checked_schema) == ((), False)

    def test_changes_are_the_document_difference(self) -> None:
        report = analyse(recipe(), {"a": 1, "b": 2}, {"a": 1, "c": 3})
        assert [(c.kind, c.path) for c in report.changes] == [("removed", ".b"), ("added", ".c")]

    def test_a_clean_report(self) -> None:
        source = {"model": "m", "messages": []}
        report = analyse(recipe(), source, {"contents": []})
        assert report.clean

    def test_extra_documents_are_noted(self) -> None:
        report = analyse(recipe(), SOURCE, RESULT, extra_documents=2)
        assert len(report.notes) == 1
        assert "2 more document(s)" in report.notes[0]
