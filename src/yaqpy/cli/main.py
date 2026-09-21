"""``yaqpy`` command line entry point (design doc 12)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from typing import TextIO

from yaqpy.app.local import LocalEnvironment, LocalFileSystem
from yaqpy.app.printer import InPlaceSink, StreamSink
from yaqpy.app.service import YqService
from yaqpy.cli.args import InvocationError, resolve_invocation
from yaqpy.cli.describe_cli import run_describe_mode, wants_describe_mode
from yaqpy.cli.parser import ArgumentError, parse_args, print_help
from yaqpy.cli.recipe_cli import run_recipe_mode, wants_recipe_mode
from yaqpy.errors import YqError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPT = 130


def _stdin_is_pipe() -> bool:
    try:
        return not sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _configure_streams() -> TextIO:
    """Write UTF-8 with plain ``\\n`` line endings, like the Go binary."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    return sys.stdout


def _launch_gui(ns: argparse.Namespace, err: TextIO) -> int:
    """``yaqpy --gui``: hand over to the desktop GUI.

    The import is deliberately lazy (inside this function): the CLI must keep working
    when the optional ``gui`` extra (flet) is not installed. ``yaqpy.gui.app`` itself
    does not import flet at module level, so this import is always safe.
    """
    if ns.args or ns.expression or ns.from_file:
        err.write("Error: --gui cannot be combined with an expression or files\n")
        return EXIT_ERROR
    from yaqpy.gui import app as gui_app

    return gui_app.main_entry(stderr=err)


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = stdout or _configure_streams()
    err = stderr or sys.stderr
    try:
        ns = parse_args(argv)
    except ArgumentError as e:
        err.write(f"Error: {e.message}\n")
        return EXIT_ERROR
    if ns.version:
        from yaqpy import __version__

        out.write(f"yaqpy (https://github.com/mikefarah/yq/ compatible) version v{__version__}\n")
        return EXIT_OK
    if ns.gui:
        return _launch_gui(ns, err)
    if wants_describe_mode(ns):
        return run_describe_mode(ns, out=out, err=err)
    if wants_recipe_mode(ns):
        return run_recipe_mode(ns, out=out, err=err, stdin_is_pipe=_stdin_is_pipe())
    logging.basicConfig(level=logging.DEBUG if ns.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s", stream=err)
    fs = LocalFileSystem()
    try:
        invocation = resolve_invocation(
            ns, stdin_is_pipe=_stdin_is_pipe(), file_exists=fs.exists_file, read_file=fs.read_text,
        )
    except InvocationError as e:
        err.write(f"Error: {e.message}\n")
        return EXIT_ERROR
    except OSError as e:
        err.write(f"Error: {e}\n")
        return EXIT_ERROR
    for warning in invocation.warnings:
        err.write(f"Warning: {warning}\n")
    if invocation.show_usage:
        print_help(out)
        return EXIT_OK
    request = invocation.request
    service = YqService(fs, LocalEnvironment())
    if request.in_place:
        sink: InPlaceSink | StreamSink = InPlaceSink(request.inputs[0].name)
    else:
        sink = StreamSink(out)
    try:
        result = service.evaluate(request, sink)
    except KeyboardInterrupt:
        return EXIT_INTERRUPT
    except YqError as e:
        if ns.verbose:
            traceback.print_exc(file=err)
        err.write(f"Error: {e}\n")
        return EXIT_ERROR
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return EXIT_ERROR
    except Exception as e:  # noqa: BLE001 - last resort, keep the CLI contract
        if ns.verbose:
            traceback.print_exc(file=err)
        err.write(f"Error: internal error: {e}\n")
        return EXIT_ERROR
    if request.exit_status and not result.printed_anything:
        err.write("Error: no matches found\n")
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    os._exit(main())
