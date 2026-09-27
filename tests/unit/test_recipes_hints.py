"""``hints:`` in a recipe's metadata (v0.7.2): advice shown when the result does not fit the target.

The advice lives with the recipe (the ``.recipe.yaml`` next to the ``.yaqpy``), so a recipe of your
own can carry it too; the code only picks the hints whose ``when`` fits an issue.
"""

from __future__ import annotations

import io

import pytest
from yaqpy.cli.main import main
from yaqpy.errors import RecipeError
from yaqpy.recipes import build_recipe, find_builtin
from yaqpy.recipes.conform import EXTRA, ISSUE_KINDS, MISSING, TYPE, Issue
from yaqpy.recipes.hints import applies, hints_for
from yaqpy.recipes.model import HintRule


def recipe_with(hints_yaml: str):
    return build_recipe(name="demo", expression=".", origin="demo.recipe.yaml",
                        metadata="name: demo\n" + hints_yaml)


class ParseTests:
    def test_a_hint_has_a_when_and_a_text(self) -> None:
        recipe = recipe_with("hints:\n  - when: {issue: missing, path: .model}\n    text: add a model\n")
        assert recipe.hints == (HintRule("add a model", "missing", ".model"),)

    def test_when_may_be_left_out_and_then_the_hint_fits_every_issue(self) -> None:
        recipe = recipe_with("hints:\n  - text: check the target\n")
        assert recipe.hints == (HintRule("check the target"),)

    def test_a_hint_can_be_about_a_declared_drop(self) -> None:
        recipe = recipe_with("hints:\n  - when: {dropped: .model}\n    text: put it in the URL\n")
        assert recipe.hints == (HintRule("put it in the URL", dropped=".model"),)

    def test_no_hints_by_default(self) -> None:
        assert recipe_with("").hints == ()

    @pytest.mark.parametrize("yaml, fragment", [
        ("hints: nope\n", "'hints' must be a list of mappings"),
        ("hints:\n  - when: {issue: missing}\n", "needs a 'text'"),
        ("hints:\n  - text: ''\n", "needs a 'text'"),
        ("hints:\n  - text: a\n    why: b\n", "unknown key in hint 1: why"),
        ("hints:\n  - when: {issue: missing, kind: x}\n    text: a\n", "'when' of hint 1 takes"),
        ("hints:\n  - when: {dropped: .a, issue: missing}\n    text: a\n", "'dropped' cannot go with"),
        ("hints:\n  - when: {dropped: a}\n    text: a\n", "'hints': a path pattern starts with"),
        ("hints:\n  - when: {dropped: [.a]}\n    text: a\n", "'dropped' of hint 1 must be a path"),
        ("hints:\n  - when: {issue: gone}\n    text: a\n", "is one of missing, extra, type"),
        ("hints:\n  - when: {path: model}\n    text: a\n", "'path' of hint 1 is like"),
        ("hints:\n  - when: {path: '.a[0]'}\n    text: a\n", "'path' of hint 1 is like"),
    ])
    def test_mistakes_are_errors_not_silently_ignored(self, yaml: str, fragment: str) -> None:
        with pytest.raises(RecipeError) as error:
            recipe_with(yaml)
        assert fragment in str(error.value)

    def test_every_issue_kind_can_be_named(self) -> None:
        for kind in ISSUE_KINDS:
            assert recipe_with(f"hints:\n  - when: {{issue: {kind}}}\n    text: a\n").hints[0].issue == kind


class MatchTests:
    def test_the_issue_kind_narrows_it(self) -> None:
        rule = HintRule("t", issue=MISSING)
        assert applies(rule, Issue(".a", MISSING, "m"))
        assert not applies(rule, Issue(".a", EXTRA, "m"))

    def test_the_path_must_match_exactly(self) -> None:
        rule = HintRule("t", path=".model")
        assert applies(rule, Issue(".model", MISSING, "m"))
        assert not applies(rule, Issue(".models", MISSING, "m"))
        assert not applies(rule, Issue(".a.model", MISSING, "m"))

    def test_brackets_stand_for_any_list_position(self) -> None:
        rule = HintRule("t", path=".messages[].role")
        assert applies(rule, Issue(".messages[0].role", TYPE, "m"))
        assert applies(rule, Issue(".messages[12].role", TYPE, "m"))
        assert not applies(rule, Issue(".messages.role", TYPE, "m"))
        assert not applies(rule, Issue(".messages[0].content", TYPE, "m"))

    def test_a_path_with_dots_is_not_a_regular_expression(self) -> None:
        assert not applies(HintRule("t", path=".a.b"), Issue(".axb", MISSING, "m"))


class TextTests:
    def make(self):
        return recipe_with("hints:\n  - when: {issue: missing}\n"
                           "    text: 'run {recipe} on {input}: fill {path}'\n")

    def test_the_placeholders_are_filled(self) -> None:
        texts = hints_for(self.make(), [Issue(".model", MISSING, "m")], input_name="a.json")
        assert texts == ["run demo on a.json: fill .model"]

    def test_a_name_with_a_space_is_quoted(self) -> None:
        texts = hints_for(self.make(), [Issue(".model", MISSING, "m")], input_name="my file.json")
        assert texts == ['run demo on "my file.json": fill .model']

    def test_braces_that_are_not_placeholders_are_left_alone(self) -> None:
        recipe = recipe_with("hints:\n  - text: 'send {\"a\": 1} for {path}'\n")
        assert hints_for(recipe, [Issue(".x", MISSING, "m")], input_name="-") == ['send {"a": 1} for .x']

    def test_one_hint_for_several_issues_it_fits_is_shown_per_distinct_text(self) -> None:
        issues = [Issue(".a", MISSING, "m"), Issue(".b", MISSING, "m")]
        assert hints_for(self.make(), issues, input_name="-") == ["run demo on -: fill .a",
                                                                   "run demo on -: fill .b"]
        no_path = recipe_with("hints:\n  - text: same for all\n")
        assert hints_for(no_path, issues, input_name="-") == ["same for all"]

    def test_no_issue_no_hint(self) -> None:
        assert hints_for(self.make(), [], input_name="-") == []

    def test_a_dropped_hint_fits_only_a_drop_never_an_issue(self) -> None:
        recipe = recipe_with("hints:\n  - when: {dropped: .model}\n    text: 'the model went: {path}'\n")
        issues = [Issue(".model", MISSING, "m")]
        assert hints_for(recipe, issues, input_name="-") == []
        assert hints_for(recipe, [], input_name="-", dropped=[".model"]) == ["the model went: .model"]
        assert hints_for(recipe, [], input_name="-", dropped=[".n"]) == []

    def test_an_issue_hint_never_fits_a_drop(self) -> None:
        recipe = recipe_with("hints:\n  - text: any issue\n")
        assert hints_for(recipe, [], input_name="-", dropped=[".model"]) == []


class BuiltinTests:
    """The four recipes that write to an API that requires a model say how to add one."""

    @pytest.mark.parametrize("name, example", [
        ("anthropic-to-openai", "gpt-4o"), ("gemini-to-openai", "gpt-4o"),
        ("openai-to-anthropic", "claude-opus-5-5"), ("gemini-to-anthropic", "claude-opus-5-5"),
    ])
    def test_a_missing_model_has_a_hint_with_a_model_that_fits_the_target(
            self, name: str, example: str) -> None:
        recipe = find_builtin(name)
        texts = hints_for(recipe, [Issue(".model", MISSING, "m")], input_name="req.json")
        assert texts == [f"the recipe does not choose a model. Add yours after the conversion, e.g. "
                         f"yaqpy --recipe {name} req.json | yaqpy '.model = \"{example}\"'"]

    @pytest.mark.parametrize("name", ["openai-to-gemini", "anthropic-to-gemini"])
    def test_gemini_takes_the_model_in_the_url_and_the_dropped_model_says_so(self, name: str) -> None:
        recipe = find_builtin(name)
        assert recipe.hints == (HintRule(
            "Gemini takes the model in the URL, not in the body: POST "
            "https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent "
            "(for example gemini-2.5-flash).", dropped=".model"),)
        assert hints_for(recipe, [], input_name="a.json", dropped=[".model"]) == [recipe.hints[0].text]

    @pytest.mark.parametrize("name", ["openai-to-gemini", "anthropic-to-gemini"])
    def test_no_hint_about_the_url_when_the_input_had_no_model(self, name: str) -> None:
        assert hints_for(find_builtin(name), [], input_name="a.json", dropped=[".stream"]) == []


class OwnRecipeTests:
    """A recipe of your own gets the same behaviour, with no help from the code."""

    def test_the_hint_of_a_recipe_file_is_printed(self, tmp_path) -> None:
        (tmp_path / "mine.yaqpy").write_bytes(b'{"out": .text}\n')
        (tmp_path / "mine.recipe.yaml").write_bytes(
            b"name: mine\n"
            b"target_schema: {type: object, required: [id]}\n"
            b"hints:\n"
            b"  - when: {issue: missing, path: .id}\n"
            b"    text: 'add an id: yaqpy --recipe {recipe} {input} | yaqpy ''.id = 1'''\n")
        source = tmp_path / "in.json"
        source.write_bytes(b'{"text": "hi"}')
        out, err = io.StringIO(), io.StringIO()
        code = main(["--recipe", str(tmp_path / "mine.yaqpy"), str(source)], stdout=out, stderr=err)
        assert code == 0
        assert ".id: required, but the result has no such key" in err.getvalue()
        assert f"  hint: add an id: yaqpy --recipe mine {source} | yaqpy '.id = 1'\n" in err.getvalue()
