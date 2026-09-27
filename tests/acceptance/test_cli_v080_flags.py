"""New v0.8.0 CLI flags (E6, 0926-03 3-12): --arg/--argjson/--args/--jsonargs, --slurp,
--compact-output, --tab, -S/--sort-keys.
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


class ArgTests(CliTestCase):
    def test_arg_binds_a_string_variable(self) -> None:
        r = yq("-n", "--arg", "name", "world", "$name")
        assert (r.returncode, r.stdout) == (0, "world\n")

    def test_argjson_binds_a_parsed_value(self) -> None:
        r = yq("-n", "--argjson", "n", "42", "$n + 1")
        assert (r.returncode, r.stdout) == (0, "43\n")

    def test_args_are_folded_into_args_named(self) -> None:
        r = yq("-n", "-o", "json", "--compact-output", "--arg", "a", "1", "--argjson", "b", "2",
              "$ARGS.named")
        assert (r.returncode, r.stdout) == (0, '{"a":"1","b":2}\n')

    def test_a_repeated_name_keeps_only_the_last(self) -> None:
        r = yq("-n", "--arg", "x", "one", "--arg", "x", "two", "$x")
        assert (r.returncode, r.stdout) == (0, "two\n")


class PositionalArgsTests(CliTestCase):
    def test_args_fills_positional_with_strings(self) -> None:
        r = yq("-n", "-o", "json", "--compact-output", "$ARGS.positional", "--args", "a", "b", "c")
        assert (r.returncode, r.stdout) == (0, '["a","b","c"]\n')

    def test_jsonargs_fills_positional_with_parsed_values(self) -> None:
        r = yq("-n", "-o", "json", "--compact-output", "$ARGS.positional", "--jsonargs", "1",
              "true", '"s"')
        assert (r.returncode, r.stdout) == (0, '[1,true,"s"]\n')

    def test_nothing_after_args_is_read_as_a_file(self) -> None:
        # a name that would fail to open as a file must not raise "no such file"
        r = yq("-n", ".", "--args", "definitely-not-a-real-file.yaml")
        assert r.returncode == 0


class SlurpTests(CliTestCase):
    def test_slurp_wraps_every_input_in_one_array(self) -> None:
        a = self.write("a.yaml", "1\n")
        b = self.write("b.yaml", "2\n")
        r = yq("-o", "json", "--compact-output", "--slurp", ".", a, b)
        assert (r.returncode, r.stdout) == (0, "[1,2]\n")

    def test_slurp_differs_from_eval_all(self) -> None:
        a = self.write("a.yaml", "1\n")
        b = self.write("b.yaml", "2\n")
        slurped = yq("-o", "json", "--compact-output", "--slurp", ".", a, b).stdout
        eval_all = yq("ea", "-o", "json", "--compact-output", ".", a, b).stdout
        assert slurped == "[1,2]\n"
        assert eval_all != slurped


class OutputFlagTests(CliTestCase):
    def test_compact_output_is_one_line_json(self) -> None:
        path = self.write("in.yaml", "a: 1\nb: 2\n")
        r = yq("-o", "json", "--compact-output", ".", path)
        assert (r.returncode, r.stdout) == (0, '{"a":1,"b":2}\n')

    def test_tab_indents_json_with_tabs(self) -> None:
        path = self.write("in.yaml", "a: 1\n")
        r = yq("-o", "json", "--tab", ".", path)
        assert r.returncode == 0
        assert r.stdout == '{\n\t"a": 1\n}\n'

    def test_sort_keys_sorts_every_level(self) -> None:
        path = self.write("in.json", '{"b": 1, "a": {"z": 1, "y": 2}}\n')
        r = yq("-p", "json", "-S", ".", path)
        assert r.returncode == 0
        assert r.stdout == "a:\n  y: 2\n  z: 1\nb: 1\n"
