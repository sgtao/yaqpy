"""RecipeService: run a recipe on inputs (a yaqpy extension; shared by CLI and library).

A recipe is only ever run with ``SecurityPolicy.strict()`` - no environment variables, no files,
no external commands - whatever the caller asked for, so that a recipe from someone else (or one
that ships with yaqpy) can be tried on a body that holds secrets without reading anything else.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Any

from yaqpy.app.dto import InputSource
from yaqpy.app.printer import MemorySink, ResultPrinter
from yaqpy.app.service import YqService, with_prune
from yaqpy.core.model.convert import to_python
from yaqpy.core.model.node import Node
from yaqpy.errors import FormatError, RecipeError
from yaqpy.options import Options, SecurityPolicy
from yaqpy.recipes import Recipe, build_recipe, find_builtin
from yaqpy.recipes.analysis import RecipeReport, analyse

_EXPRESSION_EXTENSIONS = (".yaqpy", ".yq")
_METADATA_SUFFIXES = (".recipe.yaml", ".recipe.yml")


@dataclass(frozen=True, slots=True)
class RecipeRun:
    recipe: Recipe
    input_name: str
    input_format: str
    output_format: str
    output: str
    document_count: int
    report: RecipeReport | None


@dataclass(frozen=True, slots=True)
class RecipeTestResult:
    name: str
    passed: bool
    message: str = ""


def _expression_with_prune(recipe: Recipe, *, nulls: bool, empties: bool) -> str:
    return with_prune(recipe.expression, nulls=nulls or "nulls" in recipe.prune,
                      empties=empties or "empties" in recipe.prune)


class RecipeService:
    def __init__(self, service: YqService) -> None:
        self.service = service

    # ------------------------------------------------------------------ finding a recipe

    def load(self, reference: str) -> Recipe:
        """A bundled recipe by name, or a recipe file (``my.yaqpy`` or ``my.recipe.yaml``)."""
        looks_like_path = (os.sep in reference or "/" in reference
                           or reference.endswith(_EXPRESSION_EXTENSIONS + _METADATA_SUFFIXES))
        if not looks_like_path and not self.service.fs.exists_file(reference):
            return find_builtin(reference)
        if not self.service.fs.exists_file(reference):
            raise RecipeError(f"recipe file not found: {reference}")
        directory = os.path.dirname(reference)

        def read_related(name: str) -> str:
            return self.service.fs.read_text(os.path.join(directory, name))

        base = os.path.basename(reference)
        try:
            if base.endswith(_METADATA_SUFFIXES):
                stem = base[: base.rindex(".recipe.")]
                return build_recipe(name=stem, expression=None, origin=reference,
                                    metadata=self.service.fs.read_text(reference),
                                    read_related=read_related)
            stem = os.path.splitext(base)[0]
            metadata = None
            for suffix in _METADATA_SUFFIXES:
                sidecar = os.path.join(directory, stem + suffix)
                if self.service.fs.exists_file(sidecar):
                    metadata = self.service.fs.read_text(sidecar)
                    break
            return build_recipe(name=stem, expression=self.service.fs.read_text(reference),
                                metadata=metadata, origin=reference, read_related=read_related)
        except OSError as e:
            raise RecipeError(f"cannot read the recipe {reference}: {e}") from None

    # ------------------------------------------------------------------ formats

    def input_format_for(self, recipe: Recipe, source_name: str, requested: str = "auto") -> str:
        """``-p`` if given; else the file extension; else what the recipe says it reads."""
        formats = self.service.formats
        if requested not in ("", "auto", "a"):
            return formats.get(requested).name
        guessed = formats.guess_from_filename(source_name)
        return (guessed or formats.get(recipe.input_format)).name

    def output_format_for(self, recipe: Recipe, requested: str = "auto") -> str:
        if requested in ("", "auto", "a"):
            return self.service.formats.get(recipe.output_format).name
        return self.service.formats.get(requested).name

    # ------------------------------------------------------------------ running

    def _read(self, source: InputSource) -> str:
        return self.service._read_input(source)  # noqa: SLF001 - one place that knows "-" and files

    def run(self, recipe: Recipe, source: InputSource, options: Options, *,
            input_format: str, output_format: str, prune_null: bool = False,
            prune_empty: bool = False) -> RecipeRun:
        service = self.service
        options = replace(options, security=SecurityPolicy.strict(), input_format=input_format,
                          output_format=output_format, null_input=False)
        expression = service.compile(_expression_with_prune(recipe, nulls=prune_null,
                                                            empties=prune_empty))
        decoder = service.formats.decoder_for(input_format, options)
        text = self._read(source)
        name = "" if source.name in ("<text>",) else source.name
        documents = list(decoder.decode_documents(text, filename=name, file_index=0,
                                                  process_leading=True))
        results: list[Node] = []
        first_input: Any = None
        first_output: Any = None
        for index, document in enumerate(documents):
            if index == 0:
                first_input = to_python(document)
            produced = service.evaluate_nodes(expression, [document], options)
            if index == 0 and produced:
                first_output = to_python(produced[0])
            results.extend(produced)
        spec = service.formats.get(output_format)
        unwrap = options.unwrap_scalar if options.unwrap_scalar is not None else spec.unwrap_scalar_default
        sink = MemorySink()
        printer = ResultPrinter(service.formats.encoder_for(output_format, options, unwrap), sink,
                                max_depth=options.limits.max_depth)
        printer.print_results(results)
        report = None
        if documents and first_output is not None:
            report = analyse(recipe, first_input, first_output, extra_documents=len(documents) - 1)
        return RecipeRun(recipe=recipe, input_name=source.name, input_format=input_format,
                         output_format=output_format, output=sink.finish() or "",
                         document_count=len(documents), report=report)

    # ------------------------------------------------------------------ the recipe's own tests

    def run_tests(self, recipe: Recipe) -> list[RecipeTestResult]:
        """Run the recipe on the inputs of its ``tests`` and compare with the expected outputs."""
        options = Options(input_format="json", output_format="json",
                          security=SecurityPolicy.strict())
        expression = self.service.compile(_expression_with_prune(recipe, nulls=False, empties=False))
        decoder = self.service.formats.decoder_for("json", options)
        outcomes: list[RecipeTestResult] = []
        for case in recipe.tests:
            try:
                documents = list(decoder.decode_documents(json.dumps(case.input)))
                produced = self.service.evaluate_nodes(expression, documents[:1], options)
            except (FormatError, RecipeError) as e:
                outcomes.append(RecipeTestResult(case.name, False, f"error: {e}"))
                continue
            except Exception as e:  # noqa: BLE001 - a failing expression is a failed test, not a crash
                outcomes.append(RecipeTestResult(case.name, False, f"error: {e}"))
                continue
            actual = to_python(produced[0]) if produced else None
            if actual == case.expected:
                outcomes.append(RecipeTestResult(case.name, True))
            else:
                outcomes.append(RecipeTestResult(
                    case.name, False,
                    "got " + json.dumps(actual, ensure_ascii=False, sort_keys=True)
                    + ", expected " + json.dumps(case.expected, ensure_ascii=False, sort_keys=True)))
        return outcomes
