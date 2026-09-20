"""``yaqpy --gui`` フラグのテスト（GUI を実際に起動しない）。

main_entry はモックに差し替えるので、flet が入っている環境でもウィンドウは開かない。
"""

from __future__ import annotations

import io
import unittest
from unittest import mock

from yaqpy.cli.main import main
from yaqpy.cli.parser import build_parser, parse_args


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_default_is_off(self) -> None:
        self.assertFalse(parse_args([".a"]).gui)

    def test_flag_is_parsed(self) -> None:
        ns = parse_args(["--gui"])
        self.assertTrue(ns.gui)
        self.assertEqual(ns.args, [])

    def test_flag_is_documented_in_help(self) -> None:
        self.assertIn("--gui", build_parser().format_help())


class DelegationTests(unittest.TestCase):
    def test_delegates_to_the_gui_entry_point(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            code, out, _ = run("--gui")
        self.assertEqual(code, 0)
        entry.assert_called_once()
        self.assertEqual(out, "")

    def test_the_gui_exit_code_is_propagated(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=7):
            code, _, _ = run("--gui")
        self.assertEqual(code, 7)

    def test_stderr_is_handed_over_for_the_install_hint(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            run("--gui")
        self.assertIn("stderr", entry.call_args.kwargs)

    def test_missing_flet_prints_the_install_hint(self) -> None:
        """flet が無い環境の再現。実物の main_entry を通すが、起動はしない。"""
        with mock.patch("yaqpy.gui.app.flet_available", return_value=False):
            code, out, err = run("--gui")
        self.assertEqual(code, 1)
        self.assertIn('pip install "flet>=1.0,<2"', err)
        self.assertIn("uv sync --extra gui", err)
        self.assertEqual(out, "")

    def test_version_flag_still_wins(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, _ = run("--gui", "-V")
        self.assertEqual(code, 0)
        self.assertIn("version", out)
        entry.assert_not_called()


class RejectionTests(unittest.TestCase):
    """--gui と式・ファイルの併用は、黙って無視せずエラーにする。"""

    def _assert_rejected(self, *argv: str) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, err = run(*argv)
        self.assertEqual(code, 1)
        self.assertIn("cannot be combined", err)
        self.assertEqual(out, "")
        entry.assert_not_called()

    def test_positional_file(self) -> None:
        self._assert_rejected("--gui", "sample.yaml")

    def test_expression_and_file(self) -> None:
        self._assert_rejected("--gui", ".a", "sample.yaml")

    def test_expression_flag(self) -> None:
        self._assert_rejected("--gui", "--expression", ".a")

    def test_from_file_flag(self) -> None:
        self._assert_rejected("--gui", "--from-file", "expr.yq")


if __name__ == "__main__":
    unittest.main()
