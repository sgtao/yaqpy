"""``prune_null`` and ``prune_empty``: tidy a converted document (yaqpy extensions).

A conversion that builds a new document from an old one leaves ``null`` behind for every
key the input did not have, and ``{}`` / ``[]`` for every group that ended up empty. An API
that reads the result would see ``"temperature": null`` or ``"generationConfig": {}``, which is
not the same as leaving the key out. These two operators remove them.

* ``prune_null`` removes every mapping entry whose value is ``null``. Sequence items are kept
  (removing them would move the positions of the others), so this is *not* the same as
  ``del(.. | select(. == null))``.
* ``prune_empty`` removes every mapping entry whose value is an empty mapping or an empty
  sequence, from the inside out: ``{a: {b: {}}}`` becomes ``{}`` (the root itself stays).

Both work on the whole subtree of what they are given, so aim them: ``.generationConfig |
prune_null`` tidies one part and leaves data such as a JSON Schema ``"default": null`` in
another part alone.
"""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator


def _prune(node: Node, *, nulls: bool, empties: bool) -> None:
    if node.kind is Kind.MAPPING:
        kept: list[Node] = []
        for key, value in node.map_items():
            _prune(value, nulls=nulls, empties=empties)
            if nulls and value.kind is Kind.SCALAR and value.is_null():
                continue
            if empties and value.kind in (Kind.MAPPING, Kind.SEQUENCE) and not value.content:
                continue
            kept.extend((key, value))
        node.content = kept
    elif node.kind is Kind.SEQUENCE:
        for item in node.content:
            _prune(item, nulls=nulls, empties=empties)


@operator("PRUNE_NULL")
def prune_null_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    for node in ctx.nodes:
        _prune(node, nulls=True, empties=False)
    return ctx


@operator("PRUNE_EMPTY")
def prune_empty_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    for node in ctx.nodes:
        _prune(node, nulls=False, empties=True)
    return ctx
