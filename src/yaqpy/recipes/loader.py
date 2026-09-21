"""Read a recipe: the expression text plus the (optional) YAML metadata that goes with it."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from yaqpy.core.model.convert import to_python
from yaqpy.errors import FormatError, RecipeError
from yaqpy.formats.yaml.codec import YamlDecoder
from yaqpy.options import Options
from yaqpy.recipes.model import AddRule, DropRule, Recipe, RecipeTest
from yaqpy.recipes.paths import parse_pattern

METADATA_KEYS = frozenset({
    "name", "title", "description", "version", "input", "output", "target_schema", "prune",
    "carries", "drops", "adds", "tests", "notes", "expression", "expression_file",
})
PRUNE_MODES = ("nulls", "empties")   # not "null": YAML reads that as the null value


def parse_metadata(text: str, origin: str) -> dict[str, Any]:
    try:
        docs = list(YamlDecoder(Options()).decode_documents(text))
    except FormatError as e:
        raise RecipeError(f"{origin}: cannot read the metadata: {e}") from None
    if not docs:
        return {}
    data = to_python(docs[0])
    if not isinstance(data, dict):
        raise RecipeError(f"{origin}: the metadata must be a mapping")
    return data


def _text(data: dict[str, Any], key: str, origin: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise RecipeError(f"{origin}: '{key}' must be text")
    return str(value)


def _text_list(data: dict[str, Any], key: str, origin: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RecipeError(f"{origin}: '{key}' must be a list of text")
    return tuple(value)


def _pattern_ok(pattern: str, key: str, origin: str) -> str:
    try:
        parse_pattern(pattern)
    except ValueError as e:
        raise RecipeError(f"{origin}: '{key}': {e}") from None
    return pattern


def _rules(data: dict[str, Any], key: str, origin: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise RecipeError(f"{origin}: '{key}' must be a list of mappings")
    for rule in value:
        if not isinstance(rule.get("path"), str):
            raise RecipeError(f"{origin}: every entry of '{key}' needs a 'path'")
        _pattern_ok(rule["path"], key, origin)
    return value


def _format_of(data: dict[str, Any], key: str, origin: str) -> tuple[str, str]:
    section = data.get(key)
    if section is None:
        return "json", ""
    if not isinstance(section, dict):
        raise RecipeError(f"{origin}: '{key}' must be a mapping (format, api)")
    unknown = set(section) - {"format", "api"}
    if unknown:
        raise RecipeError(f"{origin}: unknown key in '{key}': {', '.join(sorted(unknown))}")
    return _text(section, "format", origin, "json"), _text(section, "api", origin)


def build_recipe(*, name: str, expression: str | None, metadata: str | None, origin: str,
                 read_related: Callable[[str], str] | None = None) -> Recipe:
    """Assemble a recipe. ``read_related`` reads a file that sits next to the recipe (a target
    schema, or the expression of a metadata-only recipe); it is given the name written in the metadata.
    """
    normalise = (lambda text: text.replace("\r\n", "\n"))
    if metadata is None:
        if expression is None:
            raise RecipeError(f"{origin}: no expression")
        return Recipe(name=name, expression=normalise(expression), origin=origin)
    data = parse_metadata(metadata, origin)
    unknown = set(data) - METADATA_KEYS
    if unknown:
        raise RecipeError(f"{origin}: unknown key in the metadata: {', '.join(sorted(unknown))}")
    if expression is None:
        if isinstance(data.get("expression"), str):
            expression = data["expression"]
        elif isinstance(data.get("expression_file"), str) and read_related is not None:
            expression = read_related(data["expression_file"])
        else:
            raise RecipeError(f"{origin}: the metadata needs 'expression' or 'expression_file'")
    input_format, input_api = _format_of(data, "input", origin)
    output_format, output_api = _format_of(data, "output", origin)

    prune = _text_list(data, "prune", origin)
    for mode in prune:
        if mode not in PRUNE_MODES:
            raise RecipeError(f"{origin}: 'prune' takes {' and '.join(PRUNE_MODES)}, not {mode!r}")

    schema = data.get("target_schema")
    if isinstance(schema, str):
        if read_related is None:
            raise RecipeError(f"{origin}: cannot read the target schema {schema!r}")
        try:
            schema = json.loads(read_related(schema))
        except (OSError, ValueError) as e:
            raise RecipeError(f"{origin}: cannot read the target schema {data['target_schema']!r}: {e}") from None
    if schema is not None and not isinstance(schema, dict):
        raise RecipeError(f"{origin}: 'target_schema' must be a file name or a mapping")

    drops = tuple(DropRule(r["path"], str(r.get("reason", ""))) for r in _rules(data, "drops", origin))
    adds = []
    for rule in _rules(data, "adds", origin):
        unless = rule.get("unless") or []
        if not isinstance(unless, list) or not all(isinstance(u, str) for u in unless):
            raise RecipeError(f"{origin}: 'unless' must be a list of paths")
        adds.append(AddRule(rule["path"], str(rule.get("reason", "")),
                            tuple(_pattern_ok(u, "adds", origin) for u in unless)))
    carries = tuple(_pattern_ok(p, "carries", origin) for p in _text_list(data, "carries", origin))

    tests: list[RecipeTest] = []
    raw_tests = data.get("tests") or []
    if not isinstance(raw_tests, list):
        raise RecipeError(f"{origin}: 'tests' must be a list")
    for index, case in enumerate(raw_tests):
        if not isinstance(case, dict) or "input" not in case or "expected" not in case:
            raise RecipeError(f"{origin}: test {index + 1} needs 'input' and 'expected'")
        tests.append(RecipeTest(str(case.get("name", f"case {index + 1}")), case["input"], case["expected"]))

    version = data.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool):
        raise RecipeError(f"{origin}: 'version' must be an integer")
    return Recipe(
        name=_text(data, "name", origin, name), expression=normalise(expression),
        title=_text(data, "title", origin), description=_text(data, "description", origin),
        origin=origin, version=version, input_format=input_format, output_format=output_format,
        input_api=input_api, output_api=output_api, target_schema=schema, prune=prune,
        carries=carries, drops=drops, adds=tuple(adds), tests=tuple(tests),
        notes=_text_list(data, "notes", origin),
    )
