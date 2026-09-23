"""``yaqpy --web`` フラグのテスト（v0.6.0。サーバーは起動しない）。

``yaqpy --web`` の後ろの引数は ``yaqpy-web`` と同じに扱う（要望）。``gui.app.web_entry`` を
モックに差し替えるので、flet-web が入っていてもサーバーは立たない。
"""

from __future__ import annotations

import io
from unittest import mock

import pytest

from yaqpy.cli.main import main
from yaqpy.cli.parser import build_parser
from yaqpy.gui.web_config import WebConfig


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class DelegationTests:
    def test_defaults(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry", return_value=0) as entry:
            code, _, _ = run("--web")
        assert code == 0
        assert entry.call_args.args[0] == WebConfig()

    def test_port_after_web(self) -> None:
        """要望：yaqpy --web でもポート番号を指定できる。"""
        with mock.patch("yaqpy.gui.app.web_entry", return_value=0) as entry:
            run("--web", "--port", "9000")
        assert entry.call_args.args[0].port == 9000

    def test_every_yaqpy_web_option_works(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry", return_value=0) as entry:
            run("--web", "--host", "0.0.0.0", "--port", "9001", "--lang", "en", "--no-browser",
                "--no-cdn", "--max-input-mib", "3", "--timeout", "4", "--max-concurrent-runs", "5")
        assert entry.call_args.args[0] == WebConfig(
            host="0.0.0.0", port=9001, language="en", open_browser=False, use_cdn=False,
            max_input_mib=3, timeout_seconds=4.0, max_concurrent_runs=5)

    def test_options_may_come_before_web(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry", return_value=0) as entry:
            run("--port", "9002", "--web")
        assert entry.call_args.args[0].port == 9002

    def test_the_exit_code_comes_back(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry", return_value=1):
            assert run("--web")[0] == 1


class RefusalTests:
    def test_gui_and_web_together(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry") as entry:
            code, _, err = run("--gui", "--web")
        assert code == 1
        assert "--gui and --web" in err
        entry.assert_not_called()

    @pytest.mark.parametrize("argv", [(".a",), ("a.yaml",), ("-o", "json")])
    def test_expressions_files_and_yaqpy_options_are_not_web_options(
            self, argv: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> None:
        """Web 版はサーバー側のファイルを開かない。yaqpy 本体のオプションも受け付けない。"""
        with mock.patch("yaqpy.gui.app.web_entry") as entry:
            code, _, _ = run("--web", *argv)
        assert code == 1
        entry.assert_not_called()
        capsys.readouterr()

    def test_a_bad_port(self) -> None:
        with mock.patch("yaqpy.gui.app.web_entry") as entry:
            code, _, err = run("--web", "--port", "0")
        assert code == 1
        assert "--port" in err
        entry.assert_not_called()


class HelpTests:
    def test_yaqpy_help_describes_gui_and_web_and_points_to_the_details(self) -> None:
        """要望：yaqpy --help に --gui と --web の説明。詳しいオプションは各コマンドのヘルプへ。"""
        text = build_parser().format_help()
        assert "--gui" in text and "--web" in text
        assert "yaqpy-gui --help" in text and "yaqpy-web --help" in text
        assert "127.0.0.1:8550" in text
        assert "yaqpy --web --port 9000" in text

    def test_web_help_through_yaqpy(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _, _ = run("--web", "--help")
        out = capsys.readouterr().out
        assert code == 0
        assert out.startswith("usage: yaqpy --web")
        assert "--port" in out
