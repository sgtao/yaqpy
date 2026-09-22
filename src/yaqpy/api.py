"""Public library API (design doc section 10)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.ports import SandboxFileSystem, StaticEnvironment
from yaqpy.app.printer import MemorySink
from yaqpy.app.recipe_service import RecipeRun, RecipeService
from yaqpy.app.service import YqService
from yaqpy.core.lang.parser import Expression
from yaqpy.core.model.convert import from_python, to_python
from yaqpy.core.model.node import Node
from yaqpy.core.operators import OperatorRegistry, builtin_registry
from yaqpy.formats.registry import FormatRegistry, builtin_formats
from yaqpy.options import Options
from yaqpy.recipes import Recipe, builtin_recipes


class Yq:
    """Stateless facade. Safe to share between threads."""

    def __init__(
        self,
        options: Options | None = None,
        *,
        operators: OperatorRegistry | None = None,
        formats: FormatRegistry | None = None,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.options = options or Options()
        if environ is None:
            import os

            environ = os.environ
        self._service = YqService(
            SandboxFileSystem(), StaticEnvironment(environ),
            operators=operators or builtin_registry(), formats=formats or builtin_formats(),
            clock=clock,
        )

    # ------------------------------------------------------------------ compile

    def compile(self, expression: str) -> Expression:
        return self._service.compile(expression)

    # ------------------------------------------------------------------ text in / text out

    def _request(self, expression: str | Expression, texts: Iterable[str], mode: EvalMode,
                 options: Options | None) -> EvaluateRequest:
        source = expression.source if isinstance(expression, Expression) else expression
        inputs = tuple(InputSource("<text>", text) for text in texts)
        return EvaluateRequest(expression=source, inputs=inputs, mode=mode,
                               options=options or self.options)

    def evaluate(self, expression: str | Expression, text: str = "", *,
                 options: Options | None = None) -> str:
        request = self._request(expression, [text] if text != "" else [], EvalMode.STREAM, options)
        result = self._service.evaluate(request, MemorySink())
        return result.output or ""

    def evaluate_all(self, expression: str | Expression, texts: Iterable[str], *,
                     options: Options | None = None) -> str:
        request = self._request(expression, texts, EvalMode.ALL, options)
        result = self._service.evaluate(request, MemorySink())
        return result.output or ""

    # ------------------------------------------------------------------ nodes / python objects

    def evaluate_nodes(self, expression: str | Expression, documents: Sequence[Node], *,
                       options: Options | None = None) -> list[Node]:
        return self._service.evaluate_nodes(expression, documents, options or self.options)

    def iter_results(self, expression: str | Expression, text: str, *,
                     options: Options | None = None) -> Iterator[Node]:
        options = options or self.options
        decoder = self._service.formats.decoder_for(options.input_format, options)
        for doc in decoder.decode_documents(text):
            yield from self.evaluate_nodes(expression, [doc], options=options)

    def query(self, expression: str | Expression, data: Any, *,
              options: Options | None = None) -> list[Any]:
        root = from_python(data)
        root.evaluate_together = True
        results = self.evaluate_nodes(expression, [root], options=options)
        return [to_python(n) for n in results]

    def update(self, expression: str | Expression, data: Any, *,
               options: Options | None = None) -> Any:
        root = from_python(data)
        root.evaluate_together = True
        self.evaluate_nodes(expression, [root], options=options)
        return to_python(root)

    def load(self, text: str, *, format: str = "yaml", options: Options | None = None) -> list[Node]:
        options = options or self.options
        decoder = self._service.formats.decoder_for(format, options)
        return list(decoder.decode_documents(text))

    def dump(self, documents: Iterable[Node], *, format: str = "yaml",
             options: Options | None = None) -> str:
        from yaqpy.app.printer import ResultPrinter

        options = options or self.options
        spec = self._service.formats.get(format)
        unwrap = options.unwrap_scalar if options.unwrap_scalar is not None else spec.unwrap_scalar_default
        encoder = self._service.formats.encoder_for(format, options, unwrap)
        sink = MemorySink()
        ResultPrinter(encoder, sink).print_results(list(documents))
        return sink.finish() or ""


    # ------------------------------------------------------------------ recipes (a yaqpy extension)

    def apply_recipe(self, recipe: str | Recipe, text: str, *, input_format: str = "json",
                     output_format: str = "json", prune_null: bool = False, prune_empty: bool = False,
                     options: Options | None = None) -> RecipeRun:
        """Convert ``text`` with a recipe: a bundled one by name, or a ``Recipe`` you built.

        Never reads files or environment variables, whatever the options say. The result holds the
        converted text (``output``) and a ``report`` of what was dropped, added or does not fit the
        target schema.
        """
        service = RecipeService(self._service)
        if isinstance(recipe, str):
            recipe = service.load(recipe)
        return service.run(recipe, InputSource("<text>", text), options or self.options,
                           input_format=service.input_format_for(recipe, "", input_format),
                           output_format=service.output_format_for(recipe, output_format),
                           prune_null=prune_null, prune_empty=prune_empty)


_DEFAULT = Yq()


def compile(expression: str) -> Expression:  # noqa: A001 - mirrors the design doc
    return _DEFAULT.compile(expression)


def evaluate(expression: str, text: str = "", *, options: Options | None = None) -> str:
    return _DEFAULT.evaluate(expression, text, options=options)


def evaluate_all(expression: str, texts: Iterable[str], *, options: Options | None = None) -> str:
    return _DEFAULT.evaluate_all(expression, texts, options=options)


def query(expression: str, data: Any, *, options: Options | None = None) -> list[Any]:
    return _DEFAULT.query(expression, data, options=options)


def update(expression: str, data: Any, *, options: Options | None = None) -> Any:
    return _DEFAULT.update(expression, data, options=options)


def load(text: str, *, format: str = "yaml", options: Options | None = None) -> list[Node]:
    return _DEFAULT.load(text, format=format, options=options)


def dump(documents: Iterable[Node], *, format: str = "yaml", options: Options | None = None) -> str:
    return _DEFAULT.dump(documents, format=format, options=options)


def detect_format(text: str) -> str:
    """Guess the format of ``text`` from its content alone (a yaqpy extension; Go yq has no such
    thing - it only ever looks at a file's extension).

    Meant for text with no filename to go by, or none whose extension names a format: the same
    guess ``Options(input_format="auto")`` falls back to once a filename's extension gives no
    answer. Returns a format name ``Options(input_format=...)`` accepts; "yaml" is the fallback
    when nothing in the content looks confident enough (never an error).
    """
    return builtin_formats().guess("", text).name


def list_recipes() -> dict[str, Recipe]:
    """The bundled recipes by name."""
    return dict(builtin_recipes())


def apply_recipe(recipe: str | Recipe, text: str, *, input_format: str = "json",
                 output_format: str = "json", prune_null: bool = False, prune_empty: bool = False,
                 options: Options | None = None) -> RecipeRun:
    return _DEFAULT.apply_recipe(recipe, text, input_format=input_format, output_format=output_format,
                                 prune_null=prune_null, prune_empty=prune_empty, options=options)
