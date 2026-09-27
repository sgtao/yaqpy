"""jq words new to yaqpy in v0.8.0 (0926-03 6-1 / 3 章).

Every operator here is judged **A** in the plan: today the word is a plain syntax error (or,
for a few, an already-implemented operator with no way to write it - ``empty``), so adding it
cannot change the result of any expression that already worked. Written from the plan's own
spec (input / output / error condition), not from jq's source, tests or manual (0926-03 4 章:
出所の方針) - jq's C source and ``builtin.jq`` were not opened while writing this module.
"""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator

# ----------------------------------------------------------------------------- type filters
# `.[] | numbers` etc.: keep only the values of one broad type. Shorter than
# `select(tag == "!!int" or tag == "!!float")` and what an AI writing jq-flavoured
# expressions reaches for first (0926-03 3-7).

_ITERABLE_KINDS = (Kind.SEQUENCE, Kind.MAPPING)


def _scalar_tag(node: Node) -> str:
    return node.tag if node.tag.startswith("!!") else node.guess_tag()


def _matches_type_filter(node: Node, predicate: str) -> bool:
    if predicate == "values":
        return _scalar_tag(node) != "!!null"
    if predicate == "nulls":
        return _scalar_tag(node) == "!!null"
    if predicate == "booleans":
        return _scalar_tag(node) == "!!bool"
    if predicate == "numbers":
        return _scalar_tag(node) in ("!!int", "!!float")
    if predicate == "strings":
        return _scalar_tag(node) == "!!str"
    if predicate == "arrays":
        return node.kind is Kind.SEQUENCE
    if predicate == "objects":
        return node.kind is Kind.MAPPING
    if predicate == "iterables":
        return node.kind in _ITERABLE_KINDS
    if predicate == "scalars":
        return node.kind not in _ITERABLE_KINDS
    raise AssertionError(f"unknown type filter {predicate!r}")     # pragma: no cover


@operator("TYPE_FILTER", num_args=0, precedence=50)
def type_filter_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    predicate = expr.operation.prefs
    assert isinstance(predicate, str)
    return ctx.child(n for n in ctx.nodes if _matches_type_filter(n, predicate))
