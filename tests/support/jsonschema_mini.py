"""A very small JSON Schema validator for the tests (no third-party package).

It knows exactly the keywords the ``schema`` operator writes: ``type`` (a name or a list),
``properties``, ``required``, ``additionalProperties: false``, ``items``, ``enum`` and ``format``
(``date`` and ``date-time`` are checked by shape). Unknown keywords are ignored, like a
validator would treat annotations. ``validate`` returns the list of problems (empty = valid),
each with the path of the offending value.
"""

from __future__ import annotations

import re
from typing import Any

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:?\d{2})")
KNOWN_TYPES = {"string", "integer", "number", "boolean", "object", "array", "null"}


def _type_of(value: Any) -> set[str]:
    if value is None:
        return {"null"}
    if isinstance(value, bool):
        return {"boolean"}
    if isinstance(value, int):
        return {"integer", "number"}
    if isinstance(value, float):
        return {"number", "integer"} if value.is_integer() else {"number"}
    if isinstance(value, str):
        return {"string"}
    if isinstance(value, list):
        return {"array"}
    if isinstance(value, dict):
        return {"object"}
    raise TypeError(f"not a JSON value: {value!r}")


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    problems: list[str] = []
    types = schema.get("type")
    if types is not None:
        wanted = [types] if isinstance(types, str) else list(types)
        for name in wanted:
            if name not in KNOWN_TYPES:
                problems.append(f"{path}: unknown type {name!r} in the schema")
        if not (_type_of(instance) & set(wanted)):
            problems.append(f"{path}: {instance!r} is not of type {wanted}")
            return problems
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if isinstance(instance, str) and "format" in schema:
        pattern = {"date": _DATE, "date-time": _DATE_TIME}.get(schema["format"])
        if pattern is not None and not pattern.fullmatch(instance):
            problems.append(f"{path}: {instance!r} is not a {schema['format']}")
    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                problems.append(f"{path}: the required key {name!r} is missing")
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                problems.extend(validate(value, properties[name], f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                problems.append(f"{path}: the key {name!r} is not allowed")
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            problems.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return problems


def check_structure(schema: dict[str, Any], path: str = "$") -> list[str]:
    """Structural sanity of a schema written for Draft 2020-12 (keyword types and values)."""
    problems: list[str] = []
    allowed = {"$schema", "type", "format", "enum", "properties", "required", "additionalProperties",
               "items"}
    for key in schema:
        if key not in allowed:
            problems.append(f"{path}: unexpected keyword {key!r}")
    if "$schema" in schema and path != "$":
        problems.append(f"{path}: $schema belongs at the top only")
    if "type" in schema:
        types = schema["type"]
        names = [types] if isinstance(types, str) else types
        if not isinstance(names, list) or not names or len(set(names)) != len(names):
            problems.append(f"{path}: type must be a name or a non-empty list of different names")
        elif not set(names) <= KNOWN_TYPES:
            problems.append(f"{path}: unknown type in {names}")
        elif "integer" in names and "number" in names:
            problems.append(f"{path}: integer is redundant next to number")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict) or not schema["properties"]:
            problems.append(f"{path}: properties must be a non-empty object")
        else:
            for name, sub in schema["properties"].items():
                problems.extend(check_structure(sub, f"{path}.{name}"))
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not required or len(set(required)) != len(required):
            problems.append(f"{path}: required must be a non-empty list of different names")
        elif not set(required) <= set(schema.get("properties", {})):
            problems.append(f"{path}: required names a key that is not in properties")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        problems.append(f"{path}: additionalProperties is only ever written as false")
    if "items" in schema:
        if not isinstance(schema["items"], dict):
            problems.append(f"{path}: items must be a schema")
        else:
            problems.extend(check_structure(schema["items"], f"{path}[]"))
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        problems.append(f"{path}: enum must be a non-empty list")
    return problems
