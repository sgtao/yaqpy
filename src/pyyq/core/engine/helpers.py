"""Shared helpers for operators (Go's ``operators.go`` / ``matchKeyString.go``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyyq.core.engine.context import Context
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode, Operation
from pyyq.core.lang.prefs import AssignPrefs, MultiplyPrefs
from pyyq.core.model.node import Kind, Node

type Calculation = Callable[[Navigator, Context, Node | None, Node | None], Node | None]
type LhsShortcut = Callable[[Node | None], Node | None]


def truthy(node: Node | None) -> bool:
    return node is not None and node.is_truthy()


def create_boolean(owner: Node, value: bool) -> Node:
    node = owner.create_replacement(Kind.SCALAR, "!!bool", "true" if value else "false")
    if owner.is_map_key:
        node.is_map_key = False
        node.key = owner
    return node


def match_key(name: str, pattern: str) -> bool:
    """Glob match with ``*`` and ``?`` (Go's ``matchKey`` / ``deepMatch``)."""
    if pattern == "":
        return name == pattern
    if pattern == "*":
        return True
    px = nx = 0
    next_px = next_nx = 0
    while px < len(pattern) or nx < len(name):
        if px < len(pattern):
            c = pattern[px]
            if c == "*":
                next_px = px
                next_nx = nx + 1
                px += 1
                continue
            if c == "?":
                if nx < len(name):
                    px += 1
                    nx += 1
                    continue
            elif nx < len(name) and name[nx] == c:
                px += 1
                nx += 1
                continue
        if 0 < next_nx <= len(name):
            px = next_px
            nx = next_nx
            continue
        return False
    return True


@dataclass(slots=True)
class CrossPrefs:
    calc_when_empty: bool = False
    lhs_result_value: LhsShortcut | None = None
    calculation: Calculation | None = None


def _results_for_rhs(nav: Navigator, ctx: Context, lhs: Node | None, prefs: CrossPrefs,
                     rhs_exp: ExprNode | None, results: list[Node]) -> None:
    assert prefs.calculation is not None
    if prefs.lhs_result_value is not None:
        shortcut = prefs.lhs_result_value(lhs)
        if shortcut is not None:
            results.append(shortcut)
            return
    rhs = nav.evaluate(ctx, rhs_exp)
    if prefs.calc_when_empty and not rhs.nodes:
        result = prefs.calculation(nav, ctx, lhs, None)
        if result is not None:
            results.append(result)
        return
    for rhs_node in rhs.nodes:
        result = prefs.calculation(nav, ctx, lhs, rhs_node)
        if result is not None:
            results.append(result)


def _do_cross(nav: Navigator, ctx: Context, expr: ExprNode, prefs: CrossPrefs) -> Context:
    results: list[Node] = []
    lhs = nav.evaluate(ctx, expr.lhs)
    if prefs.calc_when_empty and ctx.nodes and not lhs.nodes:
        _results_for_rhs(nav, ctx, None, prefs, expr.rhs, results)
    for lhs_node in lhs.nodes:
        _results_for_rhs(nav, ctx, lhs_node, prefs, expr.rhs, results)
    return ctx.child(results)


def cross_function_with_prefs(nav: Navigator, ctx: Context, expr: ExprNode,
                              prefs: CrossPrefs) -> Context:
    if ctx.evaluate_all_together():
        return _do_cross(nav, ctx, expr, prefs)
    results: list[Node] = []
    for node in ctx.nodes:
        inner = _do_cross(nav, ctx.single_child(node), expr, prefs)
        results.extend(inner.nodes)
    return ctx.child(results)


def cross_function(nav: Navigator, ctx: Context, expr: ExprNode, calc: Calculation,
                   calc_when_empty: bool = False) -> Context:
    return cross_function_with_prefs(
        nav, ctx, expr, CrossPrefs(calc_when_empty=calc_when_empty, calculation=calc))


def compound_assign(nav: Navigator, ctx: Context, expr: ExprNode,
                    build: Callable[[ExprNode, ExprNode | None], ExprNode]) -> Context:
    """Go's ``compoundAssignFunction``: ``a += b`` as ``a = a + b`` per lhs node."""
    lhs = nav.evaluate(ctx, expr.lhs)
    prefs = AssignPrefs()
    p = expr.operation.prefs
    if isinstance(p, AssignPrefs):
        prefs = p
    elif isinstance(p, MultiplyPrefs):
        prefs = AssignPrefs(clobber_custom_tags=p.assign.clobber_custom_tags)
    registry = nav.env.operators
    assignment = Operation(registry.get("ASSIGN"), prefs=prefs)
    for candidate in lhs.nodes:
        clone = candidate.copy()
        value_copy_exp = ExprNode(Operation(registry.get("REF"), node=clone))
        value_exp = ExprNode(Operation(registry.get("REF"), node=candidate))
        tree = ExprNode(assignment, lhs=value_exp, rhs=build(value_copy_exp, expr.rhs))
        nav.evaluate(ctx, tree)
    return ctx


def get_assign_prefs(preferences: object) -> AssignPrefs:
    if isinstance(preferences, AssignPrefs):
        return preferences
    if isinstance(preferences, MultiplyPrefs):
        return preferences.assign
    return AssignPrefs()
