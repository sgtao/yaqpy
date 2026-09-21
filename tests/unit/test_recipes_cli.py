"""``yaqpy --recipe`` and friends, driven in-process with recipe files written to a temp directory."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

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


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
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
        self.assertEqual((code, json.loads(out), err), (0, {"out": {"text": "hi", "size": 3}}, ""))

    def test_reads_yaml_input_by_the_file_extension(self) -> None:
        source = self.write("in.yaml", "text: hi\nsize: 3\n")
        code, out, _ = self.run_cli("--recipe", self.recipe, "-I0", source)
        self.assertEqual((code, json.loads(out)), (0, {"out": {"text": "hi", "size": 3}}))

    def test_the_output_format_is_the_recipes_unless_asked_otherwise(self) -> None:
        source = self.write("in.json", '{"text": "hi", "size": 3}')
        _, out, _ = self.run_cli("--recipe", self.recipe, "-o", "yaml", source)
        self.assertEqual(out, "out:\n  text: hi\n  size: 3\n")

    def test_what_was_dropped_or_added_goes_to_stderr_not_stdout(self) -> None:
        source = self.write("in.json", '{"text": "hi", "secret": "s", "extra": 1}')
        code, out, err = self.run_cli("--recipe", self.recipe, "-I0", source)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"out": {"text": "hi"}})
        self.assertIn("recipe demo: ", err)
        self.assertIn("dropped .secret - never leaves this machine", err)
        self.assertIn("NOT HANDLED .extra", err)

    def test_an_added_item_is_reported_only_when_the_input_gave_nothing(self) -> None:
        with_size = self.write("a.json", '{"text": "hi", "size": 1}')
        self.assertEqual(self.run_cli("--recipe", self.recipe, with_size)[2], "")

    def test_report_replaces_the_result(self) -> None:
        source = self.write("in.json", '{"text": "hi", "secret": "s"}')
        code, out, err = self.run_cli("--recipe", self.recipe, "--report", source)
        self.assertEqual((code, err), (0, ""))
        for fragment in ("Recipe:  demo", "Dropped (the recipe declares", ".secret", "Changes (before",
                         "moved    .text -> .out.text", "(this recipe has no target schema)"):
            self.assertIn(fragment, out)
        self.assertNotIn('"out"', out)

    def test_a_missing_input_file_is_an_error(self) -> None:
        code, out, err = self.run_cli("--recipe", self.recipe, str(self.dir / "nope.json"))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no such file", err)

    def test_an_unknown_recipe(self) -> None:
        source = self.write("in.json", "{}")
        code, _, err = self.run_cli("--recipe", "no-such-recipe", source)
        self.assertEqual(code, 1)
        self.assertIn("unknown recipe 'no-such-recipe'", err)

    def test_a_recipe_file_that_does_not_exist(self) -> None:
        code, _, err = self.run_cli("--recipe", str(self.dir / "gone.yaqpy"), "x.json")
        self.assertEqual(code, 1)
        self.assertIn("recipe file not found", err)

    def test_the_recipe_can_be_a_metadata_only_file(self) -> None:
        meta = self.write("solo.recipe.yaml", "expression: '{\"n\": .text}'\ninput: {format: json}\n")
        source = self.write("in.json", '{"text": "hi"}')
        code, out, _ = self.run_cli("--recipe", meta, "-I0", source)
        self.assertEqual((code, json.loads(out)), (0, {"n": "hi"}))

    def test_an_expression_alone_is_a_recipe_too(self) -> None:
        bare = self.write("bare.yaqpy", ".text")
        source = self.write("in.json", '{"text": "hi"}')
        code, out, err = self.run_cli("--recipe", bare, "-o", "json", source)
        self.assertEqual((code, json.loads(out), err), (0, "hi", ""))


class RecipeIsSafeTests(CliTestCase):
    def test_environment_variables_are_not_readable_even_when_the_cli_allows_them(self) -> None:
        os.environ["YAQPY_RECIPE_SECRET"] = "hunter2"
        self.addCleanup(os.environ.pop, "YAQPY_RECIPE_SECRET", None)
        spy = self.write("spy.yaqpy", '{"leak": env(YAQPY_RECIPE_SECRET)}')
        source = self.write("in.json", "{}")
        code, out, err = self.run_cli("--recipe", spy, source)
        self.assertEqual(code, 1)
        self.assertNotIn("hunter2", out + err)
        self.assertIn("env operations have been disabled", err)

    def test_the_same_expression_does_read_it_without_a_recipe(self) -> None:
        os.environ["YAQPY_RECIPE_SECRET"] = "hunter2"
        self.addCleanup(os.environ.pop, "YAQPY_RECIPE_SECRET", None)
        source = self.write("in.json", "{}")
        code, out, _ = self.run_cli("-o", "json", "-I0", '{"leak": env(YAQPY_RECIPE_SECRET)}', source)
        self.assertEqual((code, json.loads(out)), (0, {"leak": "hunter2"}))


class ArgumentCombinationTests(CliTestCase):
    def test_flags_that_make_no_sense_with_a_recipe(self) -> None:
        source = self.write("in.json", "{}")
        for extra in (["-n"], ["-i"], ["--schema"], ["-P"], ["-s", ".a"], ["--expression", ".a"],
                      ["--from-file", self.recipe]):
            with self.subTest(extra=extra):
                code, _, err = self.run_cli("--recipe", self.recipe, *extra, source)
                self.assertEqual(code, 1)
                self.assertIn("--recipe cannot be combined with", err)

    def test_recipe_only_flags_need_a_recipe(self) -> None:
        for flag in ("--report", "--apply", "--recipe-test"):
            with self.subTest(flag=flag):
                code, _, err = self.run_cli(flag, "x.json")
                self.assertEqual(code, 1)
                self.assertIn("needs --recipe", err)

    def test_apply_and_out_dir_go_together(self) -> None:
        source = self.write("in.json", "{}")
        self.assertIn("--apply needs --out-dir", self.run_cli("--recipe", self.recipe, "--apply", source)[2])
        self.assertIn("--out-dir is used with --apply",
                      self.run_cli("--recipe", self.recipe, "--out-dir", str(self.dir / "o"), source)[2])


class ApplyTests(CliTestCase):
    def test_writes_converted_files_into_the_directory_and_prints_a_table(self) -> None:
        a = self.write("in/a.json", '{"text": "A", "size": 1}')
        b = self.write("in/b.json", '{"text": "B", "secret": "s"}')
        out_dir = str(self.dir / "converted" / "deep")
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", out_dir, a, b)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads((Path(out_dir) / "a.json").read_text("utf-8")),
                         {"out": {"text": "A", "size": 1}})
        self.assertEqual(json.loads((Path(out_dir) / "b.json").read_text("utf-8")), {"out": {"text": "B"}})
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("input") and "schema issues" in lines[0])
        self.assertTrue(lines[1].split()[1] == "ok" and lines[2].split()[1] == "ok")
        self.assertEqual(lines[2].split()[2], "1")            # b.json: one declared drop (.secret)

    def test_the_result_is_check_when_something_was_not_handled(self) -> None:
        a = self.write("a.json", '{"text": "A", "extra": 1}')
        _, out, _ = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir / "o"), a)
        self.assertEqual(out.splitlines()[1].split()[1], "check")

    def test_never_overwrites_an_input(self) -> None:
        a = self.write("a.json", '{"text": "A"}')
        code, _, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir), a)
        self.assertEqual(code, 1)
        self.assertIn("would overwrite", err)
        self.assertEqual(Path(a).read_text("utf-8"), '{"text": "A"}')

    def test_two_inputs_with_the_same_name_do_not_overwrite_each_other(self) -> None:
        a = self.write("one/x.json", '{"text": "1"}')
        b = self.write("two/x.json", '{"text": "2"}')
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir",
                                      str(self.dir / "o"), a, b)
        self.assertEqual(code, 1)
        self.assertIn("would overwrite an input or another output", err)
        self.assertEqual(json.loads((self.dir / "o" / "x.json").read_text("utf-8")), {"out": {"text": "1"}})
        self.assertEqual(out.splitlines()[2].split()[1], "error")

    def test_one_bad_file_does_not_stop_the_others(self) -> None:
        good = self.write("good.json", '{"text": "G"}')
        bad = self.write("bad.json", '{"text": ')
        code, out, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir",
                                      str(self.dir / "o"), bad, good)
        self.assertEqual(code, 1)
        self.assertIn("bad.json", err)
        self.assertTrue((self.dir / "o" / "good.json").exists())
        self.assertFalse((self.dir / "o" / "bad.json").exists())
        self.assertEqual([line.split()[1] for line in out.splitlines()[1:3]], ["error", "ok"])

    def test_the_output_extension_follows_the_output_format(self) -> None:
        a = self.write("a.json", '{"text": "A"}')
        self.run_cli("--recipe", self.recipe, "--apply", "-o", "yaml", "--out-dir", str(self.dir / "o"), a)
        self.assertEqual((self.dir / "o" / "a.yml").read_text("utf-8"), "out:\n  text: A\n") \
            if (self.dir / "o" / "a.yml").exists() else \
            self.assertEqual((self.dir / "o" / "a.yaml").read_text("utf-8"), "out:\n  text: A\n")

    def test_stdin_cannot_be_applied(self) -> None:
        code, _, err = self.run_cli("--recipe", self.recipe, "--apply", "--out-dir", str(self.dir / "o"), "-")
        self.assertEqual(code, 1)
        self.assertIn("--apply needs input files", err)


class RecipeTestCommandTests(CliTestCase):
    def test_runs_the_recipes_own_cases(self) -> None:
        code, out, _ = self.run_cli("--recipe", self.recipe, "--recipe-test")
        self.assertEqual(code, 1)                                  # the second case is wrong on purpose
        self.assertIn("ok   demo: with size", out)
        self.assertIn("FAIL demo: broken on purpose", out)
        self.assertIn("got {", out)
        self.assertIn("1/2 passed", out)

    def test_a_recipe_without_cases(self) -> None:
        code, out, _ = self.run_cli("--recipe", self.write("bare.yaqpy", "."), "--recipe-test")
        self.assertEqual((code, out), (0, "recipe bare has no test cases\n"))


class PruneFlagTests(CliTestCase):
    def test_prune_flags_without_a_recipe(self) -> None:
        source = self.write("in.json", '{"a": null, "b": {"c": {}}, "d": [null], "e": 1}')
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", source)
        self.assertEqual(json.loads(out), {"b": {"c": {}}, "d": [None], "e": 1})
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", "--prune-empty", source)
        self.assertEqual(json.loads(out), {"d": [None], "e": 1})

    def test_prune_flags_after_an_expression(self) -> None:
        source = self.write("in.json", '{"a": {"x": null}, "k": 1}')
        _, out, _ = self.run_cli("-o", "json", "-I0", "--prune-null", "--prune-empty", ".a", source)
        self.assertEqual(out.strip(), "{}")

    def test_metadata_can_switch_pruning_on_and_the_flags_add_to_it(self) -> None:
        self.write("nully.yaqpy", '{"a": null, "b": {}, "c": 1}')
        self.write("nully.recipe.yaml", "prune: [nulls]\n")
        source = self.write("in.json", "{}")
        _, out, _ = self.run_cli("--recipe", str(self.dir / "nully.yaqpy"), "-I0", source)
        self.assertEqual(json.loads(out), {"b": {}, "c": 1})
        _, out, _ = self.run_cli("--recipe", str(self.dir / "nully.yaqpy"), "-I0", "--prune-empty", source)
        self.assertEqual(json.loads(out), {"c": 1})


if __name__ == "__main__":
    unittest.main()
