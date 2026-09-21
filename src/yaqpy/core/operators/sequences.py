"""Array operators: reverse, shuffle, first, filter, unique, group_by, flatten, pivot, ..."""

from __future__ import annotations

import random

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import truthy, yaml_string
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode, Operation
from yaqpy.core.lang.prefs import FlattenPrefs, TraversePrefs
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


# ----------------------------------------------------------------------------- unique / group_by

def _group_key(nav: Navigator, matched: Context, *, encode_containers: bool) -> str:
    if not matched.nodes:
        return "null"
    first = matched.nodes[0]
    if encode_containers and first.kind is not Kind.SCALAR:
        return yaml_string(nav, first)
    return first.value


def unique_by(nav: Navigator, ctx: Context, rhs: ExprNode | None) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        if candidate.kind is not Kind.SEQUENCE:
            raise EvaluationError("only arrays are supported for unique")
        first_seen: dict[str, Node] = {}
        for child in candidate.content:
            matched = nav.evaluate(ctx.single_readonly_child(child), rhs)
            first_seen.setdefault(_group_key(nav, matched, encode_containers=True), child)
        result = candidate.create_replacement_with_comments(Kind.SEQUENCE, "!!seq", candidate.style)
        result.add_children(first_seen.values())
        results.append(result)
    return ctx.child(results)


@operator("UNIQUE_BY")
def unique_by_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return unique_by(nav, ctx, expr.rhs)


@operator("UNIQUE")
def unique_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return unique_by(nav, ctx, ExprNode(Operation(nav.env.operators.get("SELF"))))


@operator("GROUP_BY")
def group_by_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        if candidate.kind is not Kind.SEQUENCE:
            raise EvaluationError("only arrays are supported for group by")
        groups: dict[str, list[Node]] = {}
        for child in candidate.content:
            matched = nav.evaluate(ctx.single_readonly_child(child), expr.rhs)
            groups.setdefault(_group_key(nav, matched, encode_containers=False), []).append(child)
        result = candidate.create_replacement(Kind.SEQUENCE, "!!seq", "")
        for members in groups.values():
            group = Node.sequence()
            group.add_children(members)
            result.add_child(group)
        results.append(result)
    return ctx.child(results)


# ----------------------------------------------------------------------------- flatten

def _flatten(node: Node, depth: int) -> None:
    if depth == 0 or node.kind is not Kind.SEQUENCE:
        return
    flat: list[Node] = []
    for child in node.content:
        if child.kind is Kind.SEQUENCE:
            _flatten(child, depth - 1)
            flat.extend(child.content)
        else:
            flat.append(child)
    node.content = []
    node.add_children(flat)


@operator("FLATTEN_BY")
def flatten_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    depth = prefs.depth if isinstance(prefs, FlattenPrefs) else -1
    for candidate in ctx.nodes:
        if candidate.kind is not Kind.SEQUENCE:
            raise EvaluationError("only arrays are supported for flatten")
        _flatten(candidate, depth)
    return ctx


# ----------------------------------------------------------------------------- pivot

def _untagged(node: Node) -> Node:
    """Go builds pivot's result without a tag (it prints as ``()``); keep that for compatibility."""
    node.tag = ""
    return node


def _padded(column: list[Node], length: int) -> list[Node]:
    return column + [Node.null(value="") for _ in range(length - len(column))]


def _pivot_sequences(seq: Node) -> Node:
    size = len(seq.content)
    if size == 0:
        return seq
    columns: dict[int, list[Node]] = {}
    for i, row in enumerate(seq.content):
        for j, cell in enumerate(row.content):
            column = _padded(columns.get(j, []), i)
            column.append(cell)
            columns[j] = column
    result = _untagged(Node.sequence())
    for j in range(len(columns)):
        pivoted = _untagged(Node.sequence())
        pivoted.add_children(_padded(columns[j], size))
        result.add_child(pivoted)
    return result


def _pivot_maps(seq: Node) -> Node:
    size = len(seq.content)
    result = _untagged(Node.mapping())
    if size == 0:
        return result
    columns: dict[str, list[Node]] = {}
    for i, row in enumerate(seq.content):
        for key, value in row.map_items():
            column = _padded(columns.get(key.value, []), i)
            column.append(value)
            columns[key.value] = column
    for name, column in columns.items():
        pivoted = _untagged(Node.sequence())
        pivoted.add_children(_padded(column, size))
        result.add_key_value(Node.string(name), pivoted)
    return result


def _unique_element_tag(seq: Node) -> str:
    if not seq.content:
        return ""
    first = seq.content[0].tag
    for child in seq.content[1:]:
        if child.tag != first:
            raise EvaluationError(f"sequence contains elements of {first} and {child.tag} types")
    return first


@operator("PIVOT")
def pivot_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        if candidate.tag != "!!seq":
            raise EvaluationError(f"cannot pivot node of type {candidate.tag}")
        tag = _unique_element_tag(candidate)
        if tag == "!!seq":
            results.append(_pivot_sequences(candidate))
        elif tag == "!!map":
            results.append(_pivot_maps(candidate))
        else:
            raise EvaluationError(
                f"can only pivot elements of !!seq or !!map types, received {tag}")
    return ctx.child(results)
