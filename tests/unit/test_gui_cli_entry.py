"""``yaqpy-gui [FILE]`` と ``yaqpy-web [...]`` の引数とヘルプのテスト（v0.6.0）。
窓もサーバーも起動しない。"""

from __future__ import annotations

import io
from pathlib import Path
from unittest import mock

import pytest

from yaqpy.gui import app, texts
from yaqpy.gui.web_config import WebConfig


def run_gui(argv: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    return app.cli_entry(argv, stderr=err), err.getvalue()


def run_web(argv: list[str], **kwargs: str) -> tuple[int, str]:
    err = io.StringIO()
    return app.web_cli_entry(argv, stderr=err, **kwargs), err.getvalue()


class GuiEntryTests:
    """yaqpy-gui はデスクトップ専用。"""

    def test_no_arguments_opens_the_window(self) -> None:
        with mock.patch.object(app, "main_entry", return_value=0) as main_entry:
            code, _ = run_gui([])
        assert code == 0
        assert main_entry.call_args.kwargs["initial_path"] is None

    def test_an_existing_file_is_opened(self, tmp_path: Path) -> None:
        target = tmp_path / "a.yaml"
        target.write_text("a: 1\n", encoding="utf-8")
        with mock.patch.object(app, "main_entry", return_value=0) as main_entry:
            code, _ = run_gui([str(target)])
        assert code == 0
        assert main_entry.call_args.kwargs["initial_path"] == str(target)

    def test_a_missing_file_is_an_argument_error(self) -> None:
        with mock.patch.object(app, "main_entry") as main_entry:
            code, err = run_gui(["no-such-file.yaml"])
        assert code == 1
        assert "not a file" in err
        main_entry.assert_not_called()

    def test_web_is_not_an_option_of_yaqpy_gui(self) -> None:
        with mock.patch.object(app, "main_entry") as main_entry:
            code, err = run_gui(["--web"])
        assert code == 1
        assert "yaqpy-web" in err                          # どちらを使えばよいかを案内する
        main_entry.assert_not_called()

    @pytest.mark.parametrize("argv", [["--port", "9000"], ["--host", "0.0.0.0"]])
    def test_web_options_are_unknown_to_yaqpy_gui(self, argv: list[str],
                                                  capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(app, "main_entry") as main_entry:
            code, _ = run_gui(argv)
        assert code == 1
        main_entry.assert_not_called()
        capsys.readouterr()


class WebEntryTests:
    def test_defaults(self) -> None:
        with mock.patch.object(app, "web_entry", return_value=0) as web_entry:
            code, _ = run_web([])
        assert code == 0
        assert web_entry.call_args.args[0] == WebConfig()     # 127.0.0.1:8550、ブラウザを開く

    def test_port(self) -> None:
        """要望：Web の起動時にポート番号を指定できる。"""
        with mock.patch.object(app, "web_entry", return_value=0) as web_entry:
            run_web(["--port", "9000"])
        assert web_entry.call_args.args[0].port == 9000
        assert web_entry.call_args.args[0].url == "http://127.0.0.1:9000/"

    def test_options_reach_the_config(self) -> None:
        with mock.patch.object(app, "web_entry", return_value=0) as web_entry:
            run_web(["--host", "0.0.0.0", "--port", "9000", "--lang", "en", "--no-browser",
                     "--no-cdn", "--max-input-mib", "4", "--timeout", "2.5",
                     "--max-concurrent-runs", "3"])
        config = web_entry.call_args.args[0]
        assert config == WebConfig(host="0.0.0.0", port=9000, language="en", open_browser=False,
                                   use_cdn=False, max_input_mib=4, timeout_seconds=2.5,
                                   max_concurrent_runs=3)
        assert config.exposed

    def test_a_file_cannot_be_served_from_the_server_disk(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(app, "web_entry") as web_entry:
            code, _ = run_web(["pyproject.toml"])
        assert code == 1
        web_entry.assert_not_called()
        capsys.readouterr()

    @pytest.mark.parametrize("argv, flag", [(["--port", "0"], "--port"),
                                            (["--port", "70000"], "--port"),
                                            (["--max-input-mib", "0"], "--max-input-mib")])
    def test_a_bad_value_is_an_argument_error(self, argv: list[str], flag: str) -> None:
        with mock.patch.object(app, "web_entry") as web_entry:
            code, err = run_web(argv)
        assert code == 1
        assert flag in err
        web_entry.assert_not_called()

    def test_missing_flet_web_gives_an_install_hint(self) -> None:
        err = io.StringIO()
        with mock.patch.object(app, "flet_web_available", return_value=False):
            code = app.web_entry(WebConfig(), stderr=err)
        texts.select_language("ja")
        assert code == 1
        assert 'pip install "flet[web]>=1.0,<2"' in err.getvalue()
        assert "uv sync --extra web" in err.getvalue()


class HelpTests:
    """要望：yaqpy-gui と yaqpy-web のヘルプは別々（それぞれ自分の使い方だけを出す）。"""

    def _help(self, entry, capsys: pytest.CaptureFixture[str], **kwargs: str) -> str:
        assert entry(["--help"], stderr=io.StringIO(), **kwargs) == 0
        return capsys.readouterr().out

    def test_gui_help_is_about_the_desktop(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = self._help(app.cli_entry, capsys)
        assert out.startswith("usage: yaqpy-gui")
        assert "desktop" in out
        for web_only in ("--port", "--host", "--no-cdn", "--max-concurrent-runs"):
            assert web_only not in out
        assert "yaqpy-web --help" in out                   # もう一方への道しるべ

    def test_web_help_is_about_the_browser(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = self._help(app.web_cli_entry, capsys)
        assert out.startswith("usage: yaqpy-web")
        for option in ("--host", "--port", "--lang", "--no-browser", "--no-cdn",
                       "--max-input-mib", "--timeout", "--max-concurrent-runs"):
            assert option in out
        assert "127.0.0.1" in out and "8550" in out
        assert "yaqpy-gui --help" in out

    def test_web_help_through_yaqpy_names_that_command(
            self, capsys: pytest.CaptureFixture[str]) -> None:
        out = self._help(app.web_cli_entry, capsys, prog="yaqpy --web")
        assert out.startswith("usage: yaqpy --web")

    def test_unknown_option_is_1_not_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert run_web(["--nope"])[0] == 1
        assert run_gui(["--nope"])[0] == 1
        capsys.readouterr()
