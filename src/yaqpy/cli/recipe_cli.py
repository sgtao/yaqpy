"""``yaqpy --recipe`` / ``--list-recipes`` / ``--recipe-test`` (a yaqpy extension)."""

from __future__ import annotations

import argparse
import os
from typing import TextIO

from yaqpy.app.dto import InputSource
from yaqpy.app.local import LocalEnvironment, LocalFileSystem
from yaqpy.app.recipe_service import RecipeRun, RecipeService
from yaqpy.app.recipe_text import render_report, render_table, summary_lines
from yaqpy.app.service import YqService
from yaqpy.cli.args import InvocationError, resolve_invocation
from yaqpy.errors import YqError
from yaqpy.recipes import Recipe, builtin_recipes

EXIT_OK = 0
EXIT_ERROR = 1

_RECIPE_ONLY_FLAGS = (("report", "--report"), ("apply", "--apply"), ("out_dir", "--out-dir"),
                      ("recipe_test", "--recipe-test"))


def wants_recipe_mode(ns: argparse.Namespace) -> bool:
    return bool(ns.recipe or ns.list_recipes or ns.recipe_test or ns.report or ns.apply or ns.out_dir)


def _describe(recipe: Recipe) -> str:
    if recipe.title:
        return recipe.title
    lines = recipe.description.strip().splitlines()
    return lines[0] if lines else ""


def list_recipes(out: TextIO) -> int:
    recipes = builtin_recipes()
    if not recipes:
        out.write("No bundled recipes.\n")
        return EXIT_OK
    rows = [(r.name, f"{r.input_format} -> {r.output_format}", _describe(r)) for r in recipes.values()]
    out.write("Bundled recipes (use: yaqpy --recipe NAME input.json):\n\n")
    out.write(render_table(("name", "formats", "description"), rows))
    out.write("\nYour own: yaqpy --recipe ./my.yaqpy input.json   (see USAGE.ja.md, recipes)\n")
    return EXIT_OK


def _check_combination(ns: argparse.Namespace) -> None:
    clashes = [flag for flag, present in (
        ("--expression", ns.expression), ("--from-file", ns.from_file), ("--schema", ns.schema),
        ("-P", ns.pretty_print), ("-n", ns.null_input), ("-i", ns.inplace), ("-s", ns.split_exp),
        ("--split-exp-file", ns.split_exp_file), ("eval-all", ns.command == "eval-all"),
        ("-f", ns.front_matter)) if present]
    if clashes:
        raise InvocationError("--recipe cannot be combined with " + ", ".join(clashes)
                              + " (the recipe is the expression; the arguments are input files)")
    if ns.apply and not ns.out_dir:
        raise InvocationError("--apply needs --out-dir DIR (the input files are never overwritten)")
    if ns.out_dir and not ns.apply:
        raise InvocationError("--out-dir is used with --apply")


def _output_path(recipes: RecipeService, run: RecipeRun, out_dir: str) -> str:
    spec = recipes.service.formats.get(run.output_format)
    extension = "." + (spec.extensions[0] if spec.extensions else spec.name).lstrip(".")
    stem = os.path.splitext(os.path.basename(run.input_name))[0]
    return os.path.join(out_dir, stem + extension)


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def run_recipe_mode(ns: argparse.Namespace, *, out: TextIO, err: TextIO, stdin_is_pipe: bool) -> int:
    if ns.list_recipes:
        return list_recipes(out)
    fs = LocalFileSystem()
    service = YqService(fs, LocalEnvironment())
    recipes = RecipeService(service)
    try:
        if not ns.recipe:
            flags = [flag for attr, flag in _RECIPE_ONLY_FLAGS if getattr(ns, attr)]
            raise InvocationError(f"{', '.join(flags)} needs --recipe NAME|FILE (see --list-recipes)")
        recipe = recipes.load(ns.recipe)
        if ns.recipe_test:
            return _run_tests(recipes, recipe, out)
        _check_combination(ns)
        # The recipe is the expression. "." only keeps the argument parser from taking the first
        # input file for one; the formats, indent and the like are read from the flags as usual.
        ns.expression = "."
        invocation = resolve_invocation(ns, stdin_is_pipe=stdin_is_pipe, file_exists=fs.exists_file,
                                        read_file=fs.read_text)
        sources = list(invocation.request.inputs)
        if not sources:
            raise InvocationError("--recipe needs at least one input file (or data on stdin)")
        if ns.apply and any(s.name == "-" for s in sources):
            raise InvocationError("--apply needs input files (their names decide the output names)")
        options = invocation.request.options
        requested_out = "toon" if ns.toon else ns.output_format
        output_format = recipes.output_format_for(recipe, requested_out)
    except (InvocationError, YqError, OSError) as e:
        err.write(f"Error: {getattr(e, 'message', None) or e}\n")
        return EXIT_ERROR
    for warning in invocation.warnings:
        err.write(f"Warning: {warning}\n")

    rows: list[tuple[str, ...]] = []
    failed = False
    used: set[str] = set()
    for source in sources:
        try:
            run = recipes.run(recipe, source, options,
                              input_format=recipes.input_format_for(recipe, source.name, ns.input_format),
                              output_format=output_format, prune_null=ns.prune_null,
                              prune_empty=ns.prune_empty)
            target = ""
            if ns.apply:
                target = _output_path(recipes, run, ns.out_dir)
                if _same_file(target, source.name) or os.path.normcase(target) in used:
                    raise InvocationError(f"{target} would overwrite an input or another output; "
                                          f"choose another --out-dir")
                used.add(os.path.normcase(target))
                fs.write_file(target, run.output)
        except (InvocationError, YqError, OSError) as e:
            failed = True
            err.write(f"Error: {source.name}: {getattr(e, 'message', None) or e}\n")
            rows.append((source.name, "error", "-", "-", "-", "-"))
            continue
        report = run.report
        lines = summary_lines(run)
        if ns.report:
            out.write(render_report(run))
            if len(sources) > 1:
                out.write("\n")
        elif not ns.apply:
            out.write(run.output)
            if lines:
                err.write(f"recipe {recipe.name}: {source.name}\n")
                err.writelines(f"  {line}\n" for line in lines)
        if ns.apply:
            verdict = "-" if report is None else ("ok" if report.clean else "check")
            rows.append((source.name, verdict,
                         str(len([d for d in report.dropped if d.declared])) if report else "-",
                         str(len(report.not_handled)) if report else "-",
                         str(len(report.issues)) if report else "-", target))
    if ns.apply:
        if ns.report:
            out.write("\n")
        out.write(render_table(("input", "result", "dropped", "not handled", "schema issues", "output"), rows))
        out.write("(dropped = declared by the recipe; 'check' = something not handled or not fitting "
                  "the target schema. Re-run without --apply, or with --report, for the details.)\n")
    return EXIT_ERROR if failed else EXIT_OK


def _run_tests(recipes: RecipeService, recipe: Recipe, out: TextIO) -> int:
    if not recipe.tests:
        out.write(f"recipe {recipe.name} has no test cases\n")
        return EXIT_OK
    results = recipes.run_tests(recipe)
    for result in results:
        out.write(f"{'ok  ' if result.passed else 'FAIL'} {recipe.name}: {result.name}"
                  + (f"\n     {result.message}" if result.message else "") + "\n")
    passed = sum(1 for r in results if r.passed)
    out.write(f"{passed}/{len(results)} passed\n")
    return EXIT_OK if passed == len(results) else EXIT_ERROR
