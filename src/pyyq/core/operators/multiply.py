"""``*`` : numbers, string repeat and deep merge (Go's ``operator_multiply.go``)."""

from __future__ import annotations

from pyyq.core.engine.context import Context
from pyyq.core.engine.helpers import compound_assign, cross_function
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode, Operation, create_traversal_tree
from pyyq.core.lang.prefs import AssignPrefs, MultiplyPrefs, RecursiveDescentPrefs, TraversePrefs
from pyyq.core.model import tags
from pyyq.core.model.node import Kind, Node
from pyyq.core.operators.registry import operator
from pyyq.core.operators.traverse import recursive_descent
from pyyq.errors import EvaluationError

MAX_REPEAT_BYTES = 10 * 1024 * 1024


def _get_comments(lhs: Node, rhs: Node) -> tuple[str, str, str]:
    leading, head, foot = rhs.leading_content, rhs.head_comment, rhs.foot_comment
    if lhs.head_comment != "" or lhs.leading_content != "":
        head = lhs.head_comment
        leading = lhs.leading_content
    if lhs.foot_comment != "":
        foot = lhs.foot_comment
    return leading, head, foot


def multiply(prefs: MultiplyPrefs):
    def calc(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        assert lhs is not None and rhs is not None
        leading, head, foot = _get_comments(lhs, rhs)
        if rhs.tag == "!!null":
            return lhs.copy()
        if (
            (lhs.kind is Kind.MAPPING and rhs.kind is Kind.MAPPING)
            or (lhs.tag == "!!null" and rhs.kind is Kind.MAPPING)
            or (lhs.kind is Kind.SEQUENCE and rhs.kind is Kind.SEQUENCE)
            or (lhs.tag == "!!null" and rhs.kind is Kind.SEQUENCE)
        ):
            new_blank = lhs.copy()
            new_blank.leading_content = leading
            new_blank.head_comment = head
            new_blank.foot_comment = foot
            return merge_objects(nav, ctx.writable_clone(), new_blank, rhs, prefs)
        return multiply_scalars(lhs, rhs)

    return calc


def multiply_scalars(lhs: Node, rhs: Node) -> Node:
    lhs_tag = lhs.tag
    rhs_tag = rhs.guess_tag()
    lhs_is_custom = False
    if not lhs_tag.startswith("!!"):
        lhs_tag = lhs.guess_tag()
        lhs_is_custom = True
    if lhs_tag == "!!int" and rhs_tag == "!!int":
        target = lhs.copy_without_content()
        target.kind = Kind.SCALAR
        target.style = lhs.style
        target.tag = lhs.tag
        fmt, a = tags.parse_int(lhs.value)
        _, b = tags.parse_int(rhs.value)
        target.value = tags.format_int(fmt, a * b)
        return target
    if lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        target = lhs.copy_without_content()
        target.kind = Kind.SCALAR
        target.style = lhs.style
        target.tag = lhs.tag if lhs_is_custom else "!!float"
        target.value = tags.format_float(tags.parse_float(lhs.value) * tags.parse_float(rhs.value))
        return target
    if (lhs_tag == "!!str" and rhs_tag == "!!int") or (lhs_tag == "!!int" and rhs_tag == "!!str"):
        string_node, int_node = (lhs, rhs) if lhs.tag == "!!str" else (rhs, lhs)
        target = lhs.copy_without_content()
        target.update_attributes_from(string_node)
        count = tags.parse_int(int_node.value)[1]
        if count < 0:
            raise EvaluationError(f"cannot repeat string by a negative number ({count})")
        if count > 0 and len(string_node.value.encode()) > MAX_REPEAT_BYTES // count:
            raise EvaluationError(
                f"result of repeating string ({len(string_node.value)} bytes) by {count} "
                f"would exceed {MAX_REPEAT_BYTES} bytes")
        target.value = string_node.value * count
        return target
    raise EvaluationError(f"cannot multiply {lhs.tag} with {rhs.tag}")


def merge_objects(nav: Navigator, ctx: Context, lhs: Node, rhs: Node, prefs: MultiplyPrefs) -> Node:
    results: list[Node] = []
    rd_prefs = RecursiveDescentPrefs(
        recurse_array=prefs.deep_merge_arrays,
        traverse=TraversePrefs(dont_follow_alias=True, include_map_keys=True, exact_key_match=True),
    )
    recursive_descent(nav, results, ctx.single_child(rhs), rd_prefs)
    start = len(results[0].path()) if results else 0
    for candidate in results:
        _apply_assignment(nav, ctx, start, lhs, candidate, prefs)
    return lhs


def _apply_assignment(nav: Navigator, ctx: Context, start: int, lhs: Node, rhs: Node,
                      prefs: MultiplyPrefs) -> None:
    registry = nav.env.operators
    lhs_path = rhs.path()[start:]
    assignment = Operation(registry.get("ASSIGN_ATTRIBUTES"), prefs=prefs.assign)
    if prefs.append_arrays and rhs.kind is Kind.SEQUENCE:
        assignment = Operation(registry.get("ADD_ASSIGN"), prefs=prefs.assign)
    elif (not prefs.deep_merge_arrays and rhs.kind is Kind.SEQUENCE) or rhs.kind in (
        Kind.SCALAR, Kind.ALIAS
    ):
        assignment = Operation(registry.get("ASSIGN"), prefs=prefs.assign, update_assign=False)
    rhs_op = Operation(registry.get("REF"), node=rhs)
    tree = ExprNode(
        assignment,
        lhs=create_traversal_tree(lhs_path, prefs.traverse, rhs.is_map_key, registry),
        rhs=ExprNode(rhs_op),
    )
    nav.evaluate(ctx.single_child(lhs), tree)


def _prefs(expr: ExprNode) -> MultiplyPrefs:
    p = expr.operation.prefs
    return p if isinstance(p, MultiplyPrefs) else MultiplyPrefs(assign=AssignPrefs())


@operator("MULTIPLY")
def multiply_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx.readonly_clone(), expr, multiply(_prefs(expr)), False)


@operator("MULTIPLY_ASSIGN")
def multiply_assign_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs

    def build(l: ExprNode, r: ExprNode | None) -> ExprNode:
        return ExprNode(Operation(nav.env.operators.get("MULTIPLY"), prefs=prefs), lhs=l, rhs=r)

    return compound_assign(nav, ctx, expr, build)
