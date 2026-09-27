"""The advice a recipe attaches to schema issues (``hints:`` in its metadata)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from yaqpy.recipes.conform import Issue
from yaqpy.recipes.model import HintRule, Recipe


def _path_regex(pattern: str) -> re.Pattern[str]:
    """``.messages[].role`` matches ``.messages[0].role``, ``.messages[12].role`` ..."""
    return re.compile(re.escape(pattern).replace(r"\[\]", r"\[\d+\]") + r"\Z")


def applies(rule: HintRule, issue: Issue) -> bool:
    if rule.issue and rule.issue != issue.kind:
        return False
    return not rule.path or _path_regex(rule.path).match(issue.path) is not None


def _quoted(name: str) -> str:
    return f'"{name}"' if " " in name else name


def hints_for(recipe: Recipe, issues: Iterable[Issue], *, input_name: str) -> list[str]:
    """The texts of the hints that apply to the issues, each once, in the order the recipe lists them."""
    found: list[str] = []
    for rule in recipe.hints:
        for issue in issues:
            if not applies(rule, issue):
                continue
            text = (rule.text.replace("{recipe}", recipe.name).replace("{input}", _quoted(input_name))
                    .replace("{path}", issue.path))
            if text not in found:
                found.append(text)
    return found
