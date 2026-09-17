"""Per-operator preference objects carried on an Operation (Go's ``Preferences``)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TraversePrefs:
    dont_follow_alias: bool = False
    include_map_keys: bool = False
    dont_auto_create: bool = False
    dont_include_map_values: bool = False
    optional_traverse: bool = False
    exact_key_match: bool = False


@dataclass(frozen=True, slots=True)
class AssignPrefs:
    dont_overwrite_anchor: bool = False
    only_write_null: bool = False
    clobber_custom_tags: bool = False


@dataclass(frozen=True, slots=True)
class MultiplyPrefs:
    append_arrays: bool = False
    deep_merge_arrays: bool = False
    traverse: TraversePrefs = field(default_factory=TraversePrefs)
    assign: AssignPrefs = field(default_factory=AssignPrefs)


@dataclass(frozen=True, slots=True)
class RecursiveDescentPrefs:
    traverse: TraversePrefs = field(default_factory=TraversePrefs)
    recurse_array: bool = False


@dataclass(frozen=True, slots=True)
class CommentPrefs:
    line_comment: bool = False
    head_comment: bool = False
    foot_comment: bool = False


@dataclass(frozen=True, slots=True)
class ComparePrefs:
    or_equal: bool = False
    greater: bool = False


@dataclass(frozen=True, slots=True)
class EnvPrefs:
    string_value: bool = False


@dataclass(frozen=True, slots=True)
class ParentPrefs:
    level: int = 1


@dataclass(frozen=True, slots=True)
class AssignVarPrefs:
    is_reference: bool = False


@dataclass(frozen=True, slots=True)
class ExpressionPrefs:
    expression: str = ""


@dataclass(frozen=True, slots=True)
class EncoderPrefs:
    format: str = "yaml"
    indent: int = 2


@dataclass(frozen=True, slots=True)
class DecoderPrefs:
    format: str = "yaml"


@dataclass(frozen=True, slots=True)
class FlattenPrefs:
    depth: int = -1
