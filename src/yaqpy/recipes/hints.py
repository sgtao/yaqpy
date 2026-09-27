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
    if rule.dropped:
        return False
    if rule.issue and rule.issue != issue.kind:
        return False
    return not rule.path or _path_regex(rule.path).match(issue.path) is not None


def _quoted(name: str) -> str:
    return f'"{name}"' if " " in name else name


def hints_for(recipe: Recipe, issues: Iterable[Issue], *, input_name: str,
              dropped: Iterable[str] = ()) -> list[str]:
    """The texts of the hints that apply, each once, in the order the recipe lists them.

    ``issues`` are the schema issues of the result; ``dropped`` are the ``drops`` paths (as the recipe
    writes them) that were found in the input.
    """
    issues, dropped = list(issues), list(dropped)
    found: list[str] = []
    for rule in recipe.hints:
        if rule.dropped:
            places = [d for d in dropped if d == rule.dropped]
        else:
            places = [i.path for i in issues if applies(rule, i)]
        for place in places:
            text = (rule.text.replace("{recipe}", recipe.name).replace("{input}", _quoted(input_name))
                    .replace("{path}", place))
            if text not in found:
                found.append(text)
    return found
