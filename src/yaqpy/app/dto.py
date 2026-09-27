"""Request / result objects shared by every adapter (design doc 11-1)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from yaqpy.options import Options


class EvalMode(enum.Enum):
    STREAM = "stream"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class InputSource:
    name: str                       # file name, "-" for stdin, "<text>" for in-memory input
    text: str | None = None         # None -> read through the FileSystemPort


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluateRequest:
    expression: str
    inputs: tuple[InputSource, ...] = ()
    mode: EvalMode = EvalMode.STREAM
    options: Options = field(default_factory=Options)
    in_place: bool = False
    exit_status: bool = False
    input_format: str | None = None     # resolved format name (None -> from options)
    output_format: str | None = None
    unwrap_scalar: bool | None = None
    split_expression: str = ""          # -s: name a file per result with this expression
    slurp: bool = False                 # --slurp: all inputs as one array, not eval-all's stream
    # --arg NAME VALUE / --argjson NAME JSON (E6, 0926-03 3-12): bound as $NAME and folded into
    # $ARGS.named; repeated names keep only the last (jq's own rule). --args/--jsonargs fill
    # $ARGS.positional instead of being read as input files.
    named_args: tuple[tuple[str, str], ...] = ()
    named_json_args: tuple[tuple[str, str], ...] = ()
    positional_args: tuple[str, ...] | None = None
    positional_args_json: bool = False


@dataclass(frozen=True, slots=True)
class EvaluateResult:
    output: str | None
    printed_anything: bool
    document_count: int
    warnings: tuple[str, ...]
    elapsed_seconds: float
    input_format: str = ""      # actually used (after "auto" was resolved)
    output_format: str = ""     # actually used


@dataclass(frozen=True, slots=True)
class ExpressionInfo:
    expression: str
    valid: bool
    message: str = ""
    position: int = -1


@dataclass(frozen=True, slots=True)
class FormatsInfo:
    input_formats: tuple[str, ...]
    output_formats: tuple[str, ...]
