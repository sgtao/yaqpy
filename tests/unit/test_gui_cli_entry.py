"""``yaqpy-gui [FILE] [--web ...]`` の引数のテスト（v0.6.0）。窓もサーバーも起動しない。"""

from __future__ import annotations

import io
from pathlib import Path
from unittest import mock

import pytest

from yaqpy.gui import app, texts
from yaqpy.gui.web_config import WebConfig


def run(argv: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    return app.cli_entry(argv, stderr=err), err.getvalue()


class DesktopTests:
    def test_no_arguments_opens_the_window(self) -> None:
        with mock.patch.object(app, "main_entry", return_value=0) as main_entry:
            code, _ = run([])
        assert code == 0
        assert main_entry.call_args.kwargs["initial_path"] is None

    def test_an_existing_file_is_opened(self, tmp_path: Path) -> None:
        target = tmp_path / "a.yaml"
        target.write_text("a: 1\n", encoding="utf-8")
        with mock.patch.object(app, "main_entry", return_value=0) as main_entry:
            code, _ = run([str(target)])
        assert code == 0
        assert main_entry.call_args.kwargs["initial_path"] == str(target)

    def test_a_missing_file_is_an_argument_error(self) -> None:
        with mock.patch.object(app, "main_entry") as main_entry:
            code, err = run(["no-such-file.yaml"])
        assert code == 1
        assert "not a file" in err
        main_entry.assert_not_called()

    @pytest.mark.parametrize("argv", [["--host", "0.0.0.0"], ["--port", "9000"],
                                      ["--lang", "en"], ["--no-browser"], ["--no-cdn"],
                                      ["--max-input-mib", "5"], ["--timeout", "3"],
                                      ["--max-concurrent-runs", "3"]])
    def test_web_only_options_need_web(self, argv: list[str]) -> None:
        with mock.patch.object(app, "main_entry") as main_entry:
            code, err = run(argv)
        assert code == 1
        assert argv[0] in err and "--web" in err
        main_entry.assert_not_called()


class WebTests:
    def test_defaults(self) -> None:
        with mock.patch.object(app, "web_entry", return_value=0) as web_entry:
            code, _ = run(["--web"])
        assert code == 0
        assert web_entry.call_args.args[0] == WebConfig()     # 127.0.0.1:8550、ブラウザを開く

    def test_options_reach_the_config(self) -> None:
        with mock.patch.object(app, "web_entry", return_value=0) as web_entry:
            run(["--web", "--host", "0.0.0.0", "--port", "9000", "--lang", "en", "--no-browser",
                 "--no-cdn", "--max-input-mib", "4", "--timeout", "2.5",
                 "--max-concurrent-runs", "3"])
        config = web_entry.call_args.args[0]
        assert config == WebConfig(host="0.0.0.0", port=9000, language="en", open_browser=False,
                                   use_cdn=False, max_input_mib=4, timeout_seconds=2.5,
                                   max_concurrent_runs=3)
        assert config.exposed

    def test_a_file_cannot_be_served_from_the_server_disk(self) -> None:
        with mock.patch.object(app, "web_entry") as web_entry:
            code, err = run(["--web", "pyproject.toml"])
        assert code == 1
        assert "--web" in err
        web_entry.assert_not_called()

    def test_a_bad_value_is_an_argument_error(self) -> None:
        with mock.patch.object(app, "web_entry") as web_entry:
            code, err = run(["--web", "--port", "0"])
        assert code == 1
        assert "--port" in err
        web_entry.assert_not_called()

    def test_missing_flet_web_gives_an_install_hint(self) -> None:
        err = io.StringIO()
        with mock.patch.object(app, "flet_web_available", return_value=False):
            code = app.web_entry(WebConfig(), stderr=err)
        texts.select_language("ja")
        assert code == 1
        assert 'pip install "flet[web]>=1.0,<2"' in err.getvalue()
        assert "uv sync --extra web" in err.getvalue()


class ArgparseExitCodeTests:
    def test_help_is_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _ = run(["--help"])
        assert code == 0
        assert "--web" in capsys.readouterr().out

    def test_unknown_option_is_1_not_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, _ = run(["--nope"])
        assert code == 1
        capsys.readouterr()
