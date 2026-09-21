"""``yaqpy --print-spec | --example | --guide-prompt | --skill-md``: print and exit (files are not read)."""

from __future__ import annotations

import argparse
from typing import TextIO

from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.selfdoc import render_examples, render_guide_prompt, render_skill_md, render_spec
from yaqpy.app.service import YqService

EXIT_OK = 0
EXIT_ERROR = 1

# flag attribute -> (flag as typed, renderer)
_OUTPUTS = (
    ("print_spec", "--print-spec", render_spec),
    ("example", "--example", render_examples),
    ("guide_prompt", "--guide-prompt", render_guide_prompt),
    ("skill_md", "--skill-md", render_skill_md),
)


def wants_describe_mode(ns: argparse.Namespace) -> bool:
    return any(getattr(ns, attr) for attr, _, _ in _OUTPUTS)


def run_describe_mode(ns: argparse.Namespace, *, out: TextIO, err: TextIO) -> int:
    chosen = [(flag, render) for attr, flag, render in _OUTPUTS if getattr(ns, attr)]
    if len(chosen) > 1:
        err.write("Error: " + ", ".join(flag for flag, _ in chosen) + " cannot be used together\n")
        return EXIT_ERROR
    flag, render = chosen[0]
    if ns.args or ns.expression or ns.from_file or ns.recipe or ns.list_recipes:
        err.write(f"Error: {flag} takes no expression, files or recipe (it only prints)\n")
        return EXIT_ERROR
    # Nothing here reads a file or the environment: the examples run on an in-memory service.
    service = YqService(InMemoryFileSystem(), StaticEnvironment({}))
    out.write(render(service).rstrip("\n") + "\n")
    return EXIT_OK
