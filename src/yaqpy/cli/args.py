"""Turn parsed flags into an EvaluateRequest - a pure function (design doc 12-3)."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.formats.registry import FormatRegistry, builtin_formats
from yaqpy.options import (
    CsvOptions, Limits, Options, PropertiesOptions, SchemaOptions, SecurityPolicy, TomlOptions,
    ToonOptions, XmlOptions, YamlOptions,
)

_TOON_DELIMITERS = {"comma": ",", "tab": "\t", "pipe": "|"}


class InvocationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class Invocation:
    request: EvaluateRequest
    warnings: tuple[str, ...]
    show_usage: bool = False


def _is_auto(value: str) -> bool:
    return value in ("", "auto", "a")


def process_args(ns: argparse.Namespace, *, stdin_is_pipe: bool, file_exists: Callable[[str], bool],
                 read_file: Callable[[str], str]) -> tuple[str, list[str]]:
    """Go's ``processArgs`` + ``processStdInArgs``."""
    expression = ns.expression
    args = list(ns.args)
    expression_file = ns.from_file
    # stdin handling
    if not (ns.null_input or not stdin_is_pipe or len(args) > 1
            or (len(args) > 0 and file_exists(args[0]))):
        if "-" not in args:
            args.append("-")
    maybe_first_is_file = len(args) > 0 and file_exists(args[0])
    if expression_file == "" and maybe_first_is_file and args[0].endswith(".yq"):
        expression_file = args[0]
        args = args[1:]
    if expression_file != "":
        expression = read_file(expression_file).replace("\r\n", "\n")
    if expression == "" and args and args[0] != "-" and not file_exists(args[0]):
        expression = args[0]
        args = args[1:]
    return expression, args


def resolve_invocation(ns: argparse.Namespace, *, stdin_is_pipe: bool,
                       file_exists: Callable[[str], bool], read_file: Callable[[str], str],
                       formats: FormatRegistry | None = None) -> Invocation:
    formats = formats or builtin_formats()
    warnings: list[str] = []
    expression, files = process_args(ns, stdin_is_pipe=stdin_is_pipe, file_exists=file_exists,
                                     read_file=read_file)
    # validation (Go's validateCommandFlags)
    if ns.inplace and (not files or files[0] == "-"):
        raise InvocationError("write in place flag only applicable when giving an expression and at least one file")
    if ns.front_matter:
        raise InvocationError("front matter is not supported yet (phase 2)")
    if ns.split_exp:
        raise InvocationError("split expressions are not supported yet (phase 2)")
    if ns.null_input and files:
        raise InvocationError("cannot pass files in when using null-input flag")
    if ns.indent < 0:
        raise InvocationError("indent must not be negative")
    if ns.schema_enum_max < 0:
        raise InvocationError("--schema-enum-max must not be negative")
    if ns.schema:
        expression = f"{expression} | schema" if expression else "schema"

    # formats (Go's configureInputFormat / configureOutputFormat)
    input_filename = files[0] if files else ""
    input_format = ns.input_format
    output_format = ns.output_format
    if ns.toon:
        # --toon is shorthand for -o toon; an explicit different -o is a contradiction
        if not _is_auto(output_format) and not formats.get(output_format).matches("toon"):
            raise InvocationError("--toon cannot be combined with -o/--output-format "
                                  f"'{output_format}'")
        output_format = "toon"
    if _is_auto(input_format):
        input_format = formats.from_filename(input_filename).name
        if _is_auto(output_format):
            output_format = input_format
    elif _is_auto(output_format):
        guessed = formats.from_filename(input_filename).name
        if input_filename not in ("", "-") and guessed != "yaml":
            warnings.append(
                f"yaqpy default output is now 'auto' (based on the filename extension). Normally "
                f"yaqpy would output '{guessed}', but for backwards compatibility 'yaml' has been "
                f"set. Please use -oy to specify yaml, or drop the -p flag.")
        output_format = "yaml"
    input_spec = formats.get(input_format)
    output_spec = formats.get(output_format)
    unwrap = ns.unwrap_scalar
    if unwrap is None:
        unwrap = output_spec.unwrap_scalar_default

    security = SecurityPolicy(
        allow_env=not ns.security_disable_env_ops,
        allow_file=not ns.security_disable_file_ops,
        allow_system=ns.security_enable_system_operator,
    )
    options = Options(
        input_format=input_spec.name,
        output_format=output_spec.name,
        unwrap_scalar=unwrap,
        indent=ns.indent,
        null_input=ns.null_input,
        nul_separated_output=ns.nul_output,
        pretty_print=ns.pretty_print,
        string_interpolation=ns.string_interpolation,
        yaml=YamlOptions(
            indent=ns.indent,
            compact_sequence_indent=ns.yaml_compact_seq_indent,
            print_doc_separators=not ns.no_doc,
            leading_content_preprocessing=ns.header_preprocess,
            fix_merge_anchor_to_spec=ns.yaml_fix_merge_anchor_to_spec,
        ),
        props=PropertiesOptions(
            key_value_separator=ns.properties_separator,
            use_array_brackets=ns.properties_array_brackets,
        ),
        toon=ToonOptions(
            delimiter=_TOON_DELIMITERS[ns.toon_delimiter],
            indent=ns.indent if ns.indent >= 1 else 2,
        ),
        xml=XmlOptions(
            indent=ns.indent,
            attribute_prefix=ns.xml_attribute_prefix,
            content_name=ns.xml_content_name,
            strict_mode=ns.xml_strict_mode,
            keep_namespace=ns.xml_keep_namespace,
            raw_token=ns.xml_raw_token,
            proc_inst_prefix=ns.xml_proc_inst_prefix,
            directive_name=ns.xml_directive_name,
            skip_proc_inst=ns.xml_skip_proc_inst,
            skip_directives=ns.xml_skip_directives,
        ),
        csv=CsvOptions(
            separator=ns.csv_separator,
            auto_parse=ns.csv_auto_parse,
            tsv_auto_parse=ns.tsv_auto_parse,
        ),
        toml=TomlOptions(allow_lossy=ns.toml_allow_lossy),
        schema=SchemaOptions(strict=ns.schema_strict, enum_max=ns.schema_enum_max,
                             per_doc=ns.schema_per_doc),
        security=security,
        limits=Limits(),
    )
    mode = EvalMode.ALL if ns.command == "eval-all" else EvalMode.STREAM
    show_usage = not files and not ns.null_input
    request = EvaluateRequest(
        expression=expression,
        inputs=tuple(InputSource(name) for name in files),
        mode=mode,
        options=options,
        in_place=ns.inplace,
        exit_status=ns.exit_status,
        input_format=input_spec.name,
        output_format=output_spec.name,
        unwrap_scalar=unwrap,
    )
    return Invocation(request, tuple(warnings), show_usage)
