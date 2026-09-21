"""Operators that reshape or test a structure: pick, omit, sort_keys, with, reduce, contains."""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import create_boolean, cross_function
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model import tags
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError


# ----------------------------------------------------------------------------- pick / omit

def _indices(nav: Navigator, ctx: Context, expr: ExprNode) -> Node:
    """The first result of the argument, or an empty node (Go: ``&CandidateNode{}``)."""
    found = nav.evaluate(ctx, expr.rhs)
    return found.nodes[0] if found.nodes else Node(Kind.SCALAR)


def _pick_map(original: Node, indices: Node) -> Node:
    picked: list[Node] = []
    for wanted in indices.content:
        at = original.find_key_index(wanted)
        if at > -1:
            picked.extend((original.content[at].copy(), original.content[at + 1].copy()))
    result = original.copy_without_content()
    result.add_children(picked)
    return result


def _pick_sequence(original: Node, indices: Node) -> Node:
    picked: list[Node] = []
    for wanted in indices.content:
        try:
            at = tags.parse_int(wanted.value)[1]
        except ValueError:
            raise EvaluationError(f"cannot index array with {wanted.value}") from None
        if 0 <= at < len(original.content):
            picked.append(original.content[at].copy())
    result = original.copy_without_content()
    result.add_children(picked)
    return result


@operator("PICK")
def pick_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    indices = _indices(nav, ctx, expr)
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is Kind.MAPPING:
            replacement = _pick_map(node, indices)
        elif node.kind is Kind.SEQUENCE:
            replacement = _pick_sequence(node, indices)
        else:
            raise EvaluationError(
                f"cannot pick indices from type {node.tag} ({node.nice_path()})")
        replacement.leading_content = node.leading_content
        results.append(replacement)
    return ctx.child(results)


def _omit_map(original: Node, indices: Node) -> Node:
    kept: list[Node] = []
    for key, value in original.map_items():
        if indices.find_in_array(key) < 0:
            kept.extend((key.copy(), value.copy()))
    result = original.copy_without_content()
    result.add_children(kept)
    return result


def _omit_sequence(original: Node, indices: Node) -> Node:
    kept = [child.copy() for index, child in enumerate(original.content)
            if indices.find_in_array(Node.integer(index)) < 0]
    result = original.copy_without_content()
    result.add_children(kept)
    return result


@operator("OMIT")
def omit_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    indices = _indices(nav, ctx, expr)
    if not indices.content:
        return ctx
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is Kind.MAPPING:
            replacement = _omit_map(node, indices)
        elif node.kind is Kind.SEQUENCE:
            replacement = _omit_sequence(node, indices)
        else:
            return ctx                       # omitting from a scalar changes nothing
        replacement.leading_content = node.leading_content
        results.append(replacement)
    return ctx.child(results)


# ----------------------------------------------------------------------------- sort_keys

def _sort_keys(node: Node) -> None:
    pairs = sorted(node.map_items(), key=lambda pair: pair[0].value)
    node.content = [item for pair in pairs for item in pair]    # same children, new order


@operator("SORT_KEYS")
def sort_keys_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    for candidate in ctx.nodes:
        targets = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs)
        for node in targets.nodes:
            if node.kind is Kind.MAPPING:
                _sort_keys(node)
    return ctx


# ----------------------------------------------------------------------------- with

@operator("WITH")
def with_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    block = expr.rhs
    assert block is not None
    if block.operation.spec.type != "BLOCK":
        raise EvaluationError(
            f"with must be given a block (;), got {block.operation.spec.type} instead")
    targets = nav.evaluate(ctx, block.lhs)
    for candidate in targets.nodes:
        nav.evaluate(targets.single_child(candidate), block.rhs)
    return ctx


# ----------------------------------------------------------------------------- reduce

@operator("REDUCE")
def reduce_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    lhs, rhs = expr.lhs, expr.rhs
    assert lhs is not None and rhs is not None
    if lhs.operation.spec.type != "ASSIGN_VARIABLE":
        raise EvaluationError(
            f"reduce must be given a variables assignment, got {lhs.operation.spec.type} instead")
    if rhs.operation.spec.type != "BLOCK":
        raise EvaluationError(f"reduce must be given a block, got {rhs.operation.spec.type} instead")
    assert lhs.lhs is not None and lhs.rhs is not None
    items = nav.evaluate(ctx, lhs.lhs)
    name = lhs.rhs.operation.string_value
    accumulator = nav.evaluate(ctx, rhs.lhs)
    for item in items.nodes:
        accumulator = nav.evaluate(accumulator.with_variable(name, (item,)), rhs.rhs)
    return ctx.child(accumulator.nodes)


# ----------------------------------------------------------------------------- contains

def _contains_array_element(array: Node, item: Node) -> bool:
    return any(_contains(child, item) for child in array.content)


def _contains_array(lhs: Node, rhs: Node) -> bool:
    if rhs.kind is not Kind.SEQUENCE:
        return _contains_array_element(lhs, rhs)
    return all(_contains_array_element(lhs, item) for item in rhs.content)


def _contains_object(lhs: Node, rhs: Node) -> bool:
    if rhs.kind is not Kind.MAPPING:
        return False
    for key, value in rhs.map_items():
        at = lhs.find_key_index(key)
        if at < 0 or not _contains(lhs.content[at + 1], value):
            return False
    return True


def _contains(lhs: Node, rhs: Node) -> bool:
    if lhs.kind is Kind.MAPPING:
        return _contains_object(lhs, rhs)
    if lhs.kind is Kind.SEQUENCE:
        return _contains_array(lhs, rhs)
    if lhs.kind is Kind.SCALAR:
        if rhs.kind is not Kind.SCALAR or lhs.tag != rhs.tag:
            return False
        if lhs.tag == "!!null":
            return rhs.tag == "!!null"
        if lhs.tag == "!!str":
            return rhs.value in lhs.value
        return lhs.value == rhs.value
    raise EvaluationError(f"{lhs.tag} not yet supported for contains")


@operator("CONTAINS")
def contains_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    def calculate(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        assert lhs is not None and rhs is not None
        if lhs.kind is not rhs.kind:
            raise EvaluationError(f"{rhs.tag} cannot check contained in {lhs.tag}")
        return create_boolean(lhs, _contains(lhs, rhs))

    return cross_function(nav, ctx.readonly_clone(), expr, calculate, False)
