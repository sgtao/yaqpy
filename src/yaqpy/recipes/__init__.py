"""Recipes: named, reusable conversions (a yaqpy extension; the Go yq has nothing like it).

A recipe is an ordinary yaqpy expression in a ``.yaqpy`` file, plus optional YAML metadata in
``<name>.recipe.yaml`` that says what the expression carries over, what it drops on purpose, what
it adds by itself, which JSON Schema the result must follow, and a few test cases. The metadata is
what makes a conversion checkable: it is the source of the "dropped items" list and of the target
schema comparison. See USAGE.ja.md (レシピ).
"""

from __future__ import annotations

from yaqpy.recipes.catalog import builtin_recipes, find_builtin
from yaqpy.recipes.loader import build_recipe
from yaqpy.recipes.model import AddRule, DropRule, Recipe, RecipeTest

__all__ = ["AddRule", "DropRule", "Recipe", "RecipeTest", "build_recipe", "builtin_recipes",
           "find_builtin"]
