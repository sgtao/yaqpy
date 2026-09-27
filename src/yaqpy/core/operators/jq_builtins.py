"""jq words new to yaqpy in v0.8.0 (0926-03 6-1 / 3 章).

Every operator here is judged **A** in the plan: today the word is a plain syntax error (or,
for a few, an already-implemented operator with no way to write it - ``empty``), so adding it
cannot change the result of any expression that already worked. Written from the plan's own
spec (input / output / error condition), not from jq's source, tests or manual (0926-03 4 章:
出所の方針) - jq's C source and ``builtin.jq`` were not opened while writing this module.
"""

from __future__ import annotations

import re

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import create_boolean
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model import tags
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.regex import RegexError, compile_go, find_all
from yaqpy.core.operators.registry import operator
from yaqpy.core.operators.strings import _GO_SPACE
from yaqpy.errors import EvaluationError

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


# ----------------------------------------------------------------------------- strings (3-8)

def _first_string(nav: Navigator, ctx: Context, expr: ExprNode | None) -> str:
    result = nav.evaluate(ctx.readonly_clone(), expr)
    return result.nodes[0].value if result.nodes else ""


def _require_string(node: Node, message: str) -> None:
    if node.guess_tag() != "!!str":
        raise EvaluationError(message.format(node.tag))


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return compile_go(pattern)
    except RegexError as e:
        raise EvaluationError(str(e)) from None


@operator("STARTSWITH", num_args=1, precedence=50)
def startswith_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefix = _first_string(nav, ctx, expr.rhs)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "{} cannot be matched, as it is not a string")
        results.append(create_boolean(node, node.value.startswith(prefix)))
    return ctx.child(results)


@operator("ENDSWITH", num_args=1, precedence=50)
def endswith_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    suffix = _first_string(nav, ctx, expr.rhs)
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "{} cannot be matched, as it is not a string")
        results.append(create_boolean(node, node.value.endswith(suffix)))
    return ctx.child(results)


@operator("LTRIMSTR", num_args=1, precedence=50)
def ltrimstr_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefix_ctx = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    prefix = prefix_ctx.nodes[0] if prefix_ctx.nodes else None
    results: list[Node] = []
    for node in ctx.nodes:
        if node.guess_tag() != "!!str" or prefix is None or prefix.guess_tag() != "!!str":
            results.append(node)
        elif node.value.startswith(prefix.value):
            results.append(node.create_replacement(Kind.SCALAR, node.tag, node.value[len(prefix.value):]))
        else:
            results.append(node)
    return ctx.child(results)


@operator("RTRIMSTR", num_args=1, precedence=50)
def rtrimstr_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    suffix_ctx = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    suffix = suffix_ctx.nodes[0] if suffix_ctx.nodes else None
    results: list[Node] = []
    for node in ctx.nodes:
        if node.guess_tag() != "!!str" or suffix is None or suffix.guess_tag() != "!!str":
            results.append(node)
        elif suffix.value and node.value.endswith(suffix.value):
            results.append(node.create_replacement(Kind.SCALAR, node.tag, node.value[:-len(suffix.value)]))
        else:
            results.append(node)
    return ctx.child(results)


@operator("LTRIM", num_args=0, precedence=50)
def ltrim_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot trim {}, can only operate on strings. ")
        results.append(node.create_replacement(Kind.SCALAR, node.tag, node.value.lstrip(_GO_SPACE)))
    return ctx.child(results)


@operator("RTRIM", num_args=0, precedence=50)
def rtrim_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot trim {}, can only operate on strings. ")
        results.append(node.create_replacement(Kind.SCALAR, node.tag, node.value.rstrip(_GO_SPACE)))
    return ctx.child(results)


def _split_by_regex(regex: re.Pattern[str], text: str) -> list[str]:
    pieces: list[str] = []
    last = 0
    for match in find_all(regex, text):
        pieces.append(text[last:match.start()])
        last = match.end()
    pieces.append(text[last:])
    return pieces


@operator("SPLITS", num_args=1, precedence=50)
def splits_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's ``splits(re)``: a stream of the pieces (``split(re; flags)``'s array form is the
    existing 2-arg ``split``, and fixing its known bug is deferred - 決定 9, 1-3 の 9)."""
    regex = _compile(_first_string(nav, ctx, expr.rhs))
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot split {}, can only split strings")
        for piece in _split_by_regex(regex, node.value):
            results.append(node.create_replacement(Kind.SCALAR, "!!str", piece))
    return ctx.child(results)


def _scan_result(node: Node, regex: re.Pattern[str], match: re.Match[str]) -> Node:
    if regex.groups == 0:
        return node.create_replacement(Kind.SCALAR, "!!str", match.group(0))
    seq = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
    seq.add_children(Node.null() if match.group(i) is None else Node.string(match.group(i))
                     for i in range(1, regex.groups + 1))
    return seq


@operator("SCAN", num_args=1, precedence=50)
def scan_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    regex = _compile(_first_string(nav, ctx, expr.rhs))
    results: list[Node] = []
    for node in ctx.nodes:
        _require_string(node, "cannot scan {}, can only scan strings")
        for match in find_all(regex, node.value):
            results.append(_scan_result(node, regex, match))
    return ctx.child(results)


def _codepoint(node: Node) -> int:
    if node.guess_tag() != "!!int":
        raise ValueError(node.tag)
    return tags.parse_int(node.value)[1]


@operator("IMPLODE", num_args=0, precedence=52, check_for_post_traverse=True)
def implode_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """The inverse of jq's ``explode`` (an array of codepoints -> a string). yq's ``explode``
    is unrelated (anchor expansion), so only ``implode`` is added here - 決定 8, 1-3 の 9."""
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"implode input must be an array, got {node.tag}")
        try:
            text = "".join(chr(_codepoint(child)) for child in node.content)
        except (ValueError, OverflowError):
            raise EvaluationError("implode input must be an array of codepoints") from None
        results.append(node.create_replacement(Kind.SCALAR, "!!str", text))
    return ctx.child(results)
