"""``yaqpy-gui``（デスクトップ版）と ``yaqpy-web``（Web 版）のエントリポイント。

**このモジュールは flet 未導入でも import できること。**
flet に触れるのは ``yaqpy.gui._run``（デスクトップ）と ``yaqpy.gui._web``（Web 版）の側だけに
して、導入案内を出せるようにする。

画面とコードは共通だが、コマンドとヘルプは分けている（v0.6.0 の要望）：

* ``yaqpy-gui [FILE]`` … デスクトップの窓（``yaqpy --gui`` と同じ）
* ``yaqpy-web [--port ...]`` … ブラウザ版のサーバー（``yaqpy --web`` と同じ。``yaqpy --web`` の
  後ろの引数はそのまま ``web_cli_entry`` に渡る）
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections.abc import Sequence
from typing import TextIO

from yaqpy.gui import texts
from yaqpy.gui.web_config import (
    DEFAULT_HOST,
    DEFAULT_MAX_CONCURRENT_RUNS,
    DEFAULT_MAX_INPUT_MIB,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECONDS,
    WebConfig,
    WebConfigError,
)


def flet_available() -> bool:
    return importlib.util.find_spec("flet") is not None


def flet_web_available() -> bool:
    """Web 版に要るもの（``[web]`` extra：flet-web と、それが連れてくる uvicorn）。"""
    return all(importlib.util.find_spec(name) is not None
               for name in ("flet", "flet_web", "uvicorn"))


def main_entry(*, stderr: TextIO | None = None, initial_path: str | None = None) -> int:
    """デスクトップ版を起動する（``yaqpy --gui`` からも呼ばれる）。"""
    err = stderr or sys.stderr
    if not flet_available():
        err.write(texts.INSTALL_HINT)
        return 1
    from yaqpy.gui._run import run_app

    run_app(initial_path=initial_path)
    return 0


def web_entry(config: WebConfig, *, stderr: TextIO | None = None) -> int:
    """Web 版を起動する（``yaqpy-web`` / ``yaqpy --web``。v0.6.0）。"""
    err = stderr or sys.stderr
    if not flet_web_available():
        texts.select_language(config.language)
        err.write(texts.WEB_INSTALL_HINT)
        return 1
    from yaqpy.gui._web import serve

    return serve(config, stderr=err)


def _parse(parser: argparse.ArgumentParser, argv: Sequence[str] | None
           ) -> tuple[argparse.Namespace | None, int]:
    """終了コードを CLI の規約に合わせる：--help は 0、引数の誤りは 1（argparse の 2 は使わない）。"""
    try:
        return parser.parse_args(argv), 0
    except SystemExit as e:
        return None, 0 if e.code in (0, None) else 1


# ---------------------------------------------------------------------- yaqpy-gui（デスクトップ）


def build_gui_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yaqpy-gui",
        description="yaqpy desktop GUI: open YAML / JSON / XML / CSV / TOML / properties / TOON "
                    "files in a window, try expressions and save the result. "
                    "Same as `yaqpy --gui`. Needs the gui extra (flet).",
        epilog=(
            "examples:\n"
            "  yaqpy-gui                     # open the window\n"
            "  yaqpy-gui config.yaml         # open the window with a file already open\n"
            "\n"
            "To use the same screens in a web browser, see `yaqpy-web --help`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", nargs="?", help="a file to open at startup")
    return parser


def cli_entry(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None) -> int:
    """``yaqpy-gui [FILE]``：デスクトップ版。"""
    err = stderr or sys.stderr
    args = list(sys.argv[1:] if argv is None else argv)
    if "--web" in args:                           # v0.6.0 の開発途中の書き方を案内する
        err.write("Error: the web version is started with `yaqpy-web` (or `yaqpy --web`)\n")
        return 1
    ns, code = _parse(build_gui_parser(), args)
    if ns is None:
        return code
    if ns.file is not None and not os.path.isfile(ns.file):
        err.write(f"Error: not a file: {ns.file}\n")
        return 1
    return main_entry(stderr=err, initial_path=ns.file)


# ---------------------------------------------------------------------- yaqpy-web（ブラウザ版）


def build_web_parser(prog: str = "yaqpy-web") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="yaqpy web version: serves the yaqpy GUI to a web browser from a small server "
                    "on this PC. Files are uploaded from the browser and results come back as "
                    "downloads; operators that read the server's environment or files (env, load, "
                    "system) are always off. Same as `yaqpy --web`. Needs the web extra "
                    "(flet[web]). Stop it with Ctrl+C.",
        epilog=(
            "examples:\n"
            "  yaqpy-web                          # http://127.0.0.1:8550/ (opens your browser)\n"
            "  yaqpy-web --port 9000              # another port\n"
            "  yaqpy-web --port 9000 --lang en --no-browser\n"
            "  yaqpy --web --port 9000            # the same, through the yaqpy command\n"
            "\n"
            "For the desktop window, see `yaqpy-gui --help`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"address to listen on (default {DEFAULT_HOST}: this PC only). "
                             "Anything else is reachable from other machines and prints a warning; "
                             "there is no authentication")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port to listen on (default {DEFAULT_PORT})")
    parser.add_argument("--lang", choices=texts.LANGUAGES, default=texts.DEFAULT_LANGUAGE,
                        help=f"display language for every browser (default {texts.DEFAULT_LANGUAGE})")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the default browser at startup")
    parser.add_argument("--no-cdn", action="store_true",
                        help="do not load the web client's renderer and fonts from a CDN (works "
                             "offline, but Japanese text is not displayed; use --lang en)")
    parser.add_argument("--max-input-mib", type=int, default=DEFAULT_MAX_INPUT_MIB,
                        help=f"largest file or paste accepted, in MiB (default {DEFAULT_MAX_INPUT_MIB})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help=f"longest a run may take, in seconds (default {DEFAULT_TIMEOUT_SECONDS:g})")
    parser.add_argument("--max-concurrent-runs", type=int, default=DEFAULT_MAX_CONCURRENT_RUNS,
                        help="runs allowed at the same time across all browsers "
                             f"(default {DEFAULT_MAX_CONCURRENT_RUNS})")
    return parser


def web_cli_entry(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None,
                  prog: str = "yaqpy-web") -> int:
    """``yaqpy-web [--host --port ...]``：Web 版（``yaqpy --web ...`` も ``prog`` を変えてここへ来る）。

    ファイル名は受け付けない：Web 版はサーバー側のディスクのファイルを開かない（ブラウザから
    アップロードする）。
    """
    err = stderr or sys.stderr
    ns, code = _parse(build_web_parser(prog), argv)
    if ns is None:
        return code
    try:
        config = WebConfig(
            host=ns.host,
            port=ns.port,
            language=ns.lang,
            open_browser=not ns.no_browser,
            use_cdn=not ns.no_cdn,
            max_input_mib=ns.max_input_mib,
            timeout_seconds=ns.timeout,
            max_concurrent_runs=ns.max_concurrent_runs,
        )
    except WebConfigError as e:
        err.write(f"Error: {e}\n")
        return 1
    return web_entry(config, stderr=err)


if __name__ == "__main__":
    raise SystemExit(cli_entry())
