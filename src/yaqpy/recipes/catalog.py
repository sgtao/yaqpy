"""The recipes that ship with yaqpy (``recipes/builtin/<name>.yaqpy`` + ``<name>.recipe.yaml``)."""

from __future__ import annotations

import threading
from importlib import resources

from yaqpy.errors import RecipeError
from yaqpy.recipes.loader import build_recipe
from yaqpy.recipes.model import Recipe

_EXPRESSION_SUFFIX = ".yaqpy"
_METADATA_SUFFIX = ".recipe.yaml"

_lock = threading.Lock()
_cache: dict[str, Recipe] | None = None


def _builtin_dir():  # noqa: ANN202 - importlib.resources Traversable
    return resources.files("yaqpy.recipes").joinpath("builtin")


def builtin_recipes() -> dict[str, Recipe]:
    """Every bundled recipe by name, in name order (read once)."""
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load_builtin()
    return _cache


def _load_builtin() -> dict[str, Recipe]:
    directory = _builtin_dir()
    if not directory.is_dir():
        return {}
    found: dict[str, Recipe] = {}
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(_EXPRESSION_SUFFIX):
            continue
        name = entry.name[: -len(_EXPRESSION_SUFFIX)]
        sidecar = directory.joinpath(name + _METADATA_SUFFIX)
        if not sidecar.is_file():
            raise RecipeError(f"bundled recipe {name} has no {name}{_METADATA_SUFFIX}")

        def read_related(related: str) -> str:
            return directory.joinpath(related).read_text(encoding="utf-8")

        found[name] = build_recipe(
            name=name, expression=entry.read_text(encoding="utf-8"),
            metadata=sidecar.read_text(encoding="utf-8"), origin="builtin",
            read_related=read_related)
    return found


def find_builtin(name: str) -> Recipe:
    recipes = builtin_recipes()
    try:
        return recipes[name]
    except KeyError:
        available = ", ".join(recipes) or "(none)"
        raise RecipeError(f"unknown recipe {name!r}. Bundled recipes: {available}. "
                          f"To use your own, give its file: --recipe ./my.yaqpy") from None
