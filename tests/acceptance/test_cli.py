"""CLI acceptance tests, ported from yq's ``acceptance_tests/*.sh`` (phase 1 subset).

Each test runs ``python -m yaqpy`` in a subprocess so exit codes, stdin handling
and file writes are exercised for real.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def yq(*args: str, stdin: str | None = None, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "yaqpy", *args], input=stdin, capture_output=True, text=True,
        encoding="utf-8", env=ENV, cwd=cwd, timeout=120,
    )


class CliTestCase:
    @pytest.fixture(autouse=True)
    def _workspace(self, tmp_path: Path) -> None:
        self.dir = tmp_path

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8", newline="")
        return str(path)


class BasicTests(CliTestCase):
    def test_round_trip_with_null_input(self) -> None:
        r = yq("-n", ".a = 123")
        assert (r.returncode, r.stdout) == (0, "a: 123\n")
        path = self.write("test.yml", r.stdout)
        r = yq(".a", path)
        assert r.stdout == "123\n"

    def test_trailing_comment_and_foot_comment(self) -> None:
        path = self.write("t.yml", "test:\n# this comment will be removed\n")
        assert yq(path, "-P").stdout == "test:\n# this comment will be removed\n"
        assert yq('. footComment = "hi"', path).stdout == "test:\n# hi\n"
        assert yq("ea", '. footComment = "hi"', path).stdout == "test:\n# hi\n"

    def test_pipe_with_dot(self) -> None:
        assert yq(".", stdin="a: 123\n").stdout == "a: 123\n"

    def test_expression_flag_when_file_looks_like_expression(self) -> None:
        path = self.write("test.yml", "xyz: 123\n")
        assert yq("--expression", ".xyz", path).stdout == "123\n"
        assert yq("ea", "--expression", ".xyz", path).stdout == "123\n"

    def test_expression_from_file_including_dos_line_endings(self) -> None:
        data = self.write("test.yml", "xyz: 123\n")
        for ending in ("\n", "\r\n"):
            instructions = self.write("instructions.txt", '.xyz = "meow" | .cool = "frog"' + ending)
            r = yq("--from-file", instructions, data, "-o=j", "-I=0")
            assert r.stdout == '{"xyz":"meow","cool":"frog"}\n'
            r = yq("ea", "--from-file", instructions, data, "-o=j", "-I=0")
            assert r.stdout == '{"xyz":"meow","cool":"frog"}\n'

    def test_github_action_style_stdin(self) -> None:
        path = self.write("test.yml", "a: 123\n")
        # stdin is a pipe (empty) but a file is given: read the file, not stdin
        assert yq(path, stdin="").stdout == "a: 123\n"
        assert yq("e", path, stdin="").stdout == "a: 123\n"
        assert yq("ea", path, stdin="").stdout == "a: 123\n"
        assert yq(".a", path, stdin="").stdout == "123\n"

    def test_eval_all_files(self) -> None:
        a = self.write("a.yml", "a: 123\n")
        b = self.write("b.yml", "a: 124\n")
        assert yq("ea", a, b).stdout == yq("e", ".", a, b).stdout
        assert yq("ea", a, b).stdout == "a: 123\n---\na: 124\n"

    def test_in_place(self) -> None:
        path = self.write("test.yml", "a: 1 # keep\nb: 2\n")
        r = yq("-i", ".a = 5", path)
        assert r.returncode == 0
        assert Path(path).read_text(encoding="utf-8") == "a: 5 # keep\nb: 2\n"

    def test_in_place_failure_leaves_file(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        r = yq("-i", ".a + {}", path)
        assert r.returncode == 1
        assert Path(path).read_text(encoding="utf-8") == "a: 1\n"


class EmptyInputTests(CliTestCase):
    def test_comment_only_file(self) -> None:
        path = self.write("test.yml", "# comment\n")
        assert yq("e", path).stdout == "# comment\n"
        assert yq("e", '.apple = "tree"', path).stdout == "# comment\napple: tree\n"
        assert yq("ea", '.apple = "tree"', path).stdout == "# comment\napple: tree\n"

    def test_comment_only_no_newline(self) -> None:
        path = self.write("test.yml", "#comment")
        assert yq("e", path).stdout == "#comment\n"

    def test_empty_file(self) -> None:
        path = self.write("test.yml", "")
        assert yq("e", '.apple = "tree"', path).stdout == "apple: tree\n"
        assert yq("ea", '.apple = "tree"', path).stdout == "apple: tree\n"


class LeadingSeparatorTests(CliTestCase):
    def test_separator_is_kept(self) -> None:
        path = self.write("test.yml", "---\na: 1\n")
        assert yq(path).stdout == "---\na: 1\n"
        assert yq("-N", path).stdout == "a: 1\n"

    def test_directive_and_comment_before_separator(self) -> None:
        path = self.write("test.yml", "%YAML 1.1\n# hi\n---\na: 1\n")
        assert yq(path).stdout == "%YAML 1.1\n# hi\n---\na: 1\n"

    def test_multiple_documents(self) -> None:
        path = self.write("test.yml", "a: 1\n---\nb: 2\n")
        assert yq(".", path).stdout == "a: 1\n---\nb: 2\n"
        assert yq("-N", ".", path).stdout == "a: 1\nb: 2\n"


class OutputFormatTests(CliTestCase):
    def test_auto_format_from_extension(self) -> None:
        path = self.write("test.json", '{"a": [1, 2]}')
        assert yq(".a[0]", path).stdout == "1\n"
        assert yq(".", path).stdout == '{\n  "a": [\n    1,\n    2\n  ]\n}\n'
        assert yq("-oy", ".", path).stdout == "a:\n  - 1\n  - 2\n"

    def test_explicit_input_format_defaults_output_to_yaml(self) -> None:
        path = self.write("test.json", '{"a": 1}')
        r = yq("-p", "json", ".", path)
        assert r.stdout == "a: 1\n"

    def test_json_indent_zero(self) -> None:
        assert yq("-o=j", "-I=0", ".", stdin="a: [1, {b: x}]\n").stdout == '{"a":[1,{"b":"x"}]}\n'

    def test_props(self) -> None:
        assert yq("-o=props", ".", stdin="a:\n  b: 1\n  c: [x, y]\n").stdout == "a.b = 1\na.c.0 = x\na.c.1 = y\n"

    def test_unwrap_scalar_flag(self) -> None:
        assert yq(".a", stdin='a: "x"\n').stdout == "x\n"
        assert yq("-r=false", ".a", stdin='a: "x"\n').stdout == '"x"\n'
        assert yq("-o=json", ".a", stdin='a: "x"\n').stdout == '"x"\n'
        assert yq("-o=json", "-r", ".a", stdin='a: "x"\n').stdout == "x\n"

    def test_unknown_format(self) -> None:
        r = yq("-o", "hcl", ".", stdin="a: 1\n")
        assert r.returncode == 1
        assert "unknown format" in r.stderr


class ToonOutputTests(CliTestCase):
    SAMPLE = "a: 1 # comment\nitems:\n  - n: x\n    v: 1\n  - n: y\n    v: 2\n"
    EXPECTED = "a: 1\nitems[2]{n,v}:\n  x,1\n  y,2\n"

    def test_output_format_toon(self) -> None:
        assert yq("-o", "toon", ".", stdin=self.SAMPLE).stdout == self.EXPECTED
        assert yq("-o=toon", ".items[0].n", stdin=self.SAMPLE).stdout == "x\n"

    def test_toon_flag_is_shorthand(self) -> None:
        r = yq("--toon", ".", stdin=self.SAMPLE)
        assert (r.returncode, r.stdout) == (0, self.EXPECTED)
        # order does not matter and it composes with the eval subcommand
        assert yq("e", ".", "--toon", stdin=self.SAMPLE).stdout == self.EXPECTED

    def test_toon_flag_conflicts_with_other_output_format(self) -> None:
        r = yq("--toon", "-o", "json", ".", stdin=self.SAMPLE)
        assert r.returncode == 1
        assert "--toon cannot be combined" in r.stderr
        # the same format twice is fine
        assert yq("--toon", "-o", "toon", ".", stdin=self.SAMPLE).returncode == 0

    def test_toon_delimiter(self) -> None:
        assert yq("--toon", "--toon-delimiter", "tab", ".items", stdin=self.SAMPLE).stdout == "[2\t]{n\tv}:\n  x\t1\n  y\t2\n"
        assert yq("--toon", "--toon-delimiter", "pipe", ".items", stdin=self.SAMPLE).stdout == "[2|]{n|v}:\n  x|1\n  y|2\n"
        r = yq("--toon", "--toon-delimiter", "semicolon", ".", stdin=self.SAMPLE)
        assert r.returncode == 1

    def test_toon_indent(self) -> None:
        assert yq("--toon", "-I", "4", ".", stdin="a:\n  b:\n    - {x: 1}\n").stdout == "a:\n    b[1]{x}:\n        1\n"

    def test_in_place_writes_toon_file(self) -> None:
        path = self.write("data.toon", "placeholder: 1\n")
        r = yq("-i", ".a = 2", path)
        assert r.returncode == 0, r.stderr
        assert Path(path).read_text(encoding="utf-8") == "placeholder: 1\na: 2\n"


class ToonInputTests(CliTestCase):
    TOON = "a: 1\nitems[2]{n,v}:\n  x,1\n  y,2\n"

    def test_extension_is_auto_detected(self) -> None:
        path = self.write("data.toon", self.TOON)
        # input and output default to the file's format
        assert yq(".", path).stdout == self.TOON
        assert yq(".items[1].n", path).stdout == "y\n"
        assert yq("-o", "yaml", ".", path).stdout == "a: 1\nitems:\n  - n: x\n    v: 1\n  - n: y\n    v: 2\n"
        assert yq("-o=j", "-I=0", ".items[0]", path).stdout == '{"n":"x","v":1}\n'

    def test_input_format_flag_with_stdin(self) -> None:
        assert yq("-p", "toon", "-o", "yaml", ".items[0].v", stdin=self.TOON).stdout == "1\n"
        # like Go, an explicit -p without -o falls back to yaml output
        assert yq("-p", "toon", ".a", stdin=self.TOON).stdout == "1\n"
        assert yq("-p", "toon", ".", stdin=self.TOON).stdout == "a: 1\nitems:\n  - n: x\n    v: 1\n  - n: y\n    v: 2\n"

    def test_comments_in_toon_input_are_ignored(self) -> None:
        assert yq("-p", "toon", "-o", "json", "-I", "0", ".",
                  stdin="# comment\na: 1\n  # another\nb[1]: x\n").stdout == '{"a":1,"b":["x"]}\n'

    def test_toon_syntax_error(self) -> None:
        r = yq("-p", "toon", ".", stdin="a: 1\nb[3]: x\n")
        assert r.returncode == 1
        assert "line 2" in r.stderr

    def test_eval_all_merges_toon_files(self) -> None:
        a = self.write("a.toon", "x: 1\n")
        b = self.write("b.toon", "y[2]: 1,2\n")
        r = yq("ea", "-o", "yaml", "select(fi == 0) * select(fi == 1)", a, b)
        assert r.stdout == "x: 1\ny:\n  - 1\n  - 2\n"

    def test_comments_are_dropped_silently(self) -> None:
        r = yq("--toon", ".", stdin="# head\na: 1 # line\n")
        assert (r.stdout, r.stderr) == ("a: 1\n", "")


class PrettyPrintTests(CliTestCase):
    def test_pretty_print_unquotes_and_expands(self) -> None:
        # "y" stays quoted because YAML 1.1 readers would treat it as a boolean (Go does the same)
        assert yq("-P", ".", stdin='a: {"b": "x", c: [1, "y", "z"]}\n').stdout == 'a:\n  b: x\n  c:\n    - 1\n    - "y"\n    - z\n'

    def test_pretty_print_keeps_ambiguous_strings_quoted(self) -> None:
        assert yq("-P", ".", stdin='a: "yes"\nb: "123"\n').stdout == 'a: "yes"\nb: "123"\n'


class NulSeparatorTests(CliTestCase):
    def test_nul_output(self) -> None:
        r = yq("-0", ".[]", stdin="- a\n- b\n")
        assert r.stdout == "a\0b\0"

    def test_nul_in_value_is_an_error(self) -> None:
        r = yq("-0", ".a", stdin='a: "x\\0y"\n')
        assert r.returncode == 1


class SplitTests(CliTestCase):
    """``-s`` / ``--split-exp``: ported from acceptance_tests/split-printer.sh and bad_args.sh."""

    DOCS = "a: test_doc1\n--- \na: test_doc2\n"

    def read(self, name: str) -> str:
        return (self.dir / name).read_text(encoding="utf-8")

    def check_named_docs(self, mode: str = "e") -> None:
        path = self.write("test.yml", self.DOCS)
        r = yq(mode, path, "-s", ".a", cwd=str(self.dir))
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
        assert self.read("test_doc1.yml") == "a: test_doc1\n"
        # the second file starts with the separator, as in Go
        assert self.read("test_doc2.yml") == "---\na: test_doc2\n"

    def test_basic_split_with_name(self) -> None:
        self.check_named_docs("e")

    def test_basic_split_with_name_eval_all(self) -> None:
        self.check_named_docs("ea")

    def test_custom_extension(self) -> None:
        path = self.write("test.yml", self.DOCS)
        yq("e", path, "-s", '.a + ".yaml"', cwd=str(self.dir))
        assert self.read("test_doc1.yaml") == "a: test_doc1\n"
        assert self.read("test_doc2.yaml") == "---\na: test_doc2\n"

    def test_expression_from_a_file(self) -> None:
        path = self.write("test.yml", self.DOCS)
        expression = self.write("test_splitExp.yml", ".a\n")
        r = yq(path, "--split-exp-file", expression, cwd=str(self.dir))
        assert r.returncode == 0, r.stderr
        assert self.read("test_doc1.yml") == "a: test_doc1\n"

    @pytest.mark.parametrize("mode", ("e", "ea"))
    def test_index_variable(self, mode) -> None:
        path = self.write("test.yml", self.DOCS)
        yq(mode, path, "-s", '"test_" + $index', cwd=str(self.dir))
        assert self.read("test_0.yml") == "a: test_doc1\n"
        assert self.read("test_1.yml") == "---\na: test_doc2\n"

    def test_array_items_without_separators(self) -> None:
        path = self.write("test.yml", "- name: test_fred\n  age: 35\n- name: test_catherine\n  age: 37\n")
        second = self.write("test2.yml", "- name: test_mike\n  age: 564\n")
        for mode in ("e", "ea"):
            r = yq(mode, "--no-doc", "-s", ".name", ".[]", path, second, cwd=str(self.dir))
            assert r.returncode == 0, r.stderr
            assert self.read("test_fred.yml") == "name: test_fred\nage: 35\n"
            assert self.read("test_catherine.yml") == "name: test_catherine\nage: 37\n"
            assert self.read("test_mike.yml") == "name: test_mike\nage: 564\n"

    def test_directories_are_created(self) -> None:
        path = self.write("test.yml", "f: test_dir1/test_file1\n---\nf: test_dir2/dir22/test_file2\n---\nf: test_file3\n")
        yq("e", "--no-doc", "-s", ".f", path, cwd=str(self.dir))
        assert self.read("test_dir1/test_file1.yml") == "f: test_dir1/test_file1\n"
        assert self.read("test_dir2/dir22/test_file2.yml") == "f: test_dir2/dir22/test_file2\n"
        assert self.read("test_file3.yml") == "f: test_file3\n"

    def test_the_extension_follows_the_output_format(self) -> None:
        path = self.write("test.yml", "a: one\n---\na: two\n")
        for fmt, ext in (("json", "json"), ("props", "properties"), ("xml", "xml"), ("toml", "toml")):
            r = yq("-o", fmt, "-s", '"out_" + $index', path, cwd=str(self.dir))
            assert r.returncode == 0, r.stderr
            assert (self.dir / f"out_0.{ext}").exists(), ext

    def test_the_json_file_holds_that_result(self) -> None:
        path = self.write("test.yml", "a: one\n---\na: two\n")
        yq("-o", "json", "-I0", "-s", ".a", path, cwd=str(self.dir))
        assert self.read("one.json") == '{"a":"one"}\n'

    def test_write_in_place_cannot_be_used_with_split(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        for mode in ("e", "ea"):
            r = yq(mode, "-s", "cat", "-i", '.a = "thing"', path)
            assert (r.returncode, r.stderr) == (1, "Error: write in place cannot be used with split file\n")

    def test_a_bad_split_expression(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        r = yq("-s", "!!!", path)
        assert r.returncode == 1
        assert r.stderr.startswith("Error: bad split document expression:"), r.stderr

    def test_a_name_with_dot_dot_is_refused(self) -> None:
        path = self.write("test.yml", "f: ../escaped\n")
        r = yq("-s", ".f", path, cwd=str(self.dir))
        assert r.returncode == 1
        assert "split file names must not contain '..'" in r.stderr
        assert not (self.dir.parent / "escaped.yml").exists()

    def test_file_operations_can_be_disabled(self) -> None:
        path = self.write("test.yml", "a: one\n")
        r = yq("--security-disable-file-ops", "-s", ".a", path, cwd=str(self.dir))
        assert (r.returncode, r.stderr) == (1, "Error: file operations have been disabled\n")
        assert not (self.dir / "one.yml").exists()

    def test_nothing_is_printed_to_stdout(self) -> None:
        path = self.write("test.yml", "a: one\n")
        assert yq("-s", ".a", path, cwd=str(self.dir)).stdout == ""


class BadArgsTests(CliTestCase):
    def test_bad_expression(self) -> None:
        r = yq(".a |", stdin="a: 1\n")
        assert r.returncode == 1
        assert r.stderr.startswith("Error:")

    def test_in_place_needs_file(self) -> None:
        r = yq("-i", ".a", stdin="a: 1\n")
        assert r.returncode == 1
        assert "write in place" in r.stderr

    def test_null_input_with_file(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        r = yq("-n", ".a", path)
        assert r.returncode == 1

    def test_negative_indent(self) -> None:
        r = yq("-I", "-1", ".", stdin="a: 1\n")
        assert r.returncode == 1
        assert "indent" in r.stderr

    def test_exit_status(self) -> None:
        assert yq("-e", ".a", stdin="a: 1\n").returncode == 0
        assert yq("-e", ".b", stdin="a: 1\n").returncode == 1
        assert yq("-e", ".a", stdin="a: false\n").returncode == 1

    def test_unknown_flag(self) -> None:
        r = yq("--nope", ".", stdin="a: 1\n")
        assert r.returncode == 1

    def test_version(self) -> None:
        r = yq("--version")
        assert r.returncode == 0
        assert "version" in r.stdout


class GuiFlagTests(CliTestCase):
    """`--gui` の入口だけを検査する（GUI 本体は起動しない: 起動前に必ず失敗する引数のみ使う）。"""

    def test_gui_flag_is_listed_in_help(self) -> None:
        r = yq("--help")
        assert r.returncode == 0
        assert "--gui" in r.stdout

    def test_gui_flag_rejects_an_expression(self) -> None:
        r = yq("--gui", ".a")
        assert r.returncode == 1
        assert "cannot be combined" in r.stderr

    def test_gui_flag_rejects_a_file(self) -> None:
        path = self.write("a.yaml", "a: 1\n")
        r = yq("--gui", path)
        assert r.returncode == 1
        assert "cannot be combined" in r.stderr


class SecurityTests(CliTestCase):
    def test_env_allowed_by_default_in_cli(self) -> None:
        env = dict(ENV, MYVAR="hello")
        r = subprocess.run([sys.executable, "-m", "yaqpy", "-n", "strenv(MYVAR)"], capture_output=True,
                           text=True, encoding="utf-8", env=env, timeout=120)
        assert r.stdout == "hello\n"

    def test_env_can_be_disabled(self) -> None:
        r = yq("-n", "--security-disable-env-ops", "strenv(HOME)")
        assert r.returncode == 1
        assert "disabled" in r.stderr


REQUEST = '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'


class RecipeTests(CliTestCase):
    """--recipe in a real process: the result goes to stdout, the report to stderr, exit codes."""

    def test_the_result_is_on_stdout_and_the_report_on_stderr(self) -> None:
        path = self.write("request.json", REQUEST)
        r = yq("--recipe", "openai-to-gemini", "-I", "0", path)
        assert r.returncode == 0
        assert r.stdout == '{"contents":[{"role":"user","parts":[{"text":"Hello"}]}]}\n'
        assert "dropped .model" in r.stderr
        assert "dropped .stream" in r.stderr

    def test_a_pipeline_gets_only_the_body(self) -> None:
        r = yq("--recipe", "openai-to-gemini", "-I", "0", stdin=REQUEST)
        assert r.returncode == 0
        assert r.stdout.startswith('{"contents"')
        assert "dropped" not in r.stdout

    def test_a_chain_of_two_recipes_through_a_pipe(self) -> None:
        first = yq("--recipe", "openai-to-gemini", "-I", "0", stdin=REQUEST)
        second = yq("--recipe", "gemini-to-anthropic", "-I", "0", stdin=first.stdout)
        assert second.returncode == 0
        assert second.stdout == ('{"messages":[{"role":"user","content":[{"type":"text","text":"Hello"}]}],'
                              '"max_tokens":4096}\n')
        assert "added .max_tokens = 4096" in second.stderr

    def test_report_and_recipe_test(self) -> None:
        path = self.write("request.json", REQUEST)
        r = yq("--recipe", "openai-to-anthropic", "--report", path)
        assert r.returncode == 0
        assert "Verdict: needs a look" in r.stdout
        assert r.stderr == ""
        t = yq("--recipe", "openai-to-anthropic", "--recipe-test")
        assert (t.returncode, t.stdout.splitlines()[-1]) == (0, "5/5 passed")

    def test_apply_writes_only_into_the_output_directory(self) -> None:
        path = self.write("request.json", REQUEST)
        out_dir = self.dir / "converted"
        r = yq("--recipe", "openai-to-gemini", "--apply", "--out-dir", str(out_dir), path)
        assert r.returncode == 0, r.stderr
        assert (out_dir / "request.json").exists()
        assert Path(path).read_text(encoding="utf-8") == REQUEST      # the input is untouched
        refused = yq("--recipe", "openai-to-gemini", "--apply", "--out-dir", str(self.dir), path)
        assert refused.returncode == 1
        assert Path(path).read_text(encoding="utf-8") == REQUEST

    def test_list_recipes_and_bad_use(self) -> None:
        listing = yq("--list-recipes")
        assert listing.returncode == 0
        assert "openai-to-gemini" in listing.stdout
        bad = yq("--recipe", "nope", self.write("x.json", "{}"))
        assert (bad.returncode, bad.stdout) == (1, "")
        assert "unknown recipe" in bad.stderr

    def test_a_recipe_cannot_read_the_environment(self) -> None:
        recipe = self.write("spy.yaqpy", "env(HOME)")
        r = yq("--recipe", recipe, self.write("x.json", "{}"))
        assert r.returncode == 1
        assert "env operations have been disabled" in r.stderr


class DescribeTests(CliTestCase):
    @pytest.mark.parametrize("flag, start", (("--print-spec", "# yaqpy 式の仕様"), ("--example", "# yaqpy の使用例"),
                        ("--guide-prompt", "# yaqpy の式を書いてください"),
                        ("--skill-md", "---\nname: yaqpy\n")))
    def test_each_flag_prints_and_exits_zero_from_an_empty_directory(self, flag, start) -> None:
        r = yq(flag, cwd=str(self.dir))
        assert (r.returncode, r.stderr) == (0, "")
        assert r.stdout.startswith(start)

    def test_the_skill_can_be_placed_and_its_example_commands_run(self) -> None:
        skill = yq("--skill-md").stdout
        target = self.dir / ".claude" / "skills" / "yaqpy" / "SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text(skill, encoding="utf-8", newline="\n")
        assert target.read_text(encoding="utf-8").startswith("---\nname: yaqpy\n")
        data = self.write("shop.yaml", "server:\n  port: 8080\nitems:\n  - {name: pen, price: 120}\n"
                                       "  - {name: cap, price: 80}\n")
        assert yq(".server.port", data).stdout == "8080\n"           # the first example of the skill
        assert yq(".items[] | select(.price > 100) | .name", data).stdout == "pen\n"

    def test_prune_flags_in_a_real_process(self) -> None:
        r = yq("-o", "json", "-I", "0", "--prune-null", "--prune-empty", stdin='{"a": null, "b": {}, "d": 1}')
        assert (r.returncode, r.stdout) == (0, '{"d":1}\n')
