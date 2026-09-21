"""Array operators: reverse, shuffle, first, filter (Go's ``operator_reverse.go`` and friends)."""

from __future__ import annotations

import random

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import truthy
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode, Operation
from yaqpy.core.lang.prefs import TraversePrefs
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.collections import collect_together
from yaqpy.core.operators.logic import select_operator
from yaqpy.core.operators.registry import operator
from yaqpy.core.operators.traverse import splat
from yaqpy.errors import EvaluationError


def _require_sequence(node: Node) -> None:
    if node.kind is not Kind.SEQUENCE:
        raise EvaluationError(
            f"node at path [{node.nice_path()}] is not an array (it's a {node.tag})")


# ----------------------------------------------------------------------------- reverse

@operator("REVERSE")
def reverse_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        _require_sequence(node)
        reversed_seq = node.create_replacement_with_comments(Kind.SEQUENCE, "!!seq", node.style)
        reversed_seq.add_children(reversed(node.content))
        results.append(reversed_seq)
    return ctx.child(results)


# ----------------------------------------------------------------------------- shuffle

@operator("SHUFFLE")
def shuffle_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    rng = random.Random(int(nav.env.clock().timestamp() * 1_000_000_000))
    results: list[Node] = []
    for node in ctx.nodes:
        _require_sequence(node)
        result = node.copy()
        rng.shuffle(result.content)
        for index, child in enumerate(result.content):      # keep the keys 0..n-1 in order
            assert child.key is not None
            child.key.value = str(index)
        results.append(result)
    return ctx.child(results)


# ----------------------------------------------------------------------------- first

@operator("FIRST")
def first_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        if expr.rhs is None:                 # no condition: the first child
            if candidate.content:
                results.append(candidate.content[0])
            continue
        splatted = splat(nav, ctx.single_child(candidate), TraversePrefs())
        for child in splatted.nodes:
            matched = nav.evaluate(splatted.single_child(child), expr.rhs)
            if any(truthy(n) for n in matched.nodes):
                results.append(child)
                break
    return ctx.child(results)


# ----------------------------------------------------------------------------- filter

@operator("FILTER")
def filter_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    self_exp = ExprNode(Operation(nav.env.operators.get("SELF")))
    for candidate in ctx.nodes:
        splatted = splat(nav, ctx.single_child(candidate), TraversePrefs())
        filtered = select_operator(nav, splatted, expr)
        collected = collect_together(nav, filtered, self_exp)
        collected.style = candidate.style
        results.append(collected)
    return ctx.child(results)
