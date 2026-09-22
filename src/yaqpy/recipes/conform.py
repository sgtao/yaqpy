"""Compare a converted result with the JSON Schema of its target: missing, extra and wrong-typed items.

This is deliberately *not* a full JSON Schema validator (that is the ``validate`` of a later
release). It understands what a description of an API request needs and reports each mismatch with
its path, so that "the conversion ran" can be told from "the result looks like what the API takes":

``type`` ``enum`` ``const`` ``required`` ``properties`` ``additionalProperties`` ``items``
``minItems`` ``maxItems`` ``minimum`` ``maximum`` ``anyOf`` ``oneOf`` ``allOf`` and local
``$ref`` (``#/$defs/name``). Other keywords are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MISSING = "missing"      # a required key is not there
EXTRA = "extra"          # a key the schema does not allow
TYPE = "type"            # a value of another type
VALUE = "value"          # not one of the allowed values, or not matching any alternative
RANGE = "range"          # below the minimum / above the maximum
SIZE = "size"            # too few / too many items

_MAX_REF_DEPTH = 50


@dataclass(frozen=True, slots=True)
class Issue:
    path: str
    kind: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def check(data: Any, schema: dict[str, Any] | bool) -> list[Issue]:
    """The differences between ``data`` and ``schema`` (empty when it matches)."""
    root = schema if isinstance(schema, dict) else {}
    return _Checker(root).visit(data, schema, "")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _is_type(value: Any, wanted: str) -> bool:
    actual = _type_name(value)
    if wanted == "number":
        return actual in ("integer", "number")
    if wanted == "integer":
        return actual == "integer" or (actual == "number" and float(value).is_integer())
    return actual == wanted


class _Checker:
    def __init__(self, root: dict[str, Any]) -> None:
        self.root = root

    def _resolve(self, schema: dict[str, Any]) -> dict[str, Any]:
        for _ in range(_MAX_REF_DEPTH):
            ref = schema.get("$ref")
            if not isinstance(ref, str):
                return schema
            if not ref.startswith("#/"):
                return {}                   # only local references are followed
            target: Any = self.root
            for part in ref[2:].split("/"):
                target = target.get(part) if isinstance(target, dict) else None
            if not isinstance(target, dict):
                return {}
            merged = {k: v for k, v in schema.items() if k != "$ref"}
            schema = {**target, **merged}
        return {}

    def visit(self, value: Any, schema: dict[str, Any] | bool, path: str) -> list[Issue]:
        if schema is True or not isinstance(schema, dict):
            return []
        if schema is False:
            return [Issue(path or ".", VALUE, "no value is allowed here")]
        schema = self._resolve(schema)
        where = path or "."
        issues: list[Issue] = []

        wanted = schema.get("type")
        if wanted is not None:
            names = [wanted] if isinstance(wanted, str) else list(wanted)
            if not any(_is_type(value, n) for n in names):
                return [Issue(where, TYPE, f"expected {' or '.join(names)}, got {_type_name(value)}")]
        if "const" in schema and value != schema["const"]:
            issues.append(Issue(where, VALUE, f"expected {schema['const']!r}, got {value!r}"))
        if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
            allowed = ", ".join(repr(v) for v in schema["enum"])
            issues.append(Issue(where, VALUE, f"{value!r} is not one of {allowed}"))

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                issues.append(Issue(where, RANGE, f"{value} is below the minimum {schema['minimum']}"))
            if "maximum" in schema and value > schema["maximum"]:
                issues.append(Issue(where, RANGE, f"{value} is above the maximum {schema['maximum']}"))

        if isinstance(value, dict):
            issues.extend(self._object(value, schema, path))
        elif isinstance(value, list):
            issues.extend(self._array(value, schema, path))

        for keyword in ("anyOf", "oneOf"):
            alternatives = schema.get(keyword)
            if isinstance(alternatives, list) and alternatives:
                issues.extend(self._one_of(value, alternatives, path))
        if isinstance(schema.get("allOf"), list):
            for part in schema["allOf"]:
                issues.extend(self.visit(value, part, path))
        return issues

    def _object(self, value: dict[str, Any], schema: dict[str, Any], path: str) -> list[Issue]:
        issues: list[Issue] = []
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for key in schema.get("required") or []:
            if key not in value:
                issues.append(Issue(f"{path}.{key}", MISSING, "required, but the result has no such key"))
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            here = f"{path}.{key}"
            if key in properties:
                issues.extend(self.visit(item, properties[key], here))
            elif additional is False:
                issues.append(Issue(here, EXTRA, "the target does not know this key"))
            elif isinstance(additional, dict):
                issues.extend(self.visit(item, additional, here))
        return issues

    def _array(self, value: list[Any], schema: dict[str, Any], path: str) -> list[Issue]:
        issues: list[Issue] = []
        where = path or "."
        if "minItems" in schema and len(value) < schema["minItems"]:
            issues.append(Issue(where, SIZE, f"{len(value)} item(s), at least {schema['minItems']} needed"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            issues.append(Issue(where, SIZE, f"{len(value)} items, at most {schema['maxItems']} allowed"))
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                issues.extend(self.visit(item, items, f"{path}[{index}]"))
        return issues

    def _one_of(self, value: Any, alternatives: list[Any], path: str) -> list[Issue]:
        best: list[Issue] | None = None
        best_rank = (True, 0)
        for alternative in alternatives:
            found = self.visit(value, alternative, path)
            if not found:
                return []
            # an alternative of the right type is closer than one of another type, whatever the counts
            rank = (any(i.kind == TYPE and i.path == (path or ".") for i in found), len(found))
            if best is None or rank < best_rank:
                best, best_rank = found, rank
        # nothing matched: what the closest alternative complains about is the most useful thing to say
        return best or [Issue(path or ".", VALUE, "matches none of the allowed forms")]
