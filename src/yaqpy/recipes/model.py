"""The recipe: an expression, plus metadata that lets a conversion be checked and explained."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DropRule:
    """An input path the recipe does not carry over, and why."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class AddRule:
    """An output path the recipe fills in by itself when none of the ``unless`` input paths exists."""

    path: str
    reason: str
    unless: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecipeTest:
    """One case of the recipe's own self-test: an input and the output it must give."""

    name: str
    input: Any
    expected: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class Recipe:
    name: str
    expression: str
    title: str = ""
    description: str = ""
    origin: str = "builtin"                     # "builtin" or the file the recipe was read from
    version: int = 1
    input_format: str = "json"
    output_format: str = "json"
    input_api: str = ""                         # informational, e.g. "openai-chat-completions"
    output_api: str = ""
    target_schema: dict[str, Any] | None = None  # JSON Schema of the result (a yaqpy-generated or hand-written one)
    prune: tuple[str, ...] = ()                 # "nulls" and/or "empties": tidy the whole result
    carries: tuple[str, ...] = ()               # input paths the expression reads
    drops: tuple[DropRule, ...] = ()
    adds: tuple[AddRule, ...] = ()
    tests: tuple[RecipeTest, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def can_report_drops(self) -> bool:
        """Only a recipe that says what it carries or drops can be checked for the rest."""
        return bool(self.carries or self.drops)
