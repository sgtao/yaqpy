"""``yaqpy --gui`` フラグのテスト（GUI を実際に起動しない）。

main_entry はモックに差し替えるので、flet が入っている環境でもウィンドウは開かない。
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest import mock

from yaqpy.cli.main import main
from yaqpy.cli.parser import build_parser, parse_args


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ParseTests:
    def test_default_is_off(self) -> None:
        assert not parse_args([".a"]).gui

    def test_flag_is_parsed(self) -> None:
        ns = parse_args(["--gui"])
        assert ns.gui
        assert ns.args == []

    def test_flag_is_documented_in_help(self) -> None:
        assert "--gui" in build_parser().format_help()


class DelegationTests:
    def test_delegates_to_the_gui_entry_point(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            code, out, _ = run("--gui")
        assert code == 0
        entry.assert_called_once()
        assert out == ""

    def test_the_gui_exit_code_is_propagated(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=7):
            code, _, _ = run("--gui")
        assert code == 7

    def test_stderr_is_handed_over_for_the_install_hint(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            run("--gui")
        assert "stderr" in entry.call_args.kwargs

    def test_missing_flet_prints_the_install_hint(self) -> None:
        """flet が無い環境の再現。実物の main_entry を通すが、起動はしない。"""
        with mock.patch("yaqpy.gui.app.flet_available", return_value=False):
            code, out, err = run("--gui")
        assert code == 1
        assert 'pip install "flet>=1.0,<2"' in err
        assert "uv sync --extra gui" in err
        assert out == ""

    def test_version_flag_still_wins(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, _ = run("--gui", "-V")
        assert code == 0
        assert "version" in out
        entry.assert_not_called()


class RejectionTests:
    """--gui と式・複数ファイルの併用は、黙って無視せずエラーにする。"""

    def _assert_rejected(self, *argv: str) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, err = run(*argv)
        assert code == 1
        assert "cannot be combined" in err
        assert out == ""
        entry.assert_not_called()

    def test_expression_and_file(self) -> None:
        self._assert_rejected("--gui", ".a", "sample.yaml")

    def test_expression_flag(self) -> None:
        self._assert_rejected("--gui", "--expression", ".a")

    def test_from_file_flag(self) -> None:
        self._assert_rejected("--gui", "--from-file", "expr.yq")

    def test_two_files(self) -> None:
        """--gui 自体が起動時に開けるのは 1 件だけ（複数開くには GUI 内の [＋追加]。U3）。"""
        self._assert_rejected("--gui", "a.yaml", "b.yaml")

    def test_a_single_argument_that_is_not_a_real_file(self) -> None:
        """存在しないパスは、打ち間違えた式かもしれないので開かずに断る。"""
        self._assert_rejected("--gui", ".a")


class StartupFileTests:
    """``yaqpy --gui a.yaml`` は、その 1 ファイルを開いた状態で起動する（U2、設計書 Q8）。"""

    def test_a_real_file_is_passed_through_as_the_initial_path(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.yaml"
        path.write_text("a: 1\n", encoding="utf-8")
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            code, out, err = run("--gui", str(path))
        assert code == 0
        assert out == err == ""
        assert entry.call_args.kwargs["initial_path"] == str(path)

    def test_no_file_means_no_initial_path(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            run("--gui")
        assert entry.call_args.kwargs["initial_path"] is None
