"""YqService: the use case shared by CLI, GUI and API (design doc 11-3)."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

from yaqpy.app.dto import (
    EvalMode, EvaluateRequest, EvaluateResult, ExpressionInfo, FormatsInfo, InputSource,
)
from yaqpy.app.ports import EnvironmentPort, FileSystemPort
from yaqpy.app.printer import InPlaceSink, ResultPrinter, SplitWriter
from yaqpy.core.engine import Context, EvalEnv, Navigator, StepBudget, system_clock
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.lang.parser import Expression, ExpressionCompiler
from yaqpy.core.model.node import Node
from yaqpy.core.operators import OperatorRegistry, builtin_registry
from yaqpy.errors import ExpressionSyntaxError, FormatError, SecurityError, YqError
from yaqpy.formats.registry import FormatRegistry, builtin_formats
from yaqpy.formats.yaml.codec import YamlDecoder
from yaqpy.options import Options

PRETTY_PRINT_EXP = (
    '(... | (select(tag != "!!str"), select(tag == "!!str") | '
    'select(test("(?i)^(y|yes|n|no|on|off)$") | not))  ) style=""'
)


def process_expression(expression: str, pretty_print: bool) -> str:
    """Go's ``processExpression``: append the pretty-print expression for ``-P``."""
    if pretty_print and expression == "":
        return PRETTY_PRINT_EXP
    if pretty_print:
        return f"{expression} | {PRETTY_PRINT_EXP}"
    return expression


def with_prune(expression: str, *, nulls: bool = False, empties: bool = False) -> str:
    """Append ``prune_null`` / ``prune_empty`` (yaqpy extensions) to an expression.

    The parentheses keep a trailing ``# comment`` line of the expression from swallowing the pipe.
    An empty expression means ``.``.
    """
    steps = [name for wanted, name in ((nulls, "prune_null"), (empties, "prune_empty")) if wanted]
    if not steps:
        return expression
    return "(\n" + (expression.rstrip("\n") or ".") + "\n)\n| " + " | ".join(steps)


class YqService:
    def __init__(self, fs: FileSystemPort, env: EnvironmentPort, *,
                 operators: OperatorRegistry | None = None,
                 formats: FormatRegistry | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.fs = fs
        self.env = env
        self.operators = operators or builtin_registry()
        self.formats = formats or builtin_formats()
        self.clock = clock or system_clock
        self._compiler = ExpressionCompiler(self.operators.get)

    # ------------------------------------------------------------------ compile

    def compile(self, expression: str) -> Expression:
        return self._compiler.compile(expression)

    def validate_expression(self, expression: str) -> ExpressionInfo:
        try:
            self.compile(expression)
        except ExpressionSyntaxError as e:
            return ExpressionInfo(expression, False, e.message, e.position)
        return ExpressionInfo(expression, True)

    def list_formats(self) -> FormatsInfo:
        return FormatsInfo(tuple(self.formats.input_formats()), tuple(self.formats.output_formats()))

    # ------------------------------------------------------------------ evaluate

    def new_budget(self, options: Options) -> StepBudget:
        """Create a budget the caller can keep a reference to.

        The GUI needs this so that it can call ``budget.cancel()`` while an
        evaluation is running on a worker thread.
        """
        return StepBudget(options.limits.max_steps, options.limits.timeout_seconds)

    def make_env(self, options: Options, budget: StepBudget | None = None) -> EvalEnv:
        environ = self.env.environ() if options.security.allow_env else {}
        snippet_decoder = YamlDecoder(options)
        return EvalEnv(
            operators=self.operators,
            security=options.security,
            environ=environ,
            limits=options.limits,
            budget=budget if budget is not None else self.new_budget(options),
            options=options,
            formats=self.formats,
            yaml_snippet_decoder=snippet_decoder.decode_snippet,
            clock=self.clock,
        )

    def _resolve_formats(self, request: EvaluateRequest) -> tuple[str, str, bool, InputSource | None]:
        """Resolve the input/output format names and the unwrap default.

        When the input format is "auto" and the first input's name gives no answer (no extension,
        an unknown one, or piped/pasted text with no name), the first input's actual text is read
        once here to guess from its content (a yaqpy extension; see ``FormatRegistry.guess``). If
        that read text was not already carried by the ``InputSource`` (``source.text``), it is
        returned as a replacement source so the caller can avoid reading it again (stdin especially
        can only be read once).
        """
        options = request.options
        input_format = request.input_format or options.input_format
        sniffed: InputSource | None = None
        if input_format in ("auto", "a", ""):
            first = request.inputs[0] if request.inputs else None
            if first is None:
                input_format = "yaml"
            else:
                guessed = self.formats.guess_from_filename(first.name)
                if guessed is not None:
                    input_format = guessed.name
                else:
                    text = self._read_input(first)
                    input_format = self.formats.guess(first.name, text).name
                    if first.text is None:
                        sniffed = InputSource(first.name, text=text)
        input_spec = self.formats.get(input_format)
        output_format = request.output_format or options.output_format or input_spec.name
        if output_format in ("auto", "a"):
            output_format = input_spec.name
        output_spec = self.formats.get(output_format)
        unwrap = request.unwrap_scalar
        if unwrap is None:
            unwrap = options.unwrap_scalar
        if unwrap is None:
            unwrap = output_spec.unwrap_scalar_default
        return input_spec.name, output_spec.name, unwrap, sniffed

    def _read_input(self, source: InputSource) -> str:
        if source.text is not None:
            return source.text
        if source.name == "-":
            return self.fs.read_stdin()
        try:
            return self.fs.read_text(source.name)
        except FileNotFoundError:
            raise FormatError(f"open {source.name}: no such file or directory",
                              filename=source.name) from None
        except OSError as e:
            raise FormatError(f"open {source.name}: {e.strerror or e}", filename=source.name) from None

    def evaluate(self, request: EvaluateRequest, sink: Any, *,
                 budget: StepBudget | None = None) -> EvaluateResult:
        started = time.monotonic()
        options = request.options
        expression_text = process_expression(request.expression, options.pretty_print)
        expression = self.compile(expression_text)
        input_format, output_format, unwrap, sniffed = self._resolve_formats(request)
        if sniffed is not None:
            request = dataclasses.replace(request, inputs=(sniffed, *request.inputs[1:]))
        if request.in_place and input_format == "toml" and not options.toml.allow_lossy:
            raise FormatError(
                "refusing to update a TOML file in place: its comments are not kept, so the file "
                "would lose them. Write to another file (redirect the output), or pass "
                "--toml-allow-lossy to accept that.")
        decoder = self.formats.decoder_for(input_format, options)
        encoder = self.formats.encoder_for(output_format, options, unwrap)
        budget = budget if budget is not None else self.new_budget(options)
        env = self.make_env(options, budget)
        nav = Navigator(env)
        printer = ResultPrinter(encoder, sink, nul_separated=options.nul_separated_output,
                                max_depth=options.limits.max_depth,
                                fix_merge=options.yaml.fix_merge_anchor_to_spec,
                                split=self._split_writer(request, nav, output_format),
                                sort_keys=options.sort_keys)
        root_variables = self._build_root_variables(request, env)
        document_count = 0
        try:
            if options.null_input or not request.inputs:
                document_count = self._evaluate_null_input(nav, expression, printer, request.mode,
                                                            root_variables)
            elif request.slurp:
                document_count = self._evaluate_slurp(nav, expression, printer, decoder, request,
                                                      budget, root_variables)
            elif request.mode is EvalMode.STREAM:
                document_count = self._evaluate_stream(nav, expression, printer, decoder, request,
                                                       budget, root_variables)
            else:
                document_count = self._evaluate_all(nav, expression, printer, decoder, request,
                                                    budget, root_variables)
        except YqError:
            raise
        except RecursionError:
            raise YqError("internal error: recursion limit exceeded") from None
        output = sink.finish()
        if request.in_place and isinstance(sink, InPlaceSink):
            self.fs.atomic_write(sink.path, output or "")
            output = None
        # E7 (0926-03 5-5): static (Y001-Y009, on the compiled tree) ahead of runtime
        # (R001/R002, appended to env.lint_warnings by the operators as they run), each once;
        # both are already empty when Options.lint == "off" (the expression's own lint_warnings
        # is only non-empty when the compiler computed it - it always does - so the "off" gate
        # for the static half lives here, not in the compiler).
        warnings: tuple[str, ...] = ()
        if options.lint != "off":
            warnings = tuple(dict.fromkeys((*expression.lint_warnings, *env.lint_warnings)))
        return EvaluateResult(
            output=output,
            printed_anything=printer.printed_anything,
            document_count=document_count,
            warnings=warnings,
            elapsed_seconds=time.monotonic() - started,
            input_format=input_format,
            output_format=output_format,
        )

    def _split_writer(self, request: EvaluateRequest, nav: Navigator,
                      output_format: str) -> SplitWriter | None:
        if not request.split_expression:
            return None
        if request.in_place:
            raise YqError("write in place cannot be used with split file")
        if not request.options.security.allow_file:
            raise SecurityError("file operations have been disabled", capability="file")
        try:
            name_expression = self.compile(request.split_expression)
        except ExpressionSyntaxError as e:
            raise ExpressionSyntaxError(f"bad split document expression: {e.message}",
                                        expression=e.expression, position=e.position) from None
        return SplitWriter(self.fs, nav, name_expression, output_format)

    def _root_context(self, nodes: Sequence[Node],
                      variables: Mapping[str, tuple[Node, ...]] | None = None) -> Context:
        return Context(tuple(nodes), variables or {})

    def _build_root_variables(self, request: EvaluateRequest,
                              env: EvalEnv) -> dict[str, tuple[Node, ...]]:
        """``--arg``/``--argjson``/``--args``/``--jsonargs`` (E6, 0926-03 3-12): bound once per
        evaluation as ``$NAME`` and folded into ``$ARGS``, exactly like jq. Nothing here is set
        when the request uses none of them, so an ordinary evaluation is unaffected."""
        if not (request.named_args or request.named_json_args
                or request.positional_args is not None):
            return {}
        decode = env.yaml_snippet_decoder
        assert decode is not None, "named/positional args need a YAML/JSON decoder"
        named: dict[str, Node] = {}
        for name, value in request.named_args:
            named[name] = Node.string(value)
        for name, text in request.named_json_args:
            named[name] = decode(text)
        positional = Node.sequence()
        if request.positional_args is not None:
            positional.add_children(
                decode(value) if request.positional_args_json else Node.string(value)
                for value in request.positional_args)
        named_node = Node.mapping()
        for key, value in named.items():
            named_node.add_key_value(Node.string(key), value)
        args_node = Node.mapping()
        args_node.add_key_value(Node.string("positional"), positional)
        args_node.add_key_value(Node.string("named"), named_node)
        variables: dict[str, tuple[Node, ...]] = {name: (value,) for name, value in named.items()}
        variables["ARGS"] = (args_node,)
        return variables

    def _evaluate_null_input(self, nav: Navigator, expression: Expression, printer: ResultPrinter,
                             mode: EvalMode, variables: dict[str, tuple[Node, ...]]) -> int:
        node = Node.null(value="")
        result = nav.evaluate(self._root_context([node], variables), expression.root)
        printer.print_results(result.nodes)
        return 0

    def _decode(self, decoder: Any, request: EvaluateRequest, source: InputSource,
                file_index: int, process_leading: bool, budget: StepBudget) -> Iterator[Node]:
        text = self._read_input(source)
        name = "" if source.name in ("<text>",) else source.name
        return decoder.decode_documents(text, filename=name, file_index=file_index,
                                        process_leading=process_leading, budget=budget)

    def _evaluate_stream(self, nav: Navigator, expression: Expression, printer: ResultPrinter,
                         decoder: Any, request: EvaluateRequest, budget: StepBudget,
                         variables: dict[str, tuple[Node, ...]]) -> int:
        total = 0
        root: ExprNode | None = expression.root
        for file_index, source in enumerate(request.inputs):
            for node in self._decode(decoder, request, source, file_index, True, budget):
                result = nav.evaluate(self._root_context([node], variables), root)
                printer.print_results(result.nodes)
                total += 1
        if total == 0:
            self._evaluate_null_input(nav, expression, printer, EvalMode.STREAM, variables)
        return total

    def _read_all_documents(self, request: EvaluateRequest, decoder: Any,
                            budget: StepBudget) -> list[Node]:
        documents: list[Node] = []
        for file_index, source in enumerate(request.inputs):
            for node in self._decode(decoder, request, source, file_index, file_index == 0, budget):
                documents.append(node)
        return documents

    def _evaluate_all(self, nav: Navigator, expression: Expression, printer: ResultPrinter,
                      decoder: Any, request: EvaluateRequest, budget: StepBudget,
                      variables: dict[str, tuple[Node, ...]]) -> int:
        documents = self._read_all_documents(request, decoder, budget)
        for node in documents:
            node.evaluate_together = True     # Go's readDocuments
        if not documents:
            documents.append(Node.null(value=""))
        result = nav.evaluate(self._root_context(documents, variables), expression.root)
        printer.print_results(result.nodes)
        return len(documents)

    def _evaluate_slurp(self, nav: Navigator, expression: Expression, printer: ResultPrinter,
                        decoder: Any, request: EvaluateRequest, budget: StepBudget,
                        variables: dict[str, tuple[Node, ...]]) -> int:
        """``--slurp`` (E6, 0926-03 3-12): every input, still individually decoded, becomes one
        array fed to the expression once - unlike ``eval-all``, which evaluates against the
        documents directly (``Context.evaluate_together``), not wrapped in an array value."""
        documents = self._read_all_documents(request, decoder, budget)
        array = Node.sequence()
        array.add_children(documents)
        result = nav.evaluate(self._root_context([array], variables), expression.root)
        printer.print_results(result.nodes)
        return len(documents)

    # ------------------------------------------------------------------ node level API

    def evaluate_nodes(self, expression: str | Expression, documents: Sequence[Node],
                       options: Options | None = None) -> list[Node]:
        options = options or Options()
        compiled = expression if isinstance(expression, Expression) else self.compile(expression)
        env = self.make_env(options)
        nav = Navigator(env)
        result = nav.evaluate(self._root_context(documents), compiled.root)
        return list(result.nodes)
