"""What a conversion did: what it dropped, what it added by itself, what changed, and whether the
result follows the target schema.

Nothing here is guessed. The dropped items come from the recipe's own metadata (``drops`` are
looked for in the input; whatever the input holds that ``carries`` and ``drops`` do not mention is
reported as not handled), the added items from ``adds``, the differences from a comparison of the
two documents, and the issues from the target schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yaqpy.recipes.conform import Issue, check
from yaqpy.recipes.diff import Change, diff
from yaqpy.recipes.model import Recipe
from yaqpy.recipes.paths import find_unlisted, find_values, parse_pattern

NOT_HANDLED = "not handled by the recipe (listed in neither carries nor drops)"


@dataclass(frozen=True, slots=True)
class DroppedItem:
    path: str                       # the pattern of a declared drop, or the path that was not handled
    reason: str
    declared: bool                  # False: the recipe never mentions it
    where: tuple[str, ...] = ()     # concrete paths in the input (declared drops)


@dataclass(frozen=True, slots=True)
class AddedItem:
    path: str
    value: Any
    reason: str


@dataclass(frozen=True, slots=True)
class RecipeReport:
    dropped: tuple[DroppedItem, ...]
    added: tuple[AddedItem, ...]
    changes: tuple[Change, ...]
    issues: tuple[Issue, ...]
    notes: tuple[str, ...] = ()
    checked_drops: bool = False     # False: the recipe does not say what it carries or drops
    checked_schema: bool = False    # False: the recipe has no target schema

    @property
    def not_handled(self) -> tuple[DroppedItem, ...]:
        return tuple(item for item in self.dropped if not item.declared)

    @property
    def clean(self) -> bool:
        """Nothing was lost without the recipe saying so, and the result follows the target."""
        return not self.not_handled and not self.issues


def analyse(recipe: Recipe, source: Any, result: Any, *, extra_documents: int = 0) -> RecipeReport:
    dropped: list[DroppedItem] = []
    if recipe.can_report_drops:
        for rule in recipe.drops:
            found = find_values(source, parse_pattern(rule.path))
            if found:
                dropped.append(DroppedItem(rule.path, rule.reason, True, tuple(p for p, _ in found)))
        patterns = [parse_pattern(p) for p in recipe.carries] + [parse_pattern(r.path) for r in recipe.drops]
        dropped.extend(DroppedItem(path, NOT_HANDLED, False, (path,))
                       for path in find_unlisted(source, patterns))

    added: list[AddedItem] = []
    for rule in recipe.adds:
        if any(find_values(source, parse_pattern(p)) for p in rule.unless):
            continue
        for path, value in find_values(result, parse_pattern(rule.path)):
            added.append(AddedItem(path, value, rule.reason))

    issues = check(result, recipe.target_schema) if recipe.target_schema is not None else []
    notes = ()
    if extra_documents > 0:
        notes = (f"the input has {extra_documents} more document(s); only the first one is compared",)
    return RecipeReport(
        dropped=tuple(dropped), added=tuple(added), changes=tuple(diff(source, result)),
        issues=tuple(issues), notes=notes, checked_drops=recipe.can_report_drops,
        checked_schema=recipe.target_schema is not None)
