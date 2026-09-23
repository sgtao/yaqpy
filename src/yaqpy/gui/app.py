"""``yaqpy-gui`` のエントリポイント。

**このモジュールは flet 未導入でも import できること。**
flet に触れるのは ``yaqpy.gui._run``（デスクトップ）と ``yaqpy.gui._web``（Web 版）の側だけに
して、導入案内を出せるようにする。
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
    """Web 版を起動する（``yaqpy-gui --web``。v0.6.0）。"""
    err = stderr or sys.stderr
    if not flet_web_available():
        texts.select_language(config.language)
        err.write(texts.WEB_INSTALL_HINT)
        return 1
    from yaqpy.gui._web import serve

    return serve(config, stderr=err)


_WEB_ONLY = ("host", "port", "lang", "no_browser", "no_cdn", "max_input_mib", "timeout",
             "max_concurrent_runs")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yaqpy-gui",
        description="yaqpy GUI. Opens the desktop window, or with --web serves it to a browser.",
        epilog=(
            "examples:\n"
            "  yaqpy-gui                     # desktop window\n"
            "  yaqpy-gui config.yaml         # desktop window with a file open\n"
            "  yaqpy-gui --web               # browser version on http://127.0.0.1:8550/\n"
            "  yaqpy-gui --web --port 9000 --lang en --no-browser"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", nargs="?", help="a file to open at startup (desktop only)")
    parser.add_argument("--web", action="store_true",
                        help="serve the GUI to a web browser instead of opening a window")
    web = parser.add_argument_group("web version (with --web)")
    web.add_argument("--host", default=None,
                     help=f"address to listen on (default {DEFAULT_HOST}: this PC only). "
                          "Anything else is reachable from other machines and prints a warning")
    web.add_argument("--port", type=int, default=None, help=f"port (default {DEFAULT_PORT})")
    web.add_argument("--lang", choices=texts.LANGUAGES, default=None,
                     help="display language for every browser (default ja)")
    web.add_argument("--no-browser", action="store_true", default=None,
                     help="do not open the default browser at startup")
    web.add_argument("--no-cdn", action="store_true", default=None,
                     help="do not load the web client's renderer and fonts from a CDN (works "
                          "offline, but Japanese text is not displayed; use --lang en)")
    web.add_argument("--max-input-mib", type=int, default=None,
                     help=f"largest file or paste accepted, in MiB (default {DEFAULT_MAX_INPUT_MIB})")
    web.add_argument("--timeout", type=float, default=None,
                     help=f"longest a run may take, in seconds (default {DEFAULT_TIMEOUT_SECONDS:g})")
    web.add_argument("--max-concurrent-runs", type=int, default=None,
                     help="runs allowed at the same time across all browsers "
                          f"(default {DEFAULT_MAX_CONCURRENT_RUNS})")
    return parser


def cli_entry(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None) -> int:
    """``yaqpy-gui [FILE] [--web ...]`` の引数を解釈する（v0.6.0）。

    終了コードは CLI の規約に合わせる：成功 0、引数の誤り 1（argparse の 2 は使わない）。
    """
    err = stderr or sys.stderr
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as e:                       # --help は 0、誤りは 1 にそろえる
        return 0 if e.code in (0, None) else 1

    if not ns.web:
        given = [name for name in _WEB_ONLY if getattr(ns, name) is not None]
        if given:
            flag = "--" + given[0].replace("_", "-")
            err.write(f"Error: {flag} can only be used with --web\n")
            return 1
        if ns.file is not None and not os.path.isfile(ns.file):
            err.write(f"Error: not a file: {ns.file}\n")
            return 1
        return main_entry(stderr=err, initial_path=ns.file)

    if ns.file is not None:
        err.write("Error: --web does not open a file from the server's disk; "
                  "use [+ Add File] in the browser instead\n")
        return 1
    try:
        config = WebConfig(
            host=DEFAULT_HOST if ns.host is None else ns.host,
            port=DEFAULT_PORT if ns.port is None else ns.port,
            language=ns.lang or texts.DEFAULT_LANGUAGE,
            open_browser=not ns.no_browser,
            use_cdn=not ns.no_cdn,
            max_input_mib=DEFAULT_MAX_INPUT_MIB if ns.max_input_mib is None else ns.max_input_mib,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS if ns.timeout is None else ns.timeout,
            max_concurrent_runs=(DEFAULT_MAX_CONCURRENT_RUNS if ns.max_concurrent_runs is None
                                 else ns.max_concurrent_runs),
        )
    except WebConfigError as e:
        err.write(f"Error: {e}\n")
        return 1
    return web_entry(config, stderr=err)


if __name__ == "__main__":
    raise SystemExit(cli_entry())
