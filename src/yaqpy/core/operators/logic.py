"""Comparison and boolean operators: ``== != < <= > >= and or not select``."""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import (
    CrossPrefs, create_boolean, cross_function, cross_function_with_prefs, match_key, truthy,
)
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.lang.prefs import ComparePrefs
from yaqpy.core.model import tags
from yaqpy.core.model.datetime_util import parse_datetime
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator
from yaqpy.core.operators.traverse import splat
from yaqpy.core.lang.prefs import TraversePrefs
from yaqpy.errors import EvaluationError


def _is_equals(flip: bool):
    def calc(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        if lhs is None and rhs is None:
            return create_boolean(Node(), not flip)
        if lhs is None:
            assert rhs is not None
            value = rhs.tag == "!!null"
            return create_boolean(rhs, (not value) if flip else value)
        if rhs is None:
            value = lhs.tag == "!!null"
            return create_boolean(lhs, (not value) if flip else value)
        value = False
        if lhs.tag == "!!null":
            value = rhs.tag == "!!null"
        elif lhs.kind is Kind.SCALAR and rhs.kind is Kind.SCALAR:
            value = match_key(lhs.value, rhs.value)
        if flip:
            value = not value
        return create_boolean(lhs, value)

    return calc


@operator("EQUALS")
def equals_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx, expr, _is_equals(False), True)


@operator("NOT_EQUALS")
def not_equals_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx.readonly_clone(), expr, _is_equals(True), True)


def compare_scalars(prefs: ComparePrefs, lhs: Node, rhs: Node, layout: str = "2006-01-02T15:04:05Z07:00") -> bool:
    lhs_tag = lhs.guess_tag()
    rhs_tag = rhs.guess_tag()
    is_datetime = lhs.tag == "!!timestamp"
    if lhs_tag == "!!str":
        try:
            parse_datetime(layout, lhs.value)
            is_datetime = True
        except ValueError:
            is_datetime = False
    if is_datetime:
        try:
            a = parse_datetime(layout, lhs.value)
            b = parse_datetime(layout, rhs.value)
        except ValueError as e:
            raise EvaluationError(str(e)) from None
    elif lhs_tag == "!!int" and rhs_tag == "!!int":
        a = tags.parse_int(lhs.value)[1]
        b = tags.parse_int(rhs.value)[1]
    elif lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        a = tags.parse_float(lhs.value)
        b = tags.parse_float(rhs.value)
    elif lhs_tag == "!!str" and rhs_tag == "!!str":
        a = lhs.value
        b = rhs.value
    elif lhs_tag == "!!null" and rhs_tag == "!!null" and prefs.or_equal:
        return True
    elif lhs_tag == "!!null" or rhs_tag == "!!null":
        return False
    else:
        raise EvaluationError(f"{lhs.tag} not yet supported for comparison")
    if prefs.or_equal and a == b:
        return True
    return a > b if prefs.greater else a < b


def compare(prefs: ComparePrefs):
    def calc(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        if lhs is None and rhs is None:
            return create_boolean(Node(), prefs.or_equal)
        if lhs is None:
            assert rhs is not None
            return create_boolean(rhs, False)
        if rhs is None:
            return create_boolean(lhs, False)
        if lhs.kind is Kind.MAPPING:
            raise EvaluationError("maps not yet supported for comparison")
        if lhs.kind is Kind.SEQUENCE:
            raise EvaluationError("arrays not yet supported for comparison")
        if rhs.kind is not Kind.SCALAR:
            raise EvaluationError(
                f"{rhs.tag} ({rhs.nice_path()}) cannot be subtracted from {lhs.tag}")
        target = lhs.copy_without_content()
        return create_boolean(target, compare_scalars(prefs, lhs, rhs, ctx.get_datetime_layout()))

    return calc


@operator("COMPARE")
def compare_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    assert isinstance(prefs, ComparePrefs)
    return cross_function(nav, ctx, expr, compare(prefs), True)


def _superlative(nav: Navigator, ctx: Context, prefs: ComparePrefs) -> Context:
    fn = compare(prefs)
    results: list[Node] = []
    for seq in ctx.nodes:
        splatted = splat(nav, ctx.single_child(seq), TraversePrefs())
        if not splatted.nodes:
            continue
        best = splatted.nodes[0]
        for candidate in splatted.nodes[1:]:
            cmp = fn(nav, ctx, candidate, best)
            if truthy(cmp):
                best = candidate
        results.append(best)
    return ctx.child(results)


@operator("MIN")
def min_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return _superlative(nav, ctx, ComparePrefs(greater=False))


@operator("MAX")
def max_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return _superlative(nav, ctx, ComparePrefs(greater=True))


# ----------------------------------------------------------------------------- booleans

def _owner(lhs: Node | None, rhs: Node | None) -> Node:
    if lhs is None and rhs is None:
        return Node()
    if lhs is None:
        assert rhs is not None
        return rhs
    return lhs


def _return_rhs_truthy(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    return create_boolean(_owner(lhs, rhs), truthy(rhs))


def _return_lhs_when(target: bool):
    def shortcut(lhs: Node | None) -> Node | None:
        if truthy(lhs) != target:
            return None
        return create_boolean(lhs if lhs is not None else Node(), target)

    return shortcut


@operator("OR")
def or_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = CrossPrefs(calc_when_empty=True, calculation=_return_rhs_truthy,
                       lhs_result_value=_return_lhs_when(True))
    return cross_function_with_prefs(nav, ctx.readonly_clone(), expr, prefs)


@operator("AND")
def and_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = CrossPrefs(calc_when_empty=True, calculation=_return_rhs_truthy,
                       lhs_result_value=_return_lhs_when(False))
    return cross_function_with_prefs(nav, ctx.readonly_clone(), expr, prefs)


@operator("NOT")
def not_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(create_boolean(n, not truthy(n)) for n in ctx.nodes)


def _find_boolean(want: bool, nav: Navigator, ctx: Context, expr: ExprNode | None,
                  sequence: Node) -> bool:
    for node in sequence.content:
        if expr is not None:
            rhs = nav.evaluate(ctx.single_readonly_child(node), expr)
            if not rhs.nodes:
                continue
            node = rhs.nodes[0]
        if truthy(node) == want:
            return True
    return False


@operator("ANY")
@operator("ANY_CONDITION")
def any_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"any only supports arrays, was {node.tag}")
        results.append(create_boolean(node, _find_boolean(True, nav, ctx, expr.rhs, node)))
    return ctx.child(results)


@operator("ALL")
@operator("ALL_CONDITION")
def all_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"all only supports arrays, was {node.tag}")
        results.append(create_boolean(node, not _find_boolean(False, nav, ctx, expr.rhs, node)))
    return ctx.child(results)


@operator("SELECT")
def select_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        rhs = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        if any(truthy(r) for r in rhs.nodes):
            results.append(node)
    return ctx.child(results)
