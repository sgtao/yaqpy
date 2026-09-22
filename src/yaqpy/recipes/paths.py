"""Path patterns for recipe metadata (``carries`` / ``drops``): ``.a.b``, ``.items[]``, ``.parts[type!=text]``.

* ``.name``      a mapping key
* ``[]``         any item of a sequence
* ``[key=text]`` an item that is a mapping whose ``key`` has the value ``text``
* ``[key!=text]`` an item that is a mapping whose ``key`` is missing or has another value

A pattern is checked against plain Python data (the parsed input of a conversion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MISSING = object()


@dataclass(frozen=True, slots=True)
class Segment:
    kind: str                 # "key" | "any" | "filter"
    key: str = ""
    op: str = ""              # "=" | "!="
    value: str = ""


Pattern = tuple[Segment, ...]


def parse_pattern(text: str) -> Pattern:
    """Parse ``.a.b[].c`` into segments. ``.`` alone is the root (no segments)."""
    if not text.startswith("."):
        raise ValueError(f"a path pattern starts with '.': {text!r}")
    segments: list[Segment] = []
    i = 1 if text != "." else 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "[":
            end = text.find("]", i)
            if end < 0:
                raise ValueError(f"missing ']' in the path pattern {text!r}")
            body = text[i + 1:end]
            if body == "":
                segments.append(Segment("any"))
            elif "!=" in body:
                key, value = body.split("!=", 1)
                segments.append(Segment("filter", key, "!=", value))
            elif "=" in body:
                key, value = body.split("=", 1)
                segments.append(Segment("filter", key, "=", value))
            else:
                raise ValueError(f"unknown filter [{body}] in the path pattern {text!r}")
            i = end + 1
            if i < n and text[i] == ".":
                i += 1
        else:
            j = i
            while j < n and text[j] not in ".[":
                j += 1
            name = text[i:j]
            if name == "":
                raise ValueError(f"empty key in the path pattern {text!r}")
            segments.append(Segment("key", name))
            i = j + 1 if j < n and text[j] == "." else j
    return tuple(segments)


def scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def _segment_matches(seg: Segment, kind: str, token: Any, value: Any) -> bool:
    if seg.kind == "key":
        return kind == "key" and token == seg.key
    if kind != "index":
        return False
    if seg.kind == "any":
        return True
    if not isinstance(value, dict):
        return False
    actual = value.get(seg.key, _MISSING)
    if seg.op == "=":
        return actual is not _MISSING and scalar_text(actual) == seg.value
    return actual is _MISSING or scalar_text(actual) != seg.value


def find_values(data: Any, pattern: Pattern) -> list[tuple[str, Any]]:
    """``(concrete path, value)`` for everything the pattern matches, e.g.
    ``(".messages[1].content[0].image_url", {...})``."""
    found: list[tuple[str, Any]] = []

    def walk(node: Any, depth: int, path: str) -> None:
        if depth == len(pattern):
            found.append((path or ".", node))
            return
        seg = pattern[depth]
        if isinstance(node, dict):
            if seg.kind == "key" and seg.key in node:
                walk(node[seg.key], depth + 1, f"{path}.{seg.key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if _segment_matches(seg, "index", index, item):
                    walk(item, depth + 1, f"{path}[{index}]")

    walk(data, 0, "")
    return found


def find_matches(data: Any, pattern: Pattern) -> list[str]:
    """The concrete paths (``.messages[1].content[0].image_url``) that the pattern matches."""
    return [path for path, _ in find_values(data, pattern)]


def find_unlisted(data: Any, patterns: list[Pattern]) -> list[str]:
    """Paths of ``data`` that no pattern covers.

    A path is covered when a pattern matches it exactly (everything below it is then covered too),
    or when it is the beginning of a longer pattern (the walk goes on below it). What is
    neither is reported once, at its topmost path.
    """
    unlisted: list[str] = []

    def relation(tokens: list[tuple[str, Any, Any]], pattern: Pattern) -> str:
        if len(pattern) < len(tokens):
            return ""
        for (kind, token, value), seg in zip(tokens, pattern):
            if not _segment_matches(seg, kind, token, value):
                return ""
        return "exact" if len(pattern) == len(tokens) else "prefix"

    def walk(node: Any, tokens: list[tuple[str, Any, Any]], path: str) -> None:
        if isinstance(node, dict):
            children = [("key", key, value, f"{path}.{key}") for key, value in node.items()]
        elif isinstance(node, list):
            children = [("index", i, value, f"{path}[{i}]") for i, value in enumerate(node)]
        else:
            return
        for kind, token, value, label in children:
            below = tokens + [(kind, token, value)]
            relations = {relation(below, p) for p in patterns}
            if "exact" in relations:
                continue
            if "prefix" in relations:
                walk(value, below, label)
                continue
            unlisted.append(label)

    walk(data, [], "")
    return unlisted
