"""``+ - / % //`` and their compound-assign forms."""

from __future__ import annotations

from pyyq.core.engine.context import Context
from pyyq.core.engine.helpers import CrossPrefs, compound_assign, cross_function, cross_function_with_prefs, truthy
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode, Operation
from pyyq.core.model import tags
from pyyq.core.model.datetime_util import format_datetime, looks_like_datetime, parse_datetime, parse_go_duration
from pyyq.core.model.node import Kind, Node, Style
from pyyq.core.operators.registry import operator
from pyyq.errors import EvaluationError


# ----------------------------------------------------------------------------- add

def _to_nodes(candidate: Node, lhs: Node) -> list[Node]:
    if candidate.tag == "!!null":
        return []
    clone = candidate.copy()
    if candidate.kind is Kind.SEQUENCE:
        return clone.content
    if lhs.content:
        clone.style = lhs.content[0].style
    return [clone]


def add(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    if lhs is None and rhs is None:
        return None
    if lhs is None:
        assert rhs is not None
        return rhs.copy()
    if rhs is None:
        return lhs.copy()
    if lhs.tag == "!!null":
        return lhs.copy_as_replacement(rhs)
    target = lhs.copy_without_content()
    if lhs.kind is Kind.MAPPING:
        if rhs.kind is not Kind.MAPPING:
            raise EvaluationError(
                f"{rhs.tag} ({rhs.nice_path()}) cannot be added to a {lhs.tag} ({lhs.nice_path()})")
        _add_maps(target, lhs, rhs)
    elif lhs.kind is Kind.SEQUENCE:
        _add_sequences(target, lhs, rhs)
    elif lhs.kind is Kind.SCALAR:
        if rhs.kind is not Kind.SCALAR:
            raise EvaluationError(
                f"{rhs.tag} ({rhs.nice_path()}) cannot be added to a {lhs.tag} ({lhs.nice_path()})")
        target.kind = Kind.SCALAR
        target.style = lhs.style
        _add_scalars(ctx, target, lhs, rhs)
    return target


def _shift_datetime(layout: str, value: str, duration: str, sign: int) -> str:
    try:
        delta = parse_go_duration(duration)
    except ValueError:
        raise EvaluationError(f"unable to parse duration [{duration}]") from None
    try:
        current = parse_datetime(layout, value)
    except ValueError as e:
        raise EvaluationError(str(e)) from None
    return format_datetime(current + delta * sign, layout)


def _add_scalars(ctx: Context, target: Node, lhs: Node, rhs: Node) -> None:
    lhs_tag = lhs.tag
    rhs_tag = rhs.guess_tag()
    lhs_is_custom = False
    if not lhs_tag.startswith("!!"):
        lhs_tag = lhs.guess_tag()
        lhs_is_custom = True
    if looks_like_datetime(lhs.tag, lhs.value, ctx.get_datetime_layout()):
        target.value = _shift_datetime(ctx.get_datetime_layout(), lhs.value, rhs.value, 1)
    elif lhs_tag == "!!str":
        target.tag = lhs.tag
        target.value = lhs.value if rhs_tag == "!!null" else lhs.value + rhs.value
    elif rhs_tag == "!!str":
        target.tag = rhs.tag
        target.value = lhs.value + rhs.value
    elif lhs_tag == "!!int" and rhs_tag == "!!int":
        fmt, a = tags.parse_int(lhs.value)
        _, b = tags.parse_int(rhs.value)
        target.tag = lhs.tag
        target.value = tags.format_int(fmt, a + b)
    elif lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        total = tags.parse_float(lhs.value) + tags.parse_float(rhs.value)
        target.tag = lhs.tag if lhs_is_custom else "!!float"
        target.value = tags.format_float(total)
    else:
        raise EvaluationError(f"{lhs_tag} cannot be added to {rhs_tag}")


def _add_sequences(target: Node, lhs: Node, rhs: Node) -> None:
    target.kind = Kind.SEQUENCE
    if not lhs.content:
        target.style = Style.NONE
    target.tag = lhs.tag
    extra = _to_nodes(rhs, lhs)
    target.add_children(lhs.content)
    target.add_children(extra)


def _add_maps(target: Node, lhs: Node, rhs: Node) -> None:
    if not lhs.content:
        target.style = Style.NONE
    target.content = []
    target.add_children(lhs.content)
    for key, value in rhs.map_items():
        index = target.find_key_index(key)
        if index < 0:
            target.add_key_value(key, value)
        else:
            old = target.content[index + 1]
            target.content[index + 1] = old.copy_as_replacement(value)
    target.kind = Kind.MAPPING
    if lhs.content:
        target.style = lhs.style
    target.tag = lhs.tag


@operator("ADD")
def add_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    calc_when_empty = len(ctx.nodes) > 0
    return cross_function(nav, ctx.readonly_clone(), expr, add, calc_when_empty)


def _create_add(lhs: ExprNode, rhs: ExprNode | None, nav: Navigator) -> ExprNode:
    return ExprNode(Operation(nav.env.operators.get("ADD")), lhs=lhs, rhs=rhs)


@operator("ADD_ASSIGN")
def add_assign_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return compound_assign(nav, ctx, expr, lambda l, r: _create_add(l, r, nav))


# ----------------------------------------------------------------------------- subtract

def subtract(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    assert lhs is not None and rhs is not None
    if lhs.tag == "!!null":
        return lhs.copy_as_replacement(rhs)
    target = lhs.copy_without_content()
    if lhs.kind is Kind.MAPPING:
        raise EvaluationError("maps not yet supported for subtraction")
    if lhs.kind is Kind.SEQUENCE:
        if rhs.kind is not Kind.SEQUENCE:
            raise EvaluationError(
                f"{rhs.tag} ({rhs.nice_path()}) cannot be subtracted from {lhs.tag}")
        target.content = []
        for child in lhs.content:
            if rhs.find_in_array(child) < 0:
                target.add_child(child)
        return target
    if rhs.kind is not Kind.SCALAR:
        raise EvaluationError(f"{rhs.tag} ({rhs.nice_path()}) cannot be subtracted from {lhs.tag}")
    target.kind = Kind.SCALAR
    target.style = lhs.style
    lhs_tag, rhs_tag = lhs.tag, rhs.tag
    lhs_is_custom = False
    if not lhs_tag.startswith("!!"):
        lhs_tag = lhs.guess_tag()
        lhs_is_custom = True
    if not rhs_tag.startswith("!!"):
        rhs_tag = rhs.guess_tag()
    if looks_like_datetime(lhs_tag, lhs.value, ctx.get_datetime_layout()):
        target.value = _shift_datetime(ctx.get_datetime_layout(), lhs.value, rhs.value, -1)
        return target
    if lhs_tag == "!!str":
        raise EvaluationError("strings cannot be subtracted")
    if lhs_tag == "!!int" and rhs_tag == "!!int":
        fmt, a = tags.parse_int(lhs.value)
        _, b = tags.parse_int(rhs.value)
        target.tag = lhs.tag
        target.value = tags.format_int(fmt, a - b)
    elif lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        target.tag = lhs.tag if lhs_is_custom else "!!float"
        target.value = tags.format_float(tags.parse_float(lhs.value) - tags.parse_float(rhs.value))
    else:
        raise EvaluationError(f"{lhs.tag} cannot be added to {rhs.tag}")
    return target


@operator("SUBTRACT")
def subtract_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx.readonly_clone(), expr, subtract, False)


@operator("SUBTRACT_ASSIGN")
def subtract_assign_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    def build(l: ExprNode, r: ExprNode | None) -> ExprNode:
        return ExprNode(Operation(nav.env.operators.get("SUBTRACT")), lhs=l, rhs=r)

    return compound_assign(nav, ctx, expr, build)


# ----------------------------------------------------------------------------- divide / modulo

def _split_string(lhs: str, sep: str) -> list[Node]:
    if lhs == "":
        return []
    return [Node.string(part) for part in lhs.split(sep)]


def divide(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    assert lhs is not None and rhs is not None
    if lhs.tag == "!!null" or lhs.kind is not Kind.SCALAR or rhs.kind is not Kind.SCALAR:
        raise EvaluationError(
            f"{lhs.tag} ({lhs.nice_path()}) cannot be divided by {rhs.tag} ({rhs.nice_path()})")
    target = lhs.copy_without_content()
    lhs_tag = lhs.tag
    rhs_tag = rhs.guess_tag()
    lhs_is_custom = False
    if not lhs_tag.startswith("!!"):
        lhs_tag = lhs.guess_tag()
        lhs_is_custom = True
    if lhs_tag == "!!str" and rhs_tag == "!!str":
        target.kind = Kind.SEQUENCE
        target.tag = "!!seq"
        target.add_children(_split_string(lhs.value, rhs.value))
    elif lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        target.kind = Kind.SCALAR
        target.style = lhs.style
        a = tags.parse_float(lhs.value)
        b = tags.parse_float(rhs.value)
        if b == 0:
            quotient = float("inf") if a > 0 else float("-inf") if a < 0 else float("nan")
        else:
            quotient = a / b
        target.tag = lhs.tag if lhs_is_custom else "!!float"
        target.value = tags.format_float(quotient)
    else:
        raise EvaluationError(f"{lhs_tag} cannot be divided by {rhs_tag}")
    return target


@operator("DIVIDE")
def divide_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx.readonly_clone(), expr, divide, False)


def modulo(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    assert lhs is not None and rhs is not None
    if lhs.tag == "!!null" or lhs.kind is not Kind.SCALAR or rhs.kind is not Kind.SCALAR:
        raise EvaluationError(
            f"{lhs.tag} ({lhs.nice_path()}) cannot modulo by {rhs.tag} ({rhs.nice_path()})")
    target = lhs.copy_without_content()
    lhs_tag = lhs.tag
    rhs_tag = rhs.guess_tag()
    lhs_is_custom = False
    if not lhs_tag.startswith("!!"):
        lhs_tag = lhs.guess_tag()
        lhs_is_custom = True
    if lhs_tag == "!!int" and rhs_tag == "!!int":
        target.kind = Kind.SCALAR
        target.style = lhs.style
        fmt, a = tags.parse_int(lhs.value)
        _, b = tags.parse_int(rhs.value)
        if b == 0:
            raise EvaluationError("cannot modulo by 0")
        # Go's % truncates toward zero
        remainder = a - b * int(a / b) if (a < 0) != (b < 0) else a % b
        target.tag = lhs.tag
        target.value = tags.format_int(fmt, remainder)
    elif lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        import math

        target.kind = Kind.SCALAR
        target.style = lhs.style
        a = tags.parse_float(lhs.value)
        b = tags.parse_float(rhs.value)
        remainder = math.fmod(a, b) if b != 0 else float("nan")
        target.tag = lhs.tag if lhs_is_custom else "!!float"
        target.value = tags.format_float(remainder)
    else:
        raise EvaluationError(f"{lhs_tag} cannot modulo by {rhs_tag}")
    return target


@operator("MODULO")
def modulo_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return cross_function(nav, ctx.readonly_clone(), expr, modulo, False)


# ----------------------------------------------------------------------------- alternative

def _alternative(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
    if lhs is None:
        return rhs
    if rhs is None:
        return lhs
    return lhs if truthy(lhs) else rhs


def _lhs_truthy(lhs: Node | None) -> Node | None:
    if lhs is not None and truthy(lhs):
        return lhs
    return None


@operator("ALTERNATIVE")
def alternative_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = CrossPrefs(calc_when_empty=True, calculation=_alternative, lhs_result_value=_lhs_truthy)
    return cross_function_with_prefs(nav, ctx, expr, prefs)
