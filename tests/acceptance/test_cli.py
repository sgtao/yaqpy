"""CLI acceptance tests, ported from yq's ``acceptance_tests/*.sh`` (phase 1 subset).

Each test runs ``python -m pyyq`` in a subprocess so exit codes, stdin handling
and file writes are exercised for real.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def yq(*args: str, stdin: str | None = None, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pyyq", *args], input=stdin, capture_output=True, text=True,
        encoding="utf-8", env=ENV, cwd=cwd, timeout=120,
    )


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> str:
        path = self.dir / name
        path.write_text(text, encoding="utf-8", newline="")
        return str(path)


class BasicTests(CliTestCase):
    def test_round_trip_with_null_input(self) -> None:
        r = yq("-n", ".a = 123")
        self.assertEqual((r.returncode, r.stdout), (0, "a: 123\n"))
        path = self.write("test.yml", r.stdout)
        r = yq(".a", path)
        self.assertEqual(r.stdout, "123\n")

    def test_trailing_comment_and_foot_comment(self) -> None:
        path = self.write("t.yml", "test:\n# this comment will be removed\n")
        self.assertEqual(yq(path, "-P").stdout, "test:\n# this comment will be removed\n")
        self.assertEqual(yq('. footComment = "hi"', path).stdout, "test:\n# hi\n")
        self.assertEqual(yq("ea", '. footComment = "hi"', path).stdout, "test:\n# hi\n")

    def test_pipe_with_dot(self) -> None:
        self.assertEqual(yq(".", stdin="a: 123\n").stdout, "a: 123\n")

    def test_expression_flag_when_file_looks_like_expression(self) -> None:
        path = self.write("test.yml", "xyz: 123\n")
        self.assertEqual(yq("--expression", ".xyz", path).stdout, "123\n")
        self.assertEqual(yq("ea", "--expression", ".xyz", path).stdout, "123\n")

    def test_expression_from_file_including_dos_line_endings(self) -> None:
        data = self.write("test.yml", "xyz: 123\n")
        for ending in ("\n", "\r\n"):
            instructions = self.write("instructions.txt", '.xyz = "meow" | .cool = "frog"' + ending)
            r = yq("--from-file", instructions, data, "-o=j", "-I=0")
            self.assertEqual(r.stdout, '{"xyz":"meow","cool":"frog"}\n')
            r = yq("ea", "--from-file", instructions, data, "-o=j", "-I=0")
            self.assertEqual(r.stdout, '{"xyz":"meow","cool":"frog"}\n')

    def test_github_action_style_stdin(self) -> None:
        path = self.write("test.yml", "a: 123\n")
        # stdin is a pipe (empty) but a file is given: read the file, not stdin
        self.assertEqual(yq(path, stdin="").stdout, "a: 123\n")
        self.assertEqual(yq("e", path, stdin="").stdout, "a: 123\n")
        self.assertEqual(yq("ea", path, stdin="").stdout, "a: 123\n")
        self.assertEqual(yq(".a", path, stdin="").stdout, "123\n")

    def test_eval_all_files(self) -> None:
        a = self.write("a.yml", "a: 123\n")
        b = self.write("b.yml", "a: 124\n")
        self.assertEqual(yq("ea", a, b).stdout, yq("e", ".", a, b).stdout)
        self.assertEqual(yq("ea", a, b).stdout, "a: 123\n---\na: 124\n")

    def test_in_place(self) -> None:
        path = self.write("test.yml", "a: 1 # keep\nb: 2\n")
        r = yq("-i", ".a = 5", path)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "a: 5 # keep\nb: 2\n")

    def test_in_place_failure_leaves_file(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        r = yq("-i", ".a + {}", path)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "a: 1\n")


class EmptyInputTests(CliTestCase):
    def test_comment_only_file(self) -> None:
        path = self.write("test.yml", "# comment\n")
        self.assertEqual(yq("e", path).stdout, "# comment\n")
        self.assertEqual(yq("e", '.apple = "tree"', path).stdout, "# comment\napple: tree\n")
        self.assertEqual(yq("ea", '.apple = "tree"', path).stdout, "# comment\napple: tree\n")

    def test_comment_only_no_newline(self) -> None:
        path = self.write("test.yml", "#comment")
        self.assertEqual(yq("e", path).stdout, "#comment\n")

    def test_empty_file(self) -> None:
        path = self.write("test.yml", "")
        self.assertEqual(yq("e", '.apple = "tree"', path).stdout, "apple: tree\n")
        self.assertEqual(yq("ea", '.apple = "tree"', path).stdout, "apple: tree\n")


class LeadingSeparatorTests(CliTestCase):
    def test_separator_is_kept(self) -> None:
        path = self.write("test.yml", "---\na: 1\n")
        self.assertEqual(yq(path).stdout, "---\na: 1\n")
        self.assertEqual(yq("-N", path).stdout, "a: 1\n")

    def test_directive_and_comment_before_separator(self) -> None:
        path = self.write("test.yml", "%YAML 1.1\n# hi\n---\na: 1\n")
        self.assertEqual(yq(path).stdout, "%YAML 1.1\n# hi\n---\na: 1\n")

    def test_multiple_documents(self) -> None:
        path = self.write("test.yml", "a: 1\n---\nb: 2\n")
        self.assertEqual(yq(".", path).stdout, "a: 1\n---\nb: 2\n")
        self.assertEqual(yq("-N", ".", path).stdout, "a: 1\nb: 2\n")


class OutputFormatTests(CliTestCase):
    def test_auto_format_from_extension(self) -> None:
        path = self.write("test.json", '{"a": [1, 2]}')
        self.assertEqual(yq(".a[0]", path).stdout, "1\n")
        self.assertEqual(yq(".", path).stdout, '{\n  "a": [\n    1,\n    2\n  ]\n}\n')
        self.assertEqual(yq("-oy", ".", path).stdout, "a:\n  - 1\n  - 2\n")

    def test_explicit_input_format_defaults_output_to_yaml(self) -> None:
        path = self.write("test.json", '{"a": 1}')
        r = yq("-p", "json", ".", path)
        self.assertEqual(r.stdout, "a: 1\n")

    def test_json_indent_zero(self) -> None:
        self.assertEqual(yq("-o=j", "-I=0", ".", stdin="a: [1, {b: x}]\n").stdout,
                         '{"a":[1,{"b":"x"}]}\n')

    def test_props(self) -> None:
        self.assertEqual(yq("-o=props", ".", stdin="a:\n  b: 1\n  c: [x, y]\n").stdout,
                         "a.b = 1\na.c.0 = x\na.c.1 = y\n")

    def test_unwrap_scalar_flag(self) -> None:
        self.assertEqual(yq(".a", stdin='a: "x"\n').stdout, "x\n")
        self.assertEqual(yq("-r=false", ".a", stdin='a: "x"\n').stdout, '"x"\n')
        self.assertEqual(yq("-o=json", ".a", stdin='a: "x"\n').stdout, '"x"\n')
        self.assertEqual(yq("-o=json", "-r", ".a", stdin='a: "x"\n').stdout, "x\n")

    def test_unknown_format(self) -> None:
        r = yq("-o", "hcl", ".", stdin="a: 1\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("unknown format", r.stderr)


class ToonOutputTests(CliTestCase):
    SAMPLE = "a: 1 # comment\nitems:\n  - n: x\n    v: 1\n  - n: y\n    v: 2\n"
    EXPECTED = "a: 1\nitems[2]{n,v}:\n  x,1\n  y,2\n"

    def test_output_format_toon(self) -> None:
        self.assertEqual(yq("-o", "toon", ".", stdin=self.SAMPLE).stdout, self.EXPECTED)
        self.assertEqual(yq("-o=toon", ".items[0].n", stdin=self.SAMPLE).stdout, "x\n")

    def test_toon_flag_is_shorthand(self) -> None:
        r = yq("--toon", ".", stdin=self.SAMPLE)
        self.assertEqual((r.returncode, r.stdout), (0, self.EXPECTED))
        # order does not matter and it composes with the eval subcommand
        self.assertEqual(yq("e", ".", "--toon", stdin=self.SAMPLE).stdout, self.EXPECTED)

    def test_toon_flag_conflicts_with_other_output_format(self) -> None:
        r = yq("--toon", "-o", "json", ".", stdin=self.SAMPLE)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--toon cannot be combined", r.stderr)
        # the same format twice is fine
        self.assertEqual(yq("--toon", "-o", "toon", ".", stdin=self.SAMPLE).returncode, 0)

    def test_toon_delimiter(self) -> None:
        self.assertEqual(yq("--toon", "--toon-delimiter", "tab", ".items", stdin=self.SAMPLE).stdout,
                         "[2\t]{n\tv}:\n  x\t1\n  y\t2\n")
        self.assertEqual(yq("--toon", "--toon-delimiter", "pipe", ".items", stdin=self.SAMPLE).stdout,
                         "[2|]{n|v}:\n  x|1\n  y|2\n")
        r = yq("--toon", "--toon-delimiter", "semicolon", ".", stdin=self.SAMPLE)
        self.assertEqual(r.returncode, 1)

    def test_toon_indent(self) -> None:
        self.assertEqual(yq("--toon", "-I", "4", ".", stdin="a:\n  b:\n    - {x: 1}\n").stdout,
                         "a:\n    b[1]{x}:\n        1\n")

    def test_in_place_writes_toon_file(self) -> None:
        path = self.write("data.toon", "placeholder: 1\n")
        # the .toon extension is not an input format yet, so read explicitly as yaml
        r = yq("-i", "-p", "yaml", "--toon", ".a = 2", path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "placeholder: 1\na: 2\n")

    def test_comments_are_dropped_silently(self) -> None:
        r = yq("--toon", ".", stdin="# head\na: 1 # line\n")
        self.assertEqual((r.stdout, r.stderr), ("a: 1\n", ""))


class PrettyPrintTests(CliTestCase):
    def test_pretty_print_unquotes_and_expands(self) -> None:
        # "y" stays quoted because YAML 1.1 readers would treat it as a boolean (Go does the same)
        self.assertEqual(yq("-P", ".", stdin='a: {"b": "x", c: [1, "y", "z"]}\n').stdout,
                         'a:\n  b: x\n  c:\n    - 1\n    - "y"\n    - z\n')

    def test_pretty_print_keeps_ambiguous_strings_quoted(self) -> None:
        self.assertEqual(yq("-P", ".", stdin='a: "yes"\nb: "123"\n').stdout,
                         'a: "yes"\nb: "123"\n')


class NulSeparatorTests(CliTestCase):
    def test_nul_output(self) -> None:
        r = yq("-0", ".[]", stdin="- a\n- b\n")
        self.assertEqual(r.stdout, "a\0b\0")

    def test_nul_in_value_is_an_error(self) -> None:
        r = yq("-0", ".a", stdin='a: "x\\0y"\n')
        self.assertEqual(r.returncode, 1)


class BadArgsTests(CliTestCase):
    def test_bad_expression(self) -> None:
        r = yq(".a |", stdin="a: 1\n")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("Error:"))

    def test_in_place_needs_file(self) -> None:
        r = yq("-i", ".a", stdin="a: 1\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("write in place", r.stderr)

    def test_null_input_with_file(self) -> None:
        path = self.write("test.yml", "a: 1\n")
        r = yq("-n", ".a", path)
        self.assertEqual(r.returncode, 1)

    def test_negative_indent(self) -> None:
        r = yq("-I", "-1", ".", stdin="a: 1\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("indent", r.stderr)

    def test_exit_status(self) -> None:
        self.assertEqual(yq("-e", ".a", stdin="a: 1\n").returncode, 0)
        self.assertEqual(yq("-e", ".b", stdin="a: 1\n").returncode, 1)
        self.assertEqual(yq("-e", ".a", stdin="a: false\n").returncode, 1)

    def test_unknown_flag(self) -> None:
        r = yq("--nope", ".", stdin="a: 1\n")
        self.assertEqual(r.returncode, 1)

    def test_version(self) -> None:
        r = yq("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("version", r.stdout)


class SecurityTests(CliTestCase):
    def test_env_allowed_by_default_in_cli(self) -> None:
        env = dict(ENV, MYVAR="hello")
        r = subprocess.run([sys.executable, "-m", "pyyq", "-n", "strenv(MYVAR)"], capture_output=True,
                           text=True, encoding="utf-8", env=env, timeout=120)
        self.assertEqual(r.stdout, "hello\n")

    def test_env_can_be_disabled(self) -> None:
        r = yq("-n", "--security-disable-env-ops", "strenv(HOME)")
        self.assertEqual(r.returncode, 1)
        self.assertIn("disabled", r.stderr)


if __name__ == "__main__":
    unittest.main()
