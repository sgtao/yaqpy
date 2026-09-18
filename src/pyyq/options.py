"""Immutable configuration objects (design doc section 10-1).

Go's yq keeps its preferences in package-level variables. pyyq passes an
``Options`` object per call instead so that several evaluations with different
settings can run at the same time in one process (NFR-03).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityPolicy:
    allow_env: bool = False
    allow_file: bool = False
    allow_system: bool = False

    @classmethod
    def strict(cls) -> SecurityPolicy:
        """Default for the library and for the API service: nothing is allowed."""
        return cls()

    @classmethod
    def cli_default(cls) -> SecurityPolicy:
        """Same defaults as the Go CLI: env and file operators on, system off."""
        return cls(allow_env=True, allow_file=True, allow_system=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Limits:
    max_input_bytes: int = 50 * 1024 * 1024
    max_depth: int = 1000
    max_alias_expansion: int = 100_000
    max_steps: int | None = None
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_input_bytes <= 0:
            raise ValueError("max_input_bytes must be positive")
        if self.max_depth <= 0:
            raise ValueError("max_depth must be positive")
        if self.max_steps is not None and self.max_steps <= 0:
            raise ValueError("max_steps must be positive when set")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when set")


@dataclass(frozen=True, slots=True, kw_only=True)
class YamlOptions:
    indent: int = 2
    compact_sequence_indent: bool = False
    print_doc_separators: bool = True
    leading_content_preprocessing: bool = True
    fix_merge_anchor_to_spec: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonOptions:
    indent: int = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class PropertiesOptions:
    key_value_separator: str = " = "
    use_array_brackets: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ToonOptions:
    """TOON (Token-Oriented Object Notation) settings, spec v4.1."""

    delimiter: str = ","          # "," | "	" | "|"
    indent: int = 2
    strict: bool = True           # decoder: validate counts, indentation, duplicate keys
    keyed_tabular: bool = True    # encoder: use `[N:]{fields}:` for uniform object-of-objects

    def __post_init__(self) -> None:
        if self.delimiter not in (",", "	", "|"):
            raise ValueError("toon delimiter must be ',', tab or '|'")
        if self.indent < 1:
            raise ValueError("toon indent must be at least 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class Options:
    input_format: str = "yaml"
    output_format: str | None = None
    unwrap_scalar: bool | None = None
    indent: int = 2
    null_input: bool = False
    nul_separated_output: bool = False
    pretty_print: bool = False
    yaml: YamlOptions = field(default_factory=YamlOptions)
    json: JsonOptions = field(default_factory=JsonOptions)
    props: PropertiesOptions = field(default_factory=PropertiesOptions)
    toon: ToonOptions = field(default_factory=ToonOptions)
    security: SecurityPolicy = field(default_factory=SecurityPolicy.strict)
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self) -> None:
        if self.indent < 0:
            raise ValueError("indent must not be negative")
        if not self.input_format:
            raise ValueError("input_format must not be empty")

    @property
    def effective_output_format(self) -> str:
        return self.output_format or self.input_format
