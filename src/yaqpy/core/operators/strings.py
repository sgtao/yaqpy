"""String operators: join, split, sub, match, capture, test, trim, case, to_string, to_number,
and string interpolation (Go's ``operator_strings.go`` / ``operator_to_number.go``)."""

from __future__ import annotations

import re

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import create_boolean, yaml_string
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.core.operators.basic import value_operator
from yaqpy.core.operators.regex import (
    RegexError, byte_length, byte_offset, compile_go, find_all, replace_all,
)
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError

# Go's unicode.IsSpace: what strings.TrimSpace removes.
_GO_SPACE = "".join(map(chr, (
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B),
    0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
)))
_MATCH_DOCS = "https://mikefarah.gitbook.io/yq/operators/string-operators"


def _first_value(context: Context) -> str:
    return context.nodes[0].value if context.nodes else ""


def _require_string(node: Node, message: str) -> None:
    if node.guess_tag() != "!!str":
        raise EvaluationError(message.format(node.tag))


# ----------------------------------------------------------------------------- interpolation

def _evaluate_text(nav: Navigator, ctx: Context, expression: str) -> str:
    from yaqpy.core.lang.parser import parse_expression

    result = nav.evaluate(ctx, parse_expression(expression, nav.env.operators.get))
    if not result.nodes:
        return ""
    node = result.nodes[0]
    return node.value if node.kind is Kind.SCALAR else yaml_string(nav, node)


def interpolate(nav: Navigator, ctx: Context, text: str) -> str:
    """Replace ``\\(expression)`` in ``text`` by the value of the expression."""
    out: list[str] = []
    expression: list[str] = []
    in_expression = False
    depth = 0
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if not in_expression:
            if ch == "\\" and i < n - 1:
                following = text[i + 1]
                if following == "(":
                    in_expression = True
                    i += 2                      # skip the backslash and the parenthesis
                    continue
                if following == "\\":
                    i += 1                      # an escaped backslash: keep one
            out.append(text[i])
        else:
            if ch == ")":
                if depth == 0:
                    out.append(_evaluate_text(nav, ctx, "".join(expression)))
                    expression = []
                    in_expression = False
                    i += 1
                    continue
                depth -= 1
            elif ch == "(":
                depth += 1
            elif ch == "\\" and i < n - 1 and text[i + 1] in ")\\":
                expression.append(text[i + 1])  # an escaped ) or backslash inside the expression
                i += 2
                continue
            expression.append(ch)
        i += 1
    if in_expression:                           # unclosed: leave the string as it was
        return text
    return "".join(out)


@operator("STRING_INT")
def string_interpolation_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    literal = expr.operation.string_value
    if "\\" not in literal or not nav.env.options.string_interpolation:
        return value_operator(nav, ctx, expr)
    if not ctx.nodes:
        value = interpolate(nav, ctx, literal)
        return ctx.single_child(Node.string(value))
    results = [Node.string(interpolate(nav, ctx.single_child(candidate), literal))
               for candidate in ctx.nodes]
    return ctx.child(results)


# ----------------------------------------------------------------------------- trim / case / to_string

@operator("TRIM")
def trim_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot trim {}, can only operate on strings. ")
        trimmed = node.create_replacement(Kind.SCALAR, node.tag, node.value.strip(_GO_SPACE))
        trimmed.style = node.style
        results.append(trimmed)
    return ctx.child(results)


def _simple_case(text: str, upper: bool) -> str:
    """Go maps case rune by rune (simple case mapping); Python's whole-string mapping can
    expand one character into several (``ß`` to ``SS``), so map each character on its own."""
    out: list[str] = []
    for ch in text:
        mapped = ch.upper() if upper else ch.lower()
        out.append(mapped if len(mapped) == 1 else ch)
    return "".join(out)


@operator("CHANGE_CASE")
def change_case_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    to_upper = bool(expr.operation.prefs)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot change case with {}, can only operate on strings. ")
        changed = node.create_replacement(Kind.SCALAR, node.tag, _simple_case(node.value, to_upper))
        changed.style = node.style
        results.append(changed)
    return ctx.child(results)


@operator("TO_STRING")
def to_string_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.tag == "!!str":
            text, style = node.value, Style.NONE
        elif node.kind is Kind.SCALAR:
            text, style = node.value, Style.DOUBLE_QUOTED
        else:
            text, style = yaml_string(nav, node), Style.DOUBLE_QUOTED
        converted = node.create_replacement(Kind.SCALAR, "!!str", text)
        converted.style = style
        converted.tag = "!!str"
        results.append(converted)
    return ctx.child(results)


# ----------------------------------------------------------------------------- to_number

_INT64_MIN, _INT64_MAX = -(1 << 63), (1 << 63) - 1
_INTEGER = re.compile(r"([+-]?)(?:0[xX]([0-9a-fA-F]+)|0o([0-7]+)|([0-9]+))\Z")
_DECIMAL_FLOAT = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_SPECIAL_FLOAT = re.compile(r"(?:[+-]?(?:inf|infinity)|nan)\Z", re.IGNORECASE)


def _parse_int64(value: str) -> int | None:
    """Go's ``parseInt64``: underscores are dropped; ``0x`` / ``0o`` prefixes; int64 range."""
    found = _INTEGER.match(value.replace("_", ""))
    if found is None:
        return None
    sign, hex_digits, octal_digits, decimal_digits = found.groups()
    if hex_digits is not None:
        number = int(hex_digits, 16)
    elif octal_digits is not None:
        number = int(octal_digits, 8)
    else:
        number = int(decimal_digits, 10)
    number = -number if sign == "-" else number
    return number if _INT64_MIN <= number <= _INT64_MAX else None


def _number_tag(value: str) -> str | None:
    """``!!int`` or ``!!float`` when Go's ``ParseInt`` / ``ParseFloat`` would accept the text."""
    if _parse_int64(value) is not None:
        return "!!int"
    if _DECIMAL_FLOAT.match(value) or _SPECIAL_FLOAT.match(value):
        return "!!float"
    return None


@operator("TO_NUMBER")
def to_number_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SCALAR:
            raise EvaluationError(
                f"cannot convert node at path {node.nice_path()} of tag {node.tag} to number")
        if node.tag in ("!!int", "!!float"):
            results.append(node)
            continue
        tag = _number_tag(node.value)
        if tag is None:
            raise EvaluationError(
                f"cannot convert node value [{node.value}] at path {node.nice_path()} "
                f"of tag {node.tag} to number")
        results.append(node.create_replacement(Kind.SCALAR, tag, node.value))
    return ctx.child(results)


# ----------------------------------------------------------------------------- join / split

@operator("JOIN")
def join_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    separator = _first_value(nav.evaluate(ctx.readonly_clone(), expr.rhs))
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"cannot join with {node.tag}, can only join arrays of scalars")
        parts = ["" if child.tag == "!!null" else child.value for child in node.content]
        results.append(node.create_replacement(Kind.SCALAR, "!!str", separator.join(parts)))
    return ctx.child(results)


@operator("SPLIT")
def split_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    separator = _first_value(nav.evaluate(ctx.readonly_clone(), expr.rhs))
    results: list[Node] = []
    for node in ctx.nodes:
        if node.tag == "!!null":
            continue
        _require_string(node, "cannot split {}, can only split strings")
        pieces: list[str] = []
        if node.value != "":
            pieces = list(node.value) if separator == "" else node.value.split(separator)
        result = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
        result.add_children(Node.string(piece) for piece in pieces)
        results.append(result)
    return ctx.child(results)


# ----------------------------------------------------------------------------- regular expressions

def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return compile_go(pattern)
    except RegexError as e:
        raise EvaluationError(str(e)) from None


def _extract_match_arguments(nav: Navigator, ctx: Context, expr: ExprNode) -> tuple[re.Pattern[str], bool]:
    """The compiled pattern and whether ``"g"`` (all matches) was asked for."""
    pattern_exp = expr.rhs
    is_global = False
    assert expr.rhs is not None
    if expr.rhs.operation.spec.type == "BLOCK":     # match(regex; params)
        pattern_exp = expr.rhs.lhs
        params = _first_value(nav.evaluate(ctx, expr.rhs.rhs))
        if "g" in params:
            params = params.replace("g", "")
            is_global = True
        if "i" in params:
            raise EvaluationError("'i' is not a valid option for match. "
                                  'To ignore case, use an expression like match("(?i)cat")')
        if params:
            raise EvaluationError(
                f"unrecognised match params '{params}', please see docs at {_MATCH_DOCS}")
    pattern = _first_value(nav.evaluate(ctx.readonly_clone(), pattern_exp))
    return _compile(pattern), is_global


def _matches(regex: re.Pattern[str], text: str, is_global: bool) -> list[re.Match[str]]:
    if is_global:
        return list(find_all(regex, text))
    found = regex.search(text)
    return [] if found is None else [found]


_NOT_A_STRING = ("cannot match with {}, can only match strings. "
                 "Hint: Most often you'll want to use '|=' over '=' for this operation")
_HINT = "Hint: Most often you'll want to use '|=' over '=' for this operation"


def _group_names(regex: re.Pattern[str]) -> dict[int, str]:
    return {index: name for name, index in regex.groupindex.items()}


def _match_pairs(text: str, offset: int, name: str) -> list[Node]:
    """Go's ``addMatch``: the key/value pairs ``string`` ``offset`` ``length`` [``name``]."""
    pairs = [
        Node.string("string"), Node.null() if offset < 0 else Node.string(text),
        Node.string("offset"), Node.integer(offset),
        Node.string("length"), Node.integer(byte_length(text)),
    ]
    if name:
        pairs += [Node.string("name"), Node.string(name)]
    return pairs


@operator("MATCH")
def match_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    regex, is_global = _extract_match_arguments(nav, ctx, expr)
    names = _group_names(regex)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, _NOT_A_STRING)
        text = node.value
        for found in _matches(regex, text, is_global):
            captures = Node.sequence()
            for group in range(1, regex.groups + 1):
                start = found.start(group)
                capture = Node.mapping()
                capture.add_children(_match_pairs(
                    found.group(group) or "",
                    -1 if start < 0 else byte_offset(text, start), names.get(group, "")))
                captures.add_child(capture)
            result = node.create_replacement(Kind.MAPPING, "!!map", "")
            result.add_children(_match_pairs(found.group(0), byte_offset(text, found.start()), ""))
            result.add_key_value(Node.string("captures"), captures)
            results.append(result)
    return ctx.child(results)


@operator("CAPTURE")
def capture_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    regex, is_global = _extract_match_arguments(nav, ctx, expr)
    names = _group_names(regex)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, _NOT_A_STRING)
        for found in _matches(regex, node.value, is_global):
            result = node.create_replacement(Kind.MAPPING, "!!map", "")
            for group in range(1, regex.groups + 1):
                captured = found.group(group)
                result.add_key_value(Node.string(names.get(group, "")),
                                     Node.null() if captured is None else Node.string(captured))
            results.append(result)
    return ctx.child(results)


@operator("TEST")
def test_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    regex, _ = _extract_match_arguments(nav, ctx, expr)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, _NOT_A_STRING)
        results.append(create_boolean(node, regex.search(node.value) is not None))
    return ctx.child(results)


@operator("SUBSTR")
def substitute_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    block = expr.rhs
    assert block is not None
    pattern = _first_value(nav.evaluate(ctx.readonly_clone(), block.lhs))
    replacement = _first_value(nav.evaluate(ctx, block.rhs))
    regex = _compile(pattern)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot substitute with {}, can only substitute strings. " + _HINT)
        results.append(node.create_replacement(
            Kind.SCALAR, "!!str", replace_all(regex, node.value, replacement)))
    return ctx.child(results)
