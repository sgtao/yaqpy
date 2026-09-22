"""``yaqpy --recipe`` and friends, driven in-process with recipe files written to a temp directory."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from yaqpy.cli.main import main

EXPRESSION = """\
# rename and move; every optional key only when present
. as $in
| {"out": {"text": $in.text}}
| (select($in.size != null) | .out.size) = $in.size
"""

METADATA = """\
name: demo
title: Demo conversion
input: {format: json}
output: {format: json}
carries: [.text, .size]
drops:
  - {path: .secret, reason: never leaves this machine}
adds:
  - {path: .out.size, reason: the target needs a size, unless: [.size]}
tests:
  - name: with size
    input: {text: a, size: 2}
    expected: {out: {text: a, size: 2}}
  - name: broken on purpose
    input: {text: a}
    expected: {out: {text: b}}
"""


class CliTestCase:
    @pytest.fixture(autouse=True)
    def _workspace(self, tmp_path: Path) -> None:
        self.dir = tmp_path
        self.recipe = self.write("demo.yaqpy", EXPRESSION)
        self.write("demo.recipe.yaml", METADATA)

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return str(path)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()


class RunRecipeTests(CliTestCase):
    def test_prints_the_converted_result(self) -> None:
        source = self.write("in.json", '{"text": "hi", "size": 3}')
        code, out, err = self.run_cli("--recipe", self.recipe, "-I0", source)
        assert (code, json.loads(out), err) == (0, {"out": {"text": "hi", "size": 3}}, "")

    def test_reads_yaml_input_by_the_file_extension(self) -> None:
        source = self.write("in.yaml", "text: hi\nsize: 3\n")
        code, out, _ = self.run_cli("--recipe", self.recipe, "-I0", source)
        assert (code, json.loads(out)) == (0, {"out": {"text": "hi", "size": 3}})

    def test_the_output_format_is_the_recipes_unless_asked_otherwise(self) -> None:
        source = self.write("in.json", '{"text": "hi", "size": 3}')
        _, out, _ = self.run_cli("--recipe", self.recipe, "-o", "yaml", source)
        assert out == "out:\n  text: hi\n  size: 3\n"

    def test_what_was_dropped_or_added_goes_to_stderr_not_stdout(self) -> None:
        source = self.write("in.json", '{"text": "hi", "secret": "s", "extra": 1}')
        code, out, err = self.run_cli("--recipe", self.recipe, "-I0", source)
        assert code == 0
        assert json.loads(out) == {"out": {"text": "hi"}}
        assert "recipe demo: " in err
        assert "dropped .secret - never leaves this machine" in err
        assert "NOT HANDLED .extra" in err

    def test_an_added_item_is_reported_only_when_the_input_gave_nothing(self) -> None:
        with_size = self.write("a.json", '{"text": "hi", "size": 1}')
        assert self.run_cli("--recipe", self.recipe, with_size)[2] == ""

    def test_report_replaces_the_result(self) -> None:
        source = self.write("in.json", '{"text": "hi", "secret": "s"}')
        code, out, err = self.run_cli("--recipe", self.recipe, "--report", source)
        assert (code, err) == (0, "")
        for fragment in ("Recipe:  demo", "Dropped (the recipe declares", ".secret", "Changes (before",
                         "moved    .text -> .out.text", "(this recipe has no target schema)"):
            assert fragment in out
        assert '"out"' not in out

    def test_a_missing_input_file_is_an_error(self) -> None:
        code, out, err = self.run_cli("--recipe", self.recipe, str(self.dir / "nope.json"))
        assert (code, out) == (1, "")
        assert "no such file" in err

    def test_an_unknown_recipe(self) -> None:
        source = self.write("in.json", "{}")
        code, _, err = self.run_cli("--recipe", "no-such-recipe", source)
        assert code == 1
        assert "unknown recipe 'no-such-recipe'" in err

    def test_a_recipe_file_that_does_not_exist(self) -> None:
        code, _, err = self.run_cli("--recipe", str(self.dir / "gone.yaqpy"), "x.json")
        assert code == 1
        assert "recipe file not found" in err

    def test_the_recipe_can_be_a_metadata_only_file(self) -> None:
        meta = self.write("solo.recipe.yaml", "expression: '{\"n\": .text}'\ninput: {format: json}\n")
        source = self.write("in.json", '{"text": "hi"}')
        code, out, _ = self.run_cli("--recipe", meta, "-I0", source)
        assert (code, json.loads(out)) == (0, {"n": "hi"})

    def test_an_expression_alone_is_a_recipe_too(self) -> None:
        bare = self.write("bare.yaqpy", ".text")
        source = self.write("in.json", '{"text": "hi"}')
        code, out, err = self.run_cli("--recipe", bare, "-o", "json", source)
        assert (code, json.loads(out), err) == (0, "hi", "")


class RecipeIsSafeTests(CliTestCase):
    def test_environment_variables_are_not_readable_even_when_the_cli_allows_them(self, monkeypatch) -> None:
        monkeypatch.setenv("YAQPY_RECIPE_SECRET", "hunter2")
        spy = self.write("spy.yaqpy", '{"leak": env(YAQPY_RECIPE_SECRET)}')
        source = self.write("in.json", "{}")
        code, out, err = self.run_cli("--recipe", spy, source)
        assert code == 1
        assert "hunter2" not in out + err
        assert "env operations have been disabled" in err

    def test_the_same_expression_does_read_it_without_a_recipe(self, monkeypatch) -> None:
        monkeypatch.setenv("YAQPY_RECIPE_SECRET", "hunter2")
        source = self.write("in.json", "{}")
        code, out, _ = self.run_cli("-o", "json", "-I0", '{"leak": env(YAQPY_RECIPE_SECRET)}', source)
        assert (code, json.loads(out)) == (0, {"leak": "hunter2"})


class ArgumentCombinationTests(CliTestCase):
    @pytest.mark.parametrize("extra", (["-n"], ["-i"], ["--schema"], ["-P"], ["-s", ".a"],
                                       ["--expression", ".a"], ["--from-file", "@recipe"]),
                             ids=lambda extra: " ".join(extra))
    def test_flags_that_make_no_sense_with_a_recipe(self, extra) -> None:
        source = self.write("in.json", "{}")
        extra = [self.recipe if word == "@recipe" else word for word in extra]
        code, _, err = self.run_cli("--recipe", self.recipe, *extra, source)
        assert code == 1
        assert "--recipe cannot be combined with" in err

    @pytest.mark.parametrize("flag", ("--report", "--apply", "--recipe-test"))
    def test_recipe_only_flags_need_a_recipe(self, flag) -> None:
        code, _, err = self.run_cli(flag, "x.json")
        assert code == 1
        assert "needs --recipe" in err

    def test_apply_and_out_dir_go_together(self) -> None:
        source = self.write("in.json", "{}")
        assert "--apply needs --out-dir" in self.run_cli("--recipe", self.recipe, "--apply", source)[2]
        assert "--out-dir is used with --apply" in self.run_cli("--recipe", self.recipe, "--out-dir", str(self.dir / "o"), source)[2]


class ApplyTests(CliTestCase):
    def test_writes_converted_files_into_the_directory_and_prints_a_table(self) -> None:
        a = self.write("in/a.json", '{"text": "A", "size": 1}')
        b = self.write("in/b.json", '{"text": "B", "secret": "s"}')
        out_dir = str(self.dir / "converted" / "deep")
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", out_dir, a, b)
        assert (code, err) == (0, "")
        assert json.loads((Path(out_dir) / "a.json").read_text("utf-8")) == {"out": {"text": "A", "size": 1}}
        assert json.loads((Path(out_dir) / "b.json").read_text("utf-8")) == {"out": {"text": "B"}}
        lines = out.splitlines()
        assert lines[0].startswith("input") and "schema issues" in lines[0]
        assert lines[1].split()[1] == "ok" and lines[2].split()[1] == "ok"
        assert lines[2].split()[2] == "1"            # b.json: one declared drop (.secret)

    def test_the_result_is_check_when_something_was_not_handled(self) -> None:
        a = self.write("a.json", '{"text": "A", "extra": 1}')
        _, out, _ = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir / "o"), a)
        assert out.splitlines()[1].split()[1] == "check"

    def test_never_overwrites_an_input(self) -> None:
        a = self.write("a.json", '{"text": "A"}')
        code, _, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir), a)
        assert code == 1
        assert "would overwrite" in err
        assert Path(a).read_text("utf-8") == '{"text": "A"}'

    def test_two_inputs_with_the_same_name_do_not_overwrite_each_other(self) -> None:
        a = self.write("one/x.json", '{"text": "1"}')
        b = self.write("two/x.json", '{"text": "2"}')
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir",
                                      str(self.dir / "o"), a, b)
        assert code == 1
        assert "would overwrite an input or another output" in err
        assert json.loads((self.dir / "o" / "x.json").read_text("utf-8")) == {"out": {"text": "1"}}
        assert out.splitlines()[2].split()[1] == "error"

    def test_one_bad_file_does_not_stop_the_others(self) -> None:
        good = self.write("good.json", '{"text": "G"}')
        bad = self.write("bad.json", '{"text": ')
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir",
                                      str(self.dir / "o"), bad, good)
        assert code == 1
        assert "bad.json" in err
        assert (self.dir / "o" / "good.json").exists()
        assert not (self.dir / "o" / "bad.json").exists()
        assert [line.split()[1] for line in out.splitlines()[1:3]] == ["error", "ok"]

    def test_the_output_extension_follows_the_output_format(self) -> None:
        a = self.write("a.json", '{"text": "A"}')
        self.run_cli("--recipe", self.recipe, "--apply", "-o", "yaml", "--out-dir", str(self.dir / "o"), a)
        written = [p for p in (self.dir / "o").iterdir()]
        assert [p.suffix for p in written] in ([".yml"], [".yaml"])
        assert written[0].read_text("utf-8") == "out:\n  text: A\n"

    def test_stdin_cannot_be_applied(self) -> None:
        code, _, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir / "o"), "-")
        assert code == 1
        assert "--apply needs input files" in err


class RecipeTestCommandTests(CliTestCase):
    def test_runs_the_recipes_own_cases(self) -> None:
        code, out, _ = self.run_cli("--recipe", self.recipe, "--recipe-test")
        assert code == 1                                  # the second case is wrong on purpose
        assert "ok   demo: with size" in out
        assert "FAIL demo: broken on purpose" in out
        assert "got {" in out
        assert "1/2 passed" in out

    def test_a_recipe_without_cases(self) -> None:
        code, out, _ = self.run_cli("--recipe", self.write("bare.yaqpy", "."), "--recipe-test")
        assert (code, out) == (0, "recipe bare has no test cases\n")


class PruneFlagTests(CliTestCase):
    def test_prune_flags_without_a_recipe(self) -> None:
        source = self.write("in.json", '{"a": null, "b": {"c": {}}, "d": [null], "e": 1}')
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", source)
        assert json.loads(out) == {"b": {"c": {}}, "d": [None], "e": 1}
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", "--prune-empty", source)
        assert json.loads(out) == {"d": [None], "e": 1}

    def test_prune_flags_after_an_expression(self) -> None:
        source = self.write("in.json", '{"a": {"x": null}, "k": 1}')
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", "--prune-empty", ".a", source)
        assert out.strip() == "{}"

    def test_metadata_can_switch_pruning_on_and_the_flags_add_to_it(self) -> None:
        self.write("nully.yaqpy", '{"a": null, "b": {}, "c": 1}')
        self.write("nully.recipe.yaml", "prune: [nulls]\n")
        source = self.write("in.json", "{}")
        _, out, _ = self.run_cli("--recipe", str(self.dir / "nully.yaqpy"), "-I0", source)
        assert json.loads(out) == {"b": {}, "c": 1}
        _, out, _ = self.run_cli("--recipe", str(self.dir / "nully.yaqpy"), "-I0", "--prune-empty", source)
        assert json.loads(out) == {"c": 1}


class RecipeMetadataCannotReadOtherFilesTests(CliTestCase):
    """The expression cannot touch files (strict security); neither may the metadata name one."""

    @pytest.fixture(autouse=True)
    def _secret_and_source(self, _workspace) -> None:
        self.write("secret.json", '{"type": "object", "const": "TOP-SECRET-VALUE"}')
        self.source = self.write("in.json", '{"a": 1}')

    def recipe_naming(self, target: str) -> str:
        self.write("box/r.yaqpy", ".")
        self.write("box/r.recipe.yaml", f"target_schema: {target}\n")
        return str(self.dir / "box" / "r.yaqpy")

    @pytest.mark.parametrize("target", ["../secret.json", "..\\\\secret.json", "@absolute",
                                        "sub/../../secret.json"])
    def test_a_parent_folder_and_an_absolute_path_are_refused(self, target) -> None:
        if target == "@absolute":
            target = str(self.dir / "secret.json").replace("\\", "/")
        code, out, err = self.run_cli("--recipe", self.recipe_naming(f'"{target}"'), self.source)
        assert (code, out) == (1, "")
        assert "must be a file in the folder of the recipe" in err
        assert "TOP-SECRET-VALUE" not in out + err

    def test_a_file_next_to_the_recipe_is_fine(self) -> None:
        self.write("box/schema.json", '{"type": "object", "required": ["b"]}')
        code, out, err = self.run_cli("--recipe", self.recipe_naming("schema.json"), "-I0", self.source)
        assert (code, json.loads(out)) == (0, {"a": 1})
        assert "target schema: .b: required" in err

    def test_the_same_holds_for_a_metadata_only_recipe_that_names_an_expression_file(self) -> None:
        self.write("box/only.recipe.yaml", "expression_file: ../secret.json\n")
        code, out, err = self.run_cli("--recipe", str(self.dir / "box" / "only.recipe.yaml"), self.source)
        assert (code, out) == (1, "")
        assert "must be a file in the folder of the recipe" in err
