"""The command describing itself: the operator table, the run-and-pinned examples and the four outputs."""

from __future__ import annotations

import io
import os
import re

import pytest
import yaqpy
from yaqpy.app.examples import EXAMPLES, run_example
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.selfdoc import (
    RULES, operator_table, render_guide_prompt, render_skill_md, render_spec,
)
from yaqpy.app.service import YqService
from yaqpy.cli.main import main
from yaqpy.core.lang.lex_rules import DEFAULT_RULES
from yaqpy.core.lang.specs import BASE_SPECS
from yaqpy.core.operators import builtin_registry
from yaqpy.errors import YqError
from yaqpy.formats.registry import builtin_formats
from yaqpy.recipes import builtin_recipes

SERVICE = YqService(InMemoryFileSystem(), StaticEnvironment({}))
TABLE = operator_table()
# The operators that touch files, the environment or other programs are left out on purpose
# (plan 5-2, O3). When one of them is implemented, this set - and USAGE.ja.md - must change with it.
NOT_IMPLEMENTED = {"envsubst", "error", "eval", "load", "load_base64", "load_props", "load_str",
                   "load_xml", "str_load", "system", "xml_load"}


def probe(name: str, arguments: int) -> str:
    return name if arguments == 0 or name.startswith("@") else f'{name}("x")' if arguments == 1 else name


def failure_of(expression: str) -> str:
    try:
        yaqpy.evaluate(expression, "a: 1\n")
    except YqError as e:
        return str(e)
    return ""


class OperatorTableTests:
    def test_the_operators_that_are_not_implemented_are_the_ones_left_out_on_purpose(self) -> None:
        assert {i.name for i in TABLE if not i.implemented} == NOT_IMPLEMENTED

    def test_every_operator_listed_as_missing_really_answers_unknown_operator(self) -> None:
        for info in TABLE:
            if info.implemented:
                continue
            for name in info.names:
                spec = builtin_registry().get(info.type)
                assert "unknown operator" in failure_of(probe(name, spec.num_args))

    def test_no_listed_operator_answers_unknown_operator(self) -> None:
        for info in TABLE:
            if not info.implemented:
                continue
            spec = builtin_registry().get(info.type)
            for name in info.names:
                expression = probe(name, spec.num_args)
                assert "unknown operator" not in failure_of(expression), expression

    def test_every_operator_type_that_a_word_can_reach_is_in_the_table(self) -> None:
        """The table is read from the lexer; nothing with a handler-less type may hide from it."""
        listed = {i.type for i in TABLE}
        symbols_only = {"SLICE"}            # no word writes it: `.[1:3]` is TRAVERSE_ARRAY
        for kind in BASE_SPECS:
            if not builtin_registry().has_handler(kind) and kind not in symbols_only:
                assert kind in listed

    def test_a_name_is_listed_once_and_its_spellings_are_variants_of_it(self) -> None:
        names = [i.name for i in TABLE]
        assert len(names) == len(set(names))
        by_name = {i.name: i for i in TABLE}
        assert set(by_name["to_number"].names) == {"to_number", "tonumber"}
        assert "sortKeys" in by_name["sort_keys"].names
        assert by_name["to_json"].type != ""
        assert "to_xml" not in by_name["to_json"].names        # one handler, two operators

    def test_yaqpy_extensions_are_marked_and_the_rest_is_go_yq(self) -> None:
        assert {i.name for i in TABLE if i.extension} == {"schema", "prune_null", "prune_empty"}

    def test_words_with_arguments_and_at_names_are_there(self) -> None:
        names = {i.name for i in TABLE}
        assert {"env", "strenv", "@base64", "@yaml", "from_json", "to_csv", "ascii_downcase"} <= names

    def test_no_stray_fragments_of_a_regular_expression_become_operators(self) -> None:
        names = {i.name for i in TABLE}
        assert not {"nu", "ne", "ff"} & names
        assert all(name.lstrip("@").replace("_", "").isalnum() for name in names)

    def test_the_table_walks_the_lexer_rules(self) -> None:
        assert len(DEFAULT_RULES) > 100
        assert len(TABLE) > 100


class ExampleTests:
    @pytest.mark.parametrize("example", EXAMPLES)
    def test_every_example_gives_exactly_the_pinned_output(self, example) -> None:
        output, _ = run_example(SERVICE, example)
        assert output == example.expected

    def test_a_recipe_example_shows_what_was_dropped(self) -> None:
        recipe_examples = [e for e in EXAMPLES if e.recipe]
        assert recipe_examples
        for example in recipe_examples:
            _, notes = run_example(SERVICE, example)
            for expected in example.expected_notes:
                assert any(note.startswith(expected) for note in notes), expected

    @pytest.mark.parametrize("example", EXAMPLES)
    def test_the_commands_shown_are_the_ones_that_were_run(self, example) -> None:
        assert example.command.startswith("yaqpy")
        assert example.command.endswith(example.input_name)

    def test_the_examples_cover_the_main_features(self) -> None:
        text = " ".join(e.command for e in EXAMPLES)
        for feature in ("select", "sort_by", "ireduce", "eval-all", "schema", "--prune-null", "--recipe"):
            assert feature in text


class SpecTests:
    spec = render_spec(SERVICE)

    def test_lists_every_implemented_operator_and_every_missing_one_in_its_own_section(self) -> None:
        usable_part, _, rest = self.spec.partition("### 使えない演算子")
        missing_part = rest.split("## 4.")[0]
        for info in TABLE:
            if info.implemented:
                assert f"`{info.name}`" in usable_part
                assert f"`{info.name}`" not in missing_part
            else:
                assert f"`{info.name}`" in missing_part

    def test_counts_are_the_table_counts(self) -> None:
        usable = [i for i in TABLE if i.implemented and not i.extension]
        assert f"使える演算子（{len(usable)} 個" in self.spec
        assert f"使えない演算子（{len([i for i in TABLE if not i.implemented])} 個" in self.spec

    def test_lists_the_formats_of_the_registry(self) -> None:
        for name in builtin_formats().input_formats():
            assert f"| `{name}` |" in self.spec

    def test_lists_the_recipes_and_the_extensions(self) -> None:
        for name in builtin_recipes():
            assert f"`{name}`" in self.spec
        for extension in ("schema", "prune_null", "--recipe", "--print-spec"):
            assert extension in self.spec

    def test_says_which_ways_of_writing_do_not_work(self) -> None:
        for title, _ in RULES:
            assert title in self.spec

    def test_is_the_same_every_time(self) -> None:
        assert render_spec(SERVICE) == self.spec


class GuidePromptTests:
    prompt = render_guide_prompt(SERVICE)

    def test_forbids_the_idiom_that_silently_gives_a_wrong_answer(self) -> None:
        assert "`select` の後ろに定数やオブジェクトを続けない" in self.prompt
        assert '(.contents[] | select(.role == "assistant") | .role) = "model"' in self.prompt

    def test_names_every_operator_that_must_not_be_used(self) -> None:
        missing_line = next(line for line in self.prompt.splitlines() if line.startswith("使えない演算子"))
        for name in NOT_IMPLEMENTED:
            assert name in missing_line

    def test_lists_the_usable_operators_but_not_the_missing_ones_among_them(self) -> None:
        usable_line = next(line for line in self.prompt.splitlines() if line.startswith("使える演算子"))
        assert " select " in usable_line
        assert " eval " not in usable_line + " "

    def test_examples_carry_real_results(self) -> None:
        for example in EXAMPLES[:10]:
            output, _ = run_example(SERVICE, example)
            assert output.rstrip("\n") in self.prompt

    def test_asks_for_a_checked_answer(self) -> None:
        assert "実際に実行して確かめた結果だけ" in self.prompt


class SkillMdTests:
    skill = render_skill_md(SERVICE)

    def test_starts_with_a_front_matter_that_names_the_skill_and_its_triggers(self) -> None:
        meta = _to_python(self.skill.split("---\n")[1])
        assert meta["name"] == "yaqpy"
        for phrase in ("yq で", "JSON を YAML に変換", "JSON Schema", "OpenAI のリクエストを Gemini"):
            assert phrase in meta["description"]

    @pytest.mark.parametrize("feature", ("--recipe", "--report", "--apply --out-dir", "--recipe-test", "--list-recipes",
                    "schema", "--schema-strict", "--prune-null", "eval-all", "--print-spec", "--example",
                    "--toml-allow-lossy", "-i"))
    def test_covers_every_feature(self, feature) -> None:
        assert feature in self.skill

    def test_covers_every_format_and_every_recipe(self) -> None:
        for name in builtin_formats().input_formats():
            assert f"`{name}`" in self.skill
        for name in builtin_recipes():
            assert name in self.skill

    def test_tells_the_reader_what_is_dropped_and_that_nothing_calls_an_api(self) -> None:
        for sentence in ("落としたものは必ず報告されます", "実際の API は呼びません", "4096"):
            assert sentence in self.skill

    def test_carries_the_rules_the_examples_and_the_operator_lists(self) -> None:
        for title, _ in RULES:
            assert title in self.skill
        assert "使用例（実行済み）" in self.skill
        assert "### 使えない演算子" in self.skill
        for example in EXAMPLES:
            assert example.command in self.skill


def _to_python(yaml_text: str) -> dict[str, str]:
    from yaqpy.core.model.convert import to_python
    from yaqpy.formats.yaml.codec import YamlDecoder
    from yaqpy.options import Options

    return to_python(next(iter(YamlDecoder(Options()).decode_documents(yaml_text))))


class CliTests:
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        return main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()

    def test_each_flag_prints_its_document_and_exits_zero(self) -> None:
        expected = {"--print-spec": "# yaqpy 式の仕様", "--example": "# yaqpy の使用例",
                    "--guide-prompt": "# yaqpy の式を書いてください", "--skill-md": "---\nname: yaqpy\n"}
        for flag, start in expected.items():
            code, out, err = self.run_cli(flag)
            assert (code, err) == (0, "")
            assert out.startswith(start), out[:60]
            assert out.endswith("\n") and not out.endswith("\n\n")

    def test_the_names_from_mdss_convert_are_aliases(self) -> None:
        assert self.run_cli("--sample")[1] == self.run_cli("--example")[1]
        assert self.run_cli("--prompts")[1] == self.run_cli("--guide-prompt")[1]

    def test_the_output_is_what_the_render_functions_give(self) -> None:
        assert self.run_cli("--print-spec")[1] == render_spec(SERVICE).rstrip("\n") + "\n"
        assert self.run_cli("--skill-md")[1] == render_skill_md(SERVICE).rstrip("\n") + "\n"

    def test_only_one_at_a_time_and_no_arguments(self) -> None:
        code, out, err = self.run_cli("--print-spec", "--example")
        assert (code, out) == (1, "")
        assert "cannot be used together" in err
        code, out, err = self.run_cli("--print-spec", "a.yaml")
        assert (code, out) == (1, "")
        assert "takes no expression, files or recipe" in err

    def test_no_file_is_read_and_the_environment_does_not_matter(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("YAQPY_SPEC_PROBE", "must not appear")
        monkeypatch.chdir(tmp_path)
        code, out, _ = self.run_cli("--skill-md")
        assert code == 0
        assert "must not appear" not in out
        assert list(tmp_path.iterdir()) == []

    def test_help_shows_examples_of_the_new_features(self) -> None:
        out = io.StringIO()
        from yaqpy.cli.parser import print_help

        print_help(out)
        for text in ("--recipe openai-to-gemini", "--list-recipes", "-o json schema data.yaml",
                     "--print-spec | --example | --guide-prompt | --skill-md"):
            assert text in out.getvalue()


class DocumentationTests:
    """What the guides say must be what the command says (the plan asks for exactly this check)."""

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def read(self, name: str) -> str:
        with open(os.path.join(self.ROOT, name), encoding="utf-8") as handle:
            return handle.read()

    def test_usage_lists_exactly_the_operators_that_are_not_implemented(self) -> None:
        text = self.read("USAGE.ja.md")
        begin = text.index("<!-- yaqpy:unimplemented-operators:begin")
        end = text.index("<!-- yaqpy:unimplemented-operators:end -->")
        block = text[text.index("-->", begin) + 3:end]
        documented = set(re.findall(r"`([^`]+)`", block))
        assert documented == {i.name for i in TABLE if not i.implemented}

    def test_usage_describes_every_bundled_recipe_and_every_new_flag(self) -> None:
        text = self.read("USAGE.ja.md")
        for name in builtin_recipes():
            assert f"`{name}`" in text
        for flag in ("--recipe", "--list-recipes", "--recipe-test", "--report", "--apply", "--out-dir",
                     "--prune-null", "--prune-empty", "--print-spec", "--example", "--guide-prompt",
                     "--skill-md", "apply_recipe"):
            assert flag in text

    def test_the_readme_mentions_the_new_features(self) -> None:
        text = self.read("README.md")
        for feature in ("--recipe", "--print-spec", "--skill-md", "--apply --out-dir"):
            assert feature in text

    def test_every_flag_the_parser_has_for_these_features_is_in_the_guide(self) -> None:
        from yaqpy.cli.parser import build_parser

        text = self.read("USAGE.ja.md")
        ours = {"--recipe", "--list-recipes", "--recipe-test", "--report", "--apply", "--out-dir",
                "--prune-null", "--prune-empty", "--print-spec", "--example", "--guide-prompt",
                "--skill-md", "--sample", "--prompts"}
        known = {option for action in build_parser()._actions for option in action.option_strings}  # noqa: SLF001
        assert ours <= known
        for flag in ours:
            assert flag in text

    def test_usage_and_the_gui_guide_describe_content_based_detection(self) -> None:
        usage = self.read("USAGE.ja.md")
        assert "入力形式の自動判定" in usage
        assert "detect_format" in usage
        gui = self.read("USAGE-GUI.ja.md")
        assert "中身を見て判定" in gui
