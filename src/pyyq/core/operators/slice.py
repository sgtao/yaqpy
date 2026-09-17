"""Array slicing ``.[1:3]`` (Go's ``operator_slice.go``)."""

from __future__ import annotations

from pyyq.core.engine.context import Context
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode
from pyyq.core.model import tags
from pyyq.core.model.node import Kind, Node
from pyyq.errors import EvaluationError


def _index(nav: Navigator, ctx: Context, node: Node, expr: ExprNode | None, default: int) -> int:
    result = nav.evaluate(ctx.single_readonly_child(node), expr)
    if not result.nodes:
        return default
    first = result.nodes[0]
    if first.tag != "!!int":
        raise EvaluationError(f"slice indices must be integers, got {first.tag}")
    return tags.parse_int(first.value)[1]


def slice_array_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        node = node.resolve_alias()
        first = _index(nav, ctx, node, expr.lhs, 0)
        length = len(node.content) if node.kind is Kind.SEQUENCE else len(node.value)
        second = _index(nav, ctx, node, expr.rhs, length)
        if first < 0:
            first = max(length + first, 0)
        if second < 0:
            second = max(length + second, 0)
        first = min(first, length)
        second = min(second, length)
        if node.kind is Kind.SEQUENCE:
            out = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
            for child in node.content[first:second]:
                out.add_child(child)
            results.append(out)
        elif node.kind is Kind.SCALAR and node.guess_tag() == "!!str":
            results.append(node.create_replacement(Kind.SCALAR, "!!str", node.value[first:second]))
        else:
            raise EvaluationError(f"cannot slice {node.tag}")
    return ctx.child(results)
