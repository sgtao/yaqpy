"""The library side of recipes: yaqpy.apply_recipe / list_recipes / build_recipe."""

from __future__ import annotations

import json

import pytest
import yaqpy
from yaqpy import Options, RecipeError, SecurityPolicy


class ListRecipesTests:
    def test_lists_the_bundled_recipes_by_name(self) -> None:
        recipes = yaqpy.list_recipes()
        assert "openai-to-gemini" in recipes
        assert recipes["openai-to-gemini"].input_api == "openai-chat-completions"

    def test_the_returned_dictionary_is_a_copy(self) -> None:
        yaqpy.list_recipes().clear()
        assert yaqpy.list_recipes()


class ApplyRecipeTests:
    BODY = json.dumps({"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}], "stream": True})

    def test_converts_text_and_reports(self) -> None:
        run = yaqpy.apply_recipe("openai-to-gemini", self.BODY)
        assert json.loads(run.output) == {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        assert (run.input_format, run.output_format, run.document_count) == ("json", "json", 1)
        assert sorted(d.path for d in run.report.dropped) == [".model", ".stream"]
        assert run.report.clean

    def test_a_recipe_object_built_by_the_caller(self) -> None:
        recipe = yaqpy.build_recipe(name="mine", expression='{"n": .a}', metadata="carries: [.a]",
                                    origin="mine")
        run = yaqpy.apply_recipe(recipe, '{"a": 1, "b": 2}', options=Options(indent=0))
        assert json.loads(run.output) == {"n": 1}
        assert [d.path for d in run.report.not_handled] == [".b"]

    def test_output_format_can_be_changed(self) -> None:
        run = yaqpy.apply_recipe("openai-to-gemini", self.BODY, output_format="yaml")
        assert run.output.startswith("contents:\n")

    def test_input_may_be_yaml(self) -> None:
        run = yaqpy.apply_recipe("openai-to-gemini", "model: m\nmessages:\n  - {role: user, content: hi}\n",
                                 input_format="yaml")
        assert json.loads(run.output)["contents"][0]["parts"] == [{"text": "hi"}]

    def test_prune_options(self) -> None:
        recipe = yaqpy.build_recipe(name="p", expression='{"a": null, "b": {}, "c": 1}', metadata=None,
                                    origin="p")
        assert json.loads(yaqpy.apply_recipe(recipe, "{}", prune_null=True).output) == {"b": {}, "c": 1}
        assert json.loads(yaqpy.apply_recipe(recipe, "{}", prune_null=True, prune_empty=True).output) == {"c": 1}

    def test_an_unknown_recipe_and_a_path_are_errors_in_the_library(self) -> None:
        with pytest.raises(RecipeError):
            yaqpy.apply_recipe("no-such", "{}")
        with pytest.raises(RecipeError):
            yaqpy.apply_recipe("./my.yaqpy", "{}")            # the library never reads files

    def test_a_recipe_never_reads_the_environment_even_if_the_options_allow_it(self, monkeypatch) -> None:
        monkeypatch.setenv("YAQPY_API_SECRET", "hunter2")
        recipe = yaqpy.build_recipe(name="spy", expression="env(YAQPY_API_SECRET)", metadata=None, origin="spy")
        allowed = Options(security=SecurityPolicy(allow_env=True, allow_file=True))
        with pytest.raises(yaqpy.SecurityError):
            yaqpy.apply_recipe(recipe, "{}", options=allowed)
