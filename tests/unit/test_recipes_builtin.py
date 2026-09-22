"""The bundled recipes: their own cases, the target schemas, the metadata's completeness, and
round trips between the three APIs (what one recipe writes, the opposite recipe must read back)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
import yaqpy
from yaqpy import Options
from yaqpy.app.dto import InputSource
from yaqpy.app.local import LocalEnvironment, LocalFileSystem
from yaqpy.app.recipe_service import RecipeService
from yaqpy.app.service import YqService
from yaqpy.cli.main import main
from yaqpy.recipes import builtin_recipes
from yaqpy.recipes.conform import check

NAMES = ["anthropic-to-gemini", "anthropic-to-openai", "gemini-to-anthropic", "gemini-to-openai",
         "openai-to-anthropic", "openai-to-gemini"]
JSON = Options(input_format="json", output_format="json", indent=0)
SERVICE = RecipeService(YqService(LocalFileSystem(), LocalEnvironment()))


def convert(name: str, doc: Any) -> Any:
    return json.loads(yaqpy.evaluate(builtin_recipes()[name].expression, json.dumps(doc), options=JSON))


def cases(api: str) -> list[Any]:
    """The test inputs of the bundled recipes that read ``api``."""
    for recipe in builtin_recipes().values():
        if recipe.input_api == api:
            return [t.input for t in recipe.tests]
    raise AssertionError(api)


class CatalogTests:
    def test_the_six_recipes_are_there(self) -> None:
        assert sorted(builtin_recipes()) == NAMES

    @pytest.mark.parametrize("name, recipe", builtin_recipes().items())
    def test_each_recipe_is_described_and_carries_five_cases(self, name, recipe) -> None:
        assert recipe.name == name
        assert recipe.title and recipe.description and recipe.notes
        assert name == recipe.input_api.split("-")[0] + "-to-" + recipe.output_api.split("-")[0]
        assert len(recipe.tests) == 5
        assert recipe.carries and recipe.drops
        assert recipe.target_schema is not None

    def test_the_schemas_of_a_target_are_the_same_for_every_recipe_that_writes_it(self) -> None:
        by_target: dict[str, list[Any]] = {}
        for recipe in builtin_recipes().values():
            by_target.setdefault(recipe.output_api, []).append(recipe.target_schema)
        for api, schemas in by_target.items():
            assert all(s == schemas[0] for s in schemas)


class OwnCaseTests:
    def test_every_case_of_every_recipe_passes(self) -> None:
        for name, recipe in builtin_recipes().items():
            for result in SERVICE.run_tests(recipe):
                assert result.passed, result.message

    def test_converting_does_not_change_the_input_and_gives_the_same_result_again(self) -> None:
        for name, recipe in builtin_recipes().items():
            for case in recipe.tests:
                original = json.dumps(case.input, sort_keys=True)
                first = convert(name, case.input)
                assert json.dumps(case.input, sort_keys=True) == original
                assert convert(name, case.input) == first


class SchemaTests:
    """The test inputs are what the source API accepts; the outputs are what the target accepts."""

    def test_the_inputs_follow_the_schema_of_the_api_they_are_written_for(self) -> None:
        schema_of = {r.output_api: r.target_schema for r in builtin_recipes().values()}
        for name, recipe in builtin_recipes().items():
            for case in recipe.tests:
                assert check(case.input, schema_of[recipe.input_api]) == []

    def test_the_outputs_follow_the_target_schema_except_for_the_model_that_is_never_converted(self) -> None:
        for name, recipe in builtin_recipes().items():
            for case in recipe.tests:
                issues = [(i.path, i.kind) for i in check(convert(name, case.input), recipe.target_schema)]
                assert set(issues) <= {(".model", "missing")}

    def test_a_result_that_does_not_fit_the_target_is_told(self) -> None:
        recipe = builtin_recipes()["openai-to-anthropic"]
        broken = {"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": "many",
                  "stop": ["a"]}
        assert {(i.path, i.kind) for i in check(broken, recipe.target_schema)} == {(".max_tokens", "type"), (".stop", "extra")}


class CompletenessTests:
    """Nothing in a test input is lost without the recipe saying so."""

    def test_every_key_of_every_test_input_is_carried_or_declared_dropped(self) -> None:
        for name, recipe in builtin_recipes().items():
            for case in recipe.tests:
                run = SERVICE.run(recipe, InputSource("<text>", json.dumps(case.input)), Options(),
                                  input_format="json", output_format="json")
                assert [d.path for d in run.report.not_handled] == []

    def test_a_declared_drop_is_really_absent_from_the_output(self) -> None:
        doc = {"model": "m", "stream": True, "user": "u", "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "x"}}],
             "name": "bob"}]}
        text = json.dumps(convert("openai-to-gemini", doc))
        for leaked in ("gpt", "image", "bob", '"stream"', '"user": "u"'):
            assert leaked not in text
        assert '"text": "hi"' in text

    def test_the_default_max_tokens_is_reported_and_only_when_it_was_added(self) -> None:
        recipe = builtin_recipes()["openai-to-anthropic"]

        def added(doc: dict[str, Any]) -> list[str]:
            run = SERVICE.run(recipe, InputSource("<text>", json.dumps(doc)), Options(),
                              input_format="json", output_format="json")
            return [a.path for a in run.report.added]

        messages = [{"role": "user", "content": "x"}]
        assert added({"model": "m", "messages": messages}) == [".max_tokens"]
        assert added({"model": "m", "messages": messages, "max_tokens": 9}) == []
        assert added({"model": "m", "messages": messages, "max_completion_tokens": 9}) == []


# ----------------------------------------------------------------------------- round trips

def _texts(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    return [p["text"] for p in content or [] if p.get("type", "text") == "text" and "text" in p]


EMPTY_SCHEMA = {"type": "object", "properties": {}}    # what "no parameters" is, where a schema is required


def _params(**found: Any) -> dict[str, Any]:
    return {k: v for k, v in found.items() if v is not None}


def canon_openai(doc: dict[str, Any]) -> dict[str, Any]:
    messages = doc["messages"]
    stop = doc.get("stop")
    choice = doc.get("tool_choice")
    return {
        "system": [t for m in messages if m["role"] in ("system", "developer") for t in _texts(m["content"])],
        "turns": [(m["role"], _texts(m["content"])) for m in messages if m["role"] in ("user", "assistant")],
        "params": _params(temperature=doc.get("temperature"), top_p=doc.get("top_p"),
                          max_tokens=doc.get("max_completion_tokens", doc.get("max_tokens")),
                          stop=[stop] if isinstance(stop, str) else stop),
        "tools": [(t["function"]["name"], t["function"].get("description"), t["function"].get("parameters", EMPTY_SCHEMA))
                  for t in doc.get("tools", [])],
        "tool_choice": {"auto": ("auto",), "none": ("none",), "required": ("any",), None: None}.get(choice)
        if not isinstance(choice, dict) else ("tool", choice["function"]["name"]),
    }


def canon_gemini(doc: dict[str, Any]) -> dict[str, Any]:
    config = doc.get("generationConfig", {})
    calling = doc.get("toolConfig", {}).get("functionCallingConfig", {})
    names = calling.get("allowedFunctionNames", [])
    mode = calling.get("mode")
    choice = None if mode is None else ("tool", names[0]) if mode == "ANY" and len(names) == 1 \
        else {"AUTO": ("auto",), "NONE": ("none",), "ANY": ("any",)}[mode]
    return {
        "system": _texts(doc.get("systemInstruction", {}).get("parts", [])),
        "turns": [({"model": "assistant"}.get(c.get("role", "user"), c.get("role", "user")), _texts(c["parts"]))
                  for c in doc["contents"]],
        "params": _params(temperature=config.get("temperature"), top_p=config.get("topP"),
                          top_k=config.get("topK"), max_tokens=config.get("maxOutputTokens"),
                          stop=config.get("stopSequences")),
        "tools": [(d["name"], d.get("description"), d.get("parametersJsonSchema", d.get("parameters", EMPTY_SCHEMA)))
                  for t in doc.get("tools", []) for d in t.get("functionDeclarations", [])],
        "tool_choice": choice,
    }


def canon_anthropic(doc: dict[str, Any]) -> dict[str, Any]:
    choice = doc.get("tool_choice")
    kind = None if choice is None else ("tool", choice["name"]) if choice["type"] == "tool" else (choice["type"],)
    return {
        "system": _texts(doc.get("system", [])),
        "turns": [(m["role"], _texts(m["content"])) for m in doc["messages"]],
        "params": _params(temperature=doc.get("temperature"), top_p=doc.get("top_p"),
                          top_k=doc.get("top_k"), max_tokens=doc.get("max_tokens"),
                          stop=doc.get("stop_sequences")),
        "tools": [(t["name"], t.get("description"), t["input_schema"]) for t in doc.get("tools", [])],
        "tool_choice": kind,
    }


CANON = {"openai": canon_openai, "gemini": canon_gemini, "anthropic": canon_anthropic}
# The sampling parameters a pair of APIs both have; the others are dropped on the way, by design.
SHARED = {frozenset(("openai", "gemini")): {"temperature", "top_p", "max_tokens", "stop"},
          frozenset(("openai", "anthropic")): {"temperature", "top_p", "max_tokens", "stop"},
          frozenset(("gemini", "anthropic")): {"temperature", "top_p", "top_k", "max_tokens", "stop"}}


class RoundTripTests:
    def check_pair(self, a: str, b: str) -> None:
        shared = SHARED[frozenset((a, b))]
        api = {"openai": "openai-chat-completions", "gemini": "gemini-generate-content",
               "anthropic": "anthropic-messages"}[a]
        for index, doc in enumerate(cases(api)):
            if a == "gemini" and index == 3:
                continue        # its parameters use the OpenAPI schema, which is rewritten on the way
            back = convert(f"{b}-to-{a}", convert(f"{a}-to-{b}", doc))
            before, after = CANON[a](doc), CANON[a](back)
            for part in ("system", "turns", "tools", "tool_choice"):
                assert before[part] == after[part], part
            if "max_tokens" not in before["params"] and after["params"].get("max_tokens") == 4096:
                del after["params"]["max_tokens"]     # the default the Messages API needs (reported as added)
            assert {k: v for k, v in before["params"].items() if k in shared} == {k: v for k, v in after["params"].items() if k in shared}

    def test_openai_gemini_openai(self) -> None:
        self.check_pair("openai", "gemini")

    def test_openai_anthropic_openai(self) -> None:
        self.check_pair("openai", "anthropic")

    def test_gemini_openai_gemini(self) -> None:
        self.check_pair("gemini", "openai")

    def test_gemini_anthropic_gemini(self) -> None:
        self.check_pair("gemini", "anthropic")

    def test_anthropic_openai_anthropic(self) -> None:
        self.check_pair("anthropic", "openai")

    def test_anthropic_gemini_anthropic(self) -> None:
        self.check_pair("anthropic", "gemini")

    @pytest.mark.parametrize("doc", cases("openai-chat-completions"))
    def test_a_chain_of_three_keeps_the_conversation(self, doc) -> None:
        once = convert("anthropic-to-openai", convert("gemini-to-anthropic",
                                                      convert("openai-to-gemini", doc)))
        before, after = canon_openai(doc), canon_openai(once)
        for part in ("system", "turns", "tools"):
            assert before[part] == after[part], part


class LanguageEdgeTests:
    """Things the expressions rely on, pinned so an engine change cannot silently alter a recipe."""

    def test_a_message_without_text_is_left_out_not_emitted_empty(self) -> None:
        doc = {"model": "m", "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function",
                                                                  "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "42"}]}
        assert convert("openai-to-gemini", doc) == {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
        assert convert("openai-to-anthropic", doc)["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_a_null_inside_a_tool_schema_is_data_and_survives(self) -> None:
        doc = {"model": "m", "messages": [{"role": "user", "content": "x"}],
               "tools": [{"type": "function", "function": {"name": "f", "parameters": {
                   "type": "object", "properties": {"a": {"default": None}}}}}]}
        for name in ("openai-to-gemini", "openai-to-anthropic"):
            assert '"default": null' in json.dumps(convert(name, doc)), name

    def test_zero_and_false_values_are_carried(self) -> None:
        doc = {"model": "m", "messages": [{"role": "user", "content": "x"}], "temperature": 0, "top_p": 0,
               "seed": 0, "stream": False, "n": 1}
        assert convert("openai-to-gemini", doc)["generationConfig"] == {"temperature": 0, "topP": 0, "candidateCount": 1, "seed": 0}
        assert convert("openai-to-anthropic", doc)["temperature"] == 0
        assert convert("openai-to-anthropic", doc)["stream"] is False

    def test_an_empty_or_missing_messages_list_gives_an_empty_conversation_not_an_error(self) -> None:
        assert convert("openai-to-gemini", {"model": "m", "messages": []}) == {"contents": []}
        assert convert("openai-to-gemini", {"model": "m"}) == {"contents": []}

    def test_unicode_and_newlines_are_kept(self) -> None:
        doc = {"model": "m", "messages": [{"role": "user", "content": "日本語\nline 2 \"quoted\""}]}
        assert convert("openai-to-gemini", doc)["contents"][0]["parts"][0]["text"] == "日本語\nline 2 \"quoted\""


class CliTests:
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        return main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()

    def test_list_recipes_shows_all_six(self) -> None:
        code, out, _ = self.run_cli("--list-recipes")
        assert code == 0
        for name in NAMES:
            assert name in out
        assert "json -> json" in out

    def test_recipe_test_for_a_bundled_recipe(self) -> None:
        code, out, _ = self.run_cli("--recipe", "openai-to-gemini", "--recipe-test")
        assert code == 0
        assert "5/5 passed" in out
