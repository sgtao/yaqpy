"""Request / result objects shared by every adapter (design doc 11-1)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from pyyq.options import Options


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


@dataclass(frozen=True, slots=True)
class EvaluateResult:
    output: str | None
    printed_anything: bool
    document_count: int
    warnings: tuple[str, ...]
    elapsed_seconds: float


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
