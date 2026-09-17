"""Node <-> Python object conversion (design doc section 5-4)."""

from __future__ import annotations

import base64
import datetime as _dt
from collections.abc import Mapping, Sequence
from typing import Any

from pyyq.core.model import tags as _tags
from pyyq.core.model.node import Kind, Node, Style
from pyyq.errors import EvaluationError


def to_python(node: Node, *, _depth: int = 0, _max_depth: int = 1000) -> Any:
    if _depth > _max_depth:
        raise EvaluationError("nesting too deep while converting to Python")
    node = node.resolve_alias()
    if node.kind is Kind.MAPPING:
        out: dict[str, Any] = {}
        for key, value in node.map_items():
            out[str(key.value)] = to_python(value, _depth=_depth + 1, _max_depth=_max_depth)
        return out
    if node.kind is Kind.SEQUENCE:
        return [to_python(c, _depth=_depth + 1, _max_depth=_max_depth) for c in node.content]
    tag = node.guess_tag()
    value = node.value
    if tag == "!!null":
        return None
    if tag == "!!bool":
        return node.is_truthy()
    if tag == "!!int":
        try:
            return _tags.parse_int(value)[1]
        except ValueError:
            return value
    if tag == "!!float":
        try:
            return _tags.parse_float(value)
        except ValueError:
            return value
    if tag == "!!binary":
        try:
            return base64.b64decode("".join(value.split()))
        except ValueError:
            return value
    return value


def from_python(obj: Any) -> Node:
    if obj is None:
        return Node.null()
    if isinstance(obj, bool):
        return Node.boolean(obj)
    if isinstance(obj, int):
        return Node.integer(obj)
    if isinstance(obj, float):
        return Node.scalar(_tags.format_float(obj), "!!float")
    if isinstance(obj, str):
        node = Node.string(obj)
        if node.tag == "!!str" and _tags.resolve_plain(obj) != "!!str":
            node.style = Style.DOUBLE_QUOTED
        return node
    if isinstance(obj, bytes):
        return Node.scalar(base64.b64encode(obj).decode("ascii"), "!!binary")
    if isinstance(obj, _dt.datetime):
        return Node.scalar(obj.isoformat(), "!!timestamp")
    if isinstance(obj, _dt.date):
        return Node.scalar(obj.isoformat(), "!!timestamp")
    if isinstance(obj, Mapping):
        node = Node.mapping()
        for key, value in obj.items():
            node.add_key_value(from_python(str(key)), from_python(value))
        return node
    if isinstance(obj, Sequence):
        node = Node.sequence()
        for item in obj:
            node.add_child(from_python(item))
        return node
    if isinstance(obj, (set, frozenset)):
        node = Node.sequence()
        for item in obj:
            node.add_child(from_python(item))
        return node
    raise TypeError(f"cannot convert {type(obj).__name__} to a Node")
