"""``schema``: a JSON Schema (Draft 2020-12) that describes the data (a yaqpy extension).

The result is an ordinary node tree, so it can be printed as JSON, as YAML or in any other
format, and processed further (``schema | .properties | keys``). All nodes the operator receives
are read as samples of one document shape and merged into one schema; with ``--schema-per-doc``
every node gets its own schema. A file with several documents is one context per document unless
it is read with ``eval-all``.

What is inferred (nothing that the samples do not show):

* ``type``: ``string`` (also dates and binary), ``integer``, ``number`` (a float, or ints and
  floats mixed), ``boolean``, ``null``, ``object``, ``array``. Different types become a list
  (``["string", "null"]``); keywords that belong to one type (``properties`` for objects,
  ``items`` for arrays, ``format`` for strings) stay valid next to the others.
* ``properties`` in the order the keys first appear; ``required`` lists the keys that every
  sample object has; ``additionalProperties`` stays open unless ``--schema-strict``.
* ``items`` merges every array element seen; an empty array says nothing about its items.
* ``format``: ``date-time`` or ``date`` when every string sample is such a timestamp.
* ``enum``: only with ``--schema-enum-max N``, only for strings, only when a value repeats
  (a list of all-different strings is free text, not a set of choices).

Anchors and merge keys are expanded on a copy first, so ``<<`` is not reported as a property.
"""

from __future__ import annotations

import re

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.depth import node_depth
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.core.operators.anchors import explode_node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationLimitError
from yaqpy.options import SchemaOptions

DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAX_DEPTH = 250
"""Deepest data the operator reads (it recurses; deeper input is refused, not truncated)."""

_TYPE_ORDER = ("string", "integer", "number", "boolean", "object", "array", "null")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:?\d{2})")
_ENUM_TRACKING_LIMIT = 200          # stop counting distinct strings beyond this many


class _Shape:
    """Everything seen so far at one place of the data."""

    __slots__ = ("types", "objects", "props", "prop_counts", "items", "strings", "distinct",
                 "formats")

    def __init__(self) -> None:
        self.types: set[str] = set()
        self.objects = 0
        self.props: dict[str, _Shape] = {}
        self.prop_counts: dict[str, int] = {}
        self.items: _Shape | None = None
        self.strings = 0                               # string samples
        self.distinct: dict[str, int] | None = {}      # value -> count; None once there are too many
        self.formats: set[str] = set()                 # "" for a string without a known format


def _string_format(node: Node) -> str:
    if node.tag != "!!timestamp":
        return ""
    if _DATE_TIME.fullmatch(node.value):
        return "date-time"
    if _DATE.fullmatch(node.value):
        return "date"
    return ""


def _observe(shape: _Shape, node: Node, depth: int, nav: Navigator) -> None:
    if depth > MAX_DEPTH:
        raise EvaluationLimitError(f"schema: the data is nested more than {MAX_DEPTH} levels deep",
                                   limit="max_depth")
    nav.env.budget.tick()
    if node.kind is Kind.MAPPING:
        shape.types.add("object")
        shape.objects += 1
        for key, value in node.map_items():
            child = shape.props.get(key.value)
            if child is None:
                child = shape.props[key.value] = _Shape()
            shape.prop_counts[key.value] = shape.prop_counts.get(key.value, 0) + 1
            _observe(child, value, depth + 1, nav)
    elif node.kind is Kind.SEQUENCE:
        shape.types.add("array")
        for item in node.content:
            if shape.items is None:
                shape.items = _Shape()
            _observe(shape.items, item, depth + 1, nav)
    else:
        tag = node.tag
        if tag == "!!null":
            shape.types.add("null")
        elif tag == "!!bool":
            shape.types.add("boolean")
        elif tag == "!!int":
            shape.types.add("integer")
        elif tag == "!!float":
            shape.types.add("number")
        else:
            shape.types.add("string")
            shape.strings += 1
            shape.formats.add(_string_format(node))
            if shape.distinct is not None:
                shape.distinct[node.value] = shape.distinct.get(node.value, 0) + 1
                if len(shape.distinct) > _ENUM_TRACKING_LIMIT:
                    shape.distinct = None


# ----------------------------------------------------------------------------- building the result

def _text(value: str) -> Node:
    return Node(Kind.SCALAR, tag="!!str", value=value)


def _mapping(pairs: list[tuple[str, Node]]) -> Node:
    node = Node.mapping()
    for name, value in pairs:
        key = _text(name)
        key.parent = node
        key.is_map_key = True
        value.parent = node
        value.key = key
        node.content.extend((key, value))
    return node


def _sequence(items: list[Node], *, flow: bool = False) -> Node:
    node = Node.sequence()
    for i, item in enumerate(items):
        index = Node.integer(i)
        index.parent = node
        index.is_map_key = True
        item.parent = node
        item.key = index
        node.content.append(item)
    if flow:
        node.style = Style.FLOW
    return node


def _type_names(shape: _Shape) -> list[str]:
    types = set(shape.types)
    if "number" in types:
        types.discard("integer")                       # every integer is a number
    return [t for t in _TYPE_ORDER if t in types]


def _to_node(shape: _Shape, options: SchemaOptions, *, top: bool = False) -> Node:
    pairs: list[tuple[str, Node]] = []
    if top:
        pairs.append(("$schema", _text(DIALECT)))
    types = _type_names(shape)
    if len(types) == 1:
        pairs.append(("type", _text(types[0])))
    elif types:
        pairs.append(("type", _sequence([_text(t) for t in types], flow=True)))
    if "string" in types:
        if len(shape.formats) == 1 and "" not in shape.formats:
            pairs.append(("format", _text(next(iter(shape.formats)))))
        distinct = shape.distinct
        if (options.enum_max > 0 and types == ["string"] and distinct is not None
                and 0 < len(distinct) <= options.enum_max and shape.strings > len(distinct)):
            pairs.append(("enum", _sequence([_text(v) for v in distinct])))
    if "object" in types:
        if shape.props:
            pairs.append(("properties", _mapping(
                [(name, _to_node(child, options)) for name, child in shape.props.items()])))
            required = [name for name in shape.props if shape.prop_counts[name] == shape.objects]
            if required:
                pairs.append(("required", _sequence([_text(n) for n in required])))
        if options.strict:
            pairs.append(("additionalProperties", Node(Kind.SCALAR, tag="!!bool", value="false")))
    if "array" in types and shape.items is not None:
        pairs.append(("items", _to_node(shape.items, options)))
    return _mapping(pairs)


# ----------------------------------------------------------------------------- the operator

@operator("SCHEMA")
def schema_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """Describe the nodes in the context as one JSON Schema (or one per node)."""
    options = nav.env.options.schema
    if not ctx.nodes:
        return ctx.child(())
    fix_merge = nav.env.options.yaml.fix_merge_anchor_to_spec
    groups = [[n] for n in ctx.nodes] if options.per_doc else [list(ctx.nodes)]
    results: list[Node] = []
    for group in groups:
        shape = _Shape()
        for node in group:
            if node_depth(node, MAX_DEPTH + 1) > MAX_DEPTH + 1:      # before copying: both recurse
                raise EvaluationLimitError(
                    f"schema: the data is nested more than {MAX_DEPTH} levels deep", limit="max_depth")
            probe = node.copy()                        # anchors and merge keys are expanded on a copy
            explode_node(probe, fix_merge=fix_merge, max_depth=MAX_DEPTH * 2)
            _observe(shape, probe, 0, nav)
        results.append(_to_node(shape, options, top=True))
    return ctx.child(results)
