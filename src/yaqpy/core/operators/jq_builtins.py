"""jq words new to yaqpy in v0.8.0 (0926-03 6-1 / 3 章).

Every operator here is judged **A** in the plan: today the word is a plain syntax error (or,
for a few, an already-implemented operator with no way to write it - ``empty``), so adding it
cannot change the result of any expression that already worked. Written from the plan's own
spec (input / output / error condition), not from jq's source, tests or manual (0926-03 4 章:
出所の方針) - jq's C source and ``builtin.jq`` were not opened while writing this module.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import create_boolean
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode, Operation
from yaqpy.core.model import tags
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.regex import RegexError, byte_length, compile_go, find_all
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


# ----------------------------------------------------------------------------- add / any(f) / all(f)

@operator("ADD_ALL", num_args=0, precedence=50)
def add_all_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's bare ``add`` (sum an array; ``add(f)`` is not added - low value, and it would need
    its own bare/call split like ``add``/``first`` already needed - 0926-03 3-7)."""
    from yaqpy.core.operators.arithmetic import add as add_values

    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"Cannot iterate over {node.tag} ({node.nice_path()})")
        total: Node | None = None
        for child in node.content:
            total = add_values(nav, ctx, total, child)
        results.append(total if total is not None else Node.null())
    return ctx.child(results)


# any(f)/all(f) need no new operator: they are the existing ANY_CONDITION/ALL_CONDITION
# (already reachable as `any_c(f)`/`all_c(f)`) under jq's own spelling - see the lexer rules.


# ----------------------------------------------------------------------------- min_by / max_by

def _key_of(nav: Navigator, ctx: Context, node: Node, key_expr: ExprNode | None) -> Node:
    result = nav.evaluate(ctx.single_readonly_child(node), key_expr)
    return result.nodes[0] if result.nodes else Node(tag="!!null")


def _min_max_by(nav: Navigator, ctx: Context, expr: ExprNode, greater: bool) -> Context:
    from yaqpy.core.lang.prefs import ComparePrefs
    from yaqpy.core.operators.logic import compare_scalars

    prefs = ComparePrefs(greater=greater)
    layout = ctx.get_datetime_layout()
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"{node.tag} cannot be iterated over for min_by/max_by")
        if not node.content:
            continue
        best = node.content[0]
        best_key = _key_of(nav, ctx, best, expr.rhs)
        for child in node.content[1:]:
            key = _key_of(nav, ctx, child, expr.rhs)
            if compare_scalars(prefs, key, best_key, layout):
                best, best_key = child, key
        results.append(best)
    return ctx.child(results)


@operator("MIN_BY", num_args=1, precedence=52, check_for_post_traverse=True)
def min_by_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return _min_max_by(nav, ctx, expr, greater=False)


@operator("MAX_BY", num_args=1, precedence=52, check_for_post_traverse=True)
def max_by_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return _min_max_by(nav, ctx, expr, greater=True)


# keys_unsorted needs no new operator: it is the existing KEYS (yq's `keys` is already
# unsorted - insertion order - so this is a pure alias; jq dialect will later make `keys`
# itself sort, at which point `keys_unsorted` keeps today's meaning - v0.9, 3-7).
# transpose needs no new operator either: it is `pivot` under jq's name (3-7).


# ----------------------------------------------------------------------------- utf8bytelength

@operator("UTF8BYTELENGTH", num_args=0, precedence=50)
def utf8bytelength_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.guess_tag() != "!!str":
            raise EvaluationError(f"{node.tag} only strings have UTF-8 byte length")
        results.append(node.create_replacement(Kind.SCALAR, "!!int", str(byte_length(node.value))))
    return ctx.child(results)


# ----------------------------------------------------------------------------- in / inside

@operator("IN", num_args=1, precedence=50)
def in_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's ``in(xs)``: is the current value present as a key in ``xs``? (the reverse of
    ``has``: ``$x | in(xs)`` is jq's ``xs | has($x)``.)"""
    from yaqpy.core.operators.collections import has_operator

    results: list[Node] = []
    for node in ctx.nodes:
        container_ctx = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        found = False
        for container in container_ctx.nodes:
            check = ExprNode(Operation(nav.env.operators.get("HAS")),
                            rhs=ExprNode(Operation(nav.env.operators.get("REF"), node=node)))
            result = has_operator(nav, ctx.single_readonly_child(container), check)
            if result.nodes and result.nodes[0].value == "true":
                found = True
                break
        results.append(create_boolean(node, found))
    return ctx.child(results)


@operator("INSIDE", num_args=1, precedence=50)
def inside_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's ``inside(xs)``: the reverse of ``contains``: ``$x | inside(xs)`` is
    ``xs | contains($x)``."""
    from yaqpy.core.operators.structure import contains_operator

    results: list[Node] = []
    for node in ctx.nodes:
        container_ctx = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        found = False
        for container in container_ctx.nodes:
            check = ExprNode(
                Operation(nav.env.operators.get("CONTAINS")),
                lhs=ExprNode(Operation(nav.env.operators.get("REF"), node=container)),
                rhs=ExprNode(Operation(nav.env.operators.get("REF"), node=node)),
            )
            result = contains_operator(nav, ctx.single_readonly_child(node), check)
            if result.nodes and result.nodes[0].value == "true":
                found = True
                break
        results.append(create_boolean(node, found))
    return ctx.child(results)


# ----------------------------------------------------------------------------- indices / index / rindex

def _scalar_equal(a: Node, b: Node) -> bool:
    at, bt = a.guess_tag(), b.guess_tag()
    if at in ("!!int", "!!float") and bt in ("!!int", "!!float"):
        return tags.parse_float(a.value) == tags.parse_float(b.value)
    return at == bt and a.value == b.value


def _nodes_equal(a: Node, b: Node) -> bool:
    if a.kind is not b.kind:
        return False
    if a.kind is Kind.SCALAR:
        return _scalar_equal(a, b)
    if a.kind is Kind.SEQUENCE:
        return (len(a.content) == len(b.content)
                and all(_nodes_equal(x, y) for x, y in zip(a.content, b.content)))
    if a.kind is Kind.MAPPING:
        if len(a.content) != len(b.content):
            return False
        by_key = {k.value: v for k, v in b.map_items()}
        return all(k.value in by_key and _nodes_equal(v, by_key[k.value]) for k, v in a.map_items())
    return False


def _string_indices(haystack: str, needle: str) -> list[int]:
    if needle == "":
        return []
    result: list[int] = []
    start = 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return result
        result.append(found)
        start = found + 1


def _array_indices(node: Node, needle: Node) -> list[int]:
    if needle.kind is Kind.SEQUENCE:
        n, m = len(node.content), len(needle.content)
        if m == 0:
            return []
        return [i for i in range(n - m + 1)
               if all(_nodes_equal(node.content[i + j], needle.content[j]) for j in range(m))]
    return [i for i, child in enumerate(node.content) if _nodes_equal(child, needle)]


def _compute_indices(node: Node, needle: Node) -> list[int]:
    if node.guess_tag() == "!!str":
        if needle.guess_tag() != "!!str":
            raise EvaluationError(f"Cannot index string with {needle.tag}")
        return _string_indices(node.value, needle.value)
    if node.kind is Kind.SEQUENCE:
        return _array_indices(node, needle)
    raise EvaluationError(f"{node.tag} cannot be searched for indices")


@operator("INDICES", num_args=1, precedence=50)
def indices_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        needle_ctx = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        needle = needle_ctx.nodes[0] if needle_ctx.nodes else Node(tag="!!null")
        seq = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
        seq.add_children(Node.integer(i) for i in _compute_indices(node, needle))
        results.append(seq)
    return ctx.child(results)


@operator("INDEX", num_args=1, precedence=50)
def index_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    found_ctx = indices_operator(nav, ctx, expr)
    return found_ctx.child(n.content[0] if n.content else Node.null() for n in found_ctx.nodes)


@operator("RINDEX", num_args=1, precedence=50)
def rindex_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    found_ctx = indices_operator(nav, ctx, expr)
    return found_ctx.child(n.content[-1] if n.content else Node.null() for n in found_ctx.nodes)


# ----------------------------------------------------------------------------- isempty(f)

@operator("ISEMPTY", num_args=1, precedence=50)
def isempty_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        result = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        results.append(create_boolean(node, not result.nodes))
    return ctx.child(results)


# ----------------------------------------------------------------------------- last / nth

@operator("LAST_BARE", num_args=0, precedence=52, check_for_post_traverse=True)
def last_bare_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(node.content[-1] for node in ctx.nodes if node.content)


@operator("LAST", num_args=1, precedence=52, check_for_post_traverse=True)
def last_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        stream = nav.evaluate(ctx.single_readonly_child(node), expr.rhs)
        if stream.nodes:
            results.append(stream.nodes[-1])
    return ctx.child(results)


def _int_arg(nav: Navigator, ctx: Context, node_expr: ExprNode | None) -> int:
    result = nav.evaluate(ctx.readonly_clone(), node_expr)
    if not result.nodes:
        raise EvaluationError("expected a number argument")
    return tags.parse_int(result.nodes[0].value)[1]


@operator("NTH", num_args=1, precedence=52, check_for_post_traverse=True)
def nth_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    block = expr.rhs
    if block is not None and block.operation.spec.type == "BLOCK":
        n = _int_arg(nav, ctx, block.lhs)
        if n < 0:
            raise EvaluationError("Out of bounds negative array index")
        results: list[Node] = []
        for node in ctx.nodes:
            stream = nav.evaluate(ctx.single_readonly_child(node), block.rhs)
            if n < len(stream.nodes):
                results.append(stream.nodes[n])
        return ctx.child(results)
    n = _int_arg(nav, ctx, expr.rhs)
    results = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError(f"Cannot index {node.tag} with number")
        if -len(node.content) <= n < len(node.content):
            results.append(node.content[n])
    return ctx.child(results)


# ----------------------------------------------------------------------------- limit(n;f) / skip(n;f)

@operator("LIMIT", num_args=1, precedence=52, check_for_post_traverse=True)
def limit_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """yaqpy builds every result at once (design fact 1-3-1), so `limit`/`skip` are just a
    slice of an already-complete list - no early-exit machinery is needed."""
    block = expr.rhs
    assert block is not None and block.operation.spec.type == "BLOCK", (
        "limit(n; f) needs both arguments")
    results: list[Node] = []
    for node in ctx.nodes:
        n = _int_arg(nav, ctx.single_readonly_child(node), block.lhs)
        if n <= 0:
            continue
        stream = nav.evaluate(ctx.single_readonly_child(node), block.rhs)
        results.extend(stream.nodes[:n])
    return ctx.child(results)


@operator("SKIP", num_args=1, precedence=52, check_for_post_traverse=True)
def skip_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    block = expr.rhs
    assert block is not None and block.operation.spec.type == "BLOCK", (
        "skip(n; f) needs both arguments")
    results: list[Node] = []
    for node in ctx.nodes:
        n = max(_int_arg(nav, ctx.single_readonly_child(node), block.lhs), 0)
        stream = nav.evaluate(ctx.single_readonly_child(node), block.rhs)
        results.extend(stream.nodes[n:])
    return ctx.child(results)


# ----------------------------------------------------------------------------- range(...)

_RANGE_LIMIT = 10_000_000


def _flatten_block(node: ExprNode | None) -> list[ExprNode]:
    if node is None:
        return []
    if node.operation.spec.type == "BLOCK":
        return _flatten_block(node.lhs) + _flatten_block(node.rhs)
    return [node]


def _first_number(nav: Navigator, ctx: Context, node_expr: ExprNode) -> float:
    result = nav.evaluate(ctx, node_expr)
    if not result.nodes:
        raise EvaluationError("range: missing argument")
    value = result.nodes[0]
    tag = value.guess_tag()
    if tag not in ("!!int", "!!float"):
        raise EvaluationError(f"range: expected a number, got {value.tag}")
    return tags.parse_float(value.value)


def _range_values(start: float, stop: float, step: float):
    if step == 0:
        return
    value = start
    if step > 0:
        while value < stop:
            yield value
            value += step
    else:
        while value > stop:
            yield value
            value += step


def _number_node(value: float) -> Node:
    if value == int(value):
        return Node.integer(int(value))
    return Node(Kind.SCALAR, tag="!!float", value=tags.format_float(value))


@operator("RANGE", num_args=1, precedence=50)
def range_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    args = _flatten_block(expr.rhs)
    if len(args) not in (1, 2, 3):
        raise EvaluationError("range takes 1 to 3 arguments")
    results: list[Node] = []
    for node in (ctx.nodes or (Node(tag="!!null"),)):
        single = ctx.single_readonly_child(node)
        numbers = [_first_number(nav, single, a) for a in args]
        if len(numbers) == 1:
            start, stop, step = 0.0, numbers[0], 1.0
        elif len(numbers) == 2:
            start, stop, step = numbers[0], numbers[1], 1.0
        else:
            start, stop, step = numbers
        count = 0
        for value in _range_values(start, stop, step):
            count += 1
            if count > _RANGE_LIMIT:
                raise EvaluationError(f"range: refusing to generate more than {_RANGE_LIMIT} values")
            nav.env.budget.tick()
            results.append(_number_node(value))
    return ctx.child(results)


# ----------------------------------------------------------------------------- abs / toboolean / toarray

@operator("ABS", num_args=0, precedence=50)
def abs_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        tag = node.tag if node.tag.startswith("!!") else node.guess_tag()
        if tag == "!!int":
            fmt, value = tags.parse_int(node.value)
            results.append(node.create_replacement(Kind.SCALAR, node.tag, tags.format_int(fmt, abs(value))))
        elif tag == "!!float":
            results.append(node.create_replacement(
                Kind.SCALAR, node.tag, tags.format_float(abs(tags.parse_float(node.value)))))
        else:
            raise EvaluationError(f"{node.tag} ({node.nice_path()}) is not a number, cannot take abs")
    return ctx.child(results)


@operator("TOBOOLEAN", num_args=0, precedence=50)
def toboolean_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        tag = node.tag if node.tag.startswith("!!") else node.guess_tag()
        if tag == "!!bool":
            results.append(node)
        elif tag == "!!str" and node.value in ("true", "false"):
            results.append(create_boolean(node, node.value == "true"))
        else:
            raise EvaluationError(f"Cannot convert {node.tag} ({node.nice_path()}) to boolean")
    return ctx.child(results)


@operator("TOARRAY", num_args=0, precedence=50)
def toarray_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is Kind.SEQUENCE:
            results.append(node)
        else:
            seq = Node.sequence()
            seq.add_child(node.copy())
            results.append(seq)
    return ctx.child(results)


# ----------------------------------------------------------------------------- getpath / path(f) / paths(f)
# Bare `path` (existing GET_PATH), bare `paths` and `leaf_paths` need no new operator - the
# lexer expands them into ordinary expressions (`.. | path | select(length > 0)` and friends;
# see core.lang.lex_rules). `path(f)`/`paths(f)` (jq's prefix, argument forms) do need one each.

@operator("GETPATH", num_args=1, precedence=50)
def getpath_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    from yaqpy.core.lang.ast import create_traversal_tree
    from yaqpy.core.lang.prefs import TraversePrefs
    from yaqpy.core.operators.collections import _path_from_node

    results: list[Node] = []
    for node in ctx.nodes:
        single = ctx.single_readonly_child(node)
        path_ctx = nav.evaluate(single, expr.rhs)
        if not path_ctx.nodes:
            results.append(Node.null())
            continue
        path = _path_from_node("GETPATH", path_ctx.nodes[0])
        tree = create_traversal_tree(path, TraversePrefs(optional_traverse=True), False,
                                     nav.env.operators)
        found = nav.evaluate(single, tree)
        results.append(found.nodes[0] if found.nodes else Node.null())
    return ctx.child(results)


@operator("PATH_OF", num_args=1, precedence=52, check_for_post_traverse=True)
def path_of_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's prefix ``path(f)``: the path(s) ``f`` would navigate to from ``.`` - the same
    thing as the existing postfix ``f | path`` (``GET_PATH``, unchanged), just evaluating
    ``f`` first so both spellings work."""
    from yaqpy.core.operators.collections import get_path_operator

    result = nav.evaluate(ctx, expr.rhs)
    return get_path_operator(nav, result, expr)


def _walk_all(node: Node, prefix: list):
    yield prefix, node
    if node.kind is Kind.SEQUENCE:
        for i, child in enumerate(node.content):
            yield from _walk_all(child, [*prefix, i])
    elif node.kind is Kind.MAPPING:
        for key, value in node.map_items():
            yield from _walk_all(value, [*prefix, key.value])


@operator("PATHS_FILTERED", num_args=1, precedence=52, check_for_post_traverse=True)
def paths_filtered_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's ``paths(node_filter)``: every non-root path whose value matches ``node_filter``."""
    from yaqpy.core.engine.helpers import truthy

    results: list[Node] = []
    for node in ctx.nodes:
        for path, candidate in _walk_all(node, []):
            if not path:
                continue
            matched = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs)
            if any(truthy(n) for n in matched.nodes):
                seq = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
                seq.add_children(Node.integer(p) if isinstance(p, int) else Node.string(p) for p in path)
                results.append(seq)
    return ctx.child(results)


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


# ----------------------------------------------------------------------------- math (E4, 3-11)
# Table-driven: each entry is registered as its own operator type in the loop below rather
# than by hand, so one new function is one dict entry. Type names are prefixed `MATH_` so a
# name jq also uses (`exp`) cannot collide with an unrelated existing type of the same short
# name (`EXP` is already yaqpy's internal "expand this macro expression" operator, used by
# `root`/`paths`/`leaf_paths` - see core.lang.lex_rules._expression).

_INT_RESULT_MATH = frozenset({"MATH_FLOOR", "MATH_CEIL", "MATH_ROUND", "MATH_TRUNC"})


def _round_half_away_from_zero(x: float) -> float:
    """C's (and jq's) ``round``: halves round away from zero, not Python's round-half-to-even."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


_UNARY_MATH: dict[str, Callable[[float], float]] = {
    "MATH_FLOOR": math.floor, "MATH_CEIL": math.ceil, "MATH_ROUND": _round_half_away_from_zero,
    "MATH_TRUNC": math.trunc, "MATH_FABS": math.fabs,
    "MATH_SQRT": math.sqrt, "MATH_CBRT": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "MATH_EXP": math.exp, "MATH_EXP2": math.exp2, "MATH_EXP10": lambda x: 10.0 ** x,
    "MATH_EXPM1": math.expm1,
    "MATH_LOG": math.log, "MATH_LOG2": math.log2, "MATH_LOG10": math.log10, "MATH_LOG1P": math.log1p,
    "MATH_SIN": math.sin, "MATH_COS": math.cos, "MATH_TAN": math.tan,
    "MATH_ASIN": math.asin, "MATH_ACOS": math.acos, "MATH_ATAN": math.atan,
    "MATH_SINH": math.sinh, "MATH_COSH": math.cosh, "MATH_TANH": math.tanh,
    "MATH_ASINH": math.asinh, "MATH_ACOSH": math.acosh, "MATH_ATANH": math.atanh,
}

_BINARY_MATH: dict[str, Callable[[float, float], float]] = {
    "MATH_POW": lambda a, b: a ** b, "MATH_ATAN2": math.atan2, "MATH_COPYSIGN": math.copysign,
    "MATH_HYPOT": math.hypot, "MATH_FMIN": min, "MATH_FMAX": max,
}


def _numeric_value(node: Node) -> float:
    tag = node.tag if node.tag.startswith("!!") else node.guess_tag()
    if tag not in ("!!int", "!!float"):
        raise EvaluationError(f"{node.tag} ({node.nice_path()}) is not a number")
    return tags.parse_float(node.value)


def _math_result_node(name: str, node: Node, value: float) -> Node:
    if name in _INT_RESULT_MATH:
        return node.create_replacement(Kind.SCALAR, "!!int", str(int(value)))
    return node.create_replacement(Kind.SCALAR, "!!float", tags.format_float(float(value)))


def _make_unary_math(name: str, fn: Callable[[float], float]) -> Callable[..., Context]:
    def handler(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
        results: list[Node] = []
        for node in ctx.nodes:
            try:
                value = fn(_numeric_value(node))
            except (ValueError, OverflowError) as e:
                raise EvaluationError(f"{name.removeprefix('MATH_').lower()}: {e}") from None
            results.append(_math_result_node(name, node, value))
        return ctx.child(results)

    return handler


def _make_binary_math(name: str, fn: Callable[[float, float], float]) -> Callable[..., Context]:
    def handler(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
        block = expr.rhs
        assert block is not None and block.operation.spec.type == "BLOCK", f"{name} needs 2 arguments"
        results: list[Node] = []
        for node in ctx.nodes:
            single = ctx.single_readonly_child(node)
            a = _first_number(nav, single, block.lhs)
            b = _first_number(nav, single, block.rhs)
            try:
                value = fn(a, b)
            except (ValueError, OverflowError) as e:
                raise EvaluationError(f"{name.removeprefix('MATH_').lower()}: {e}") from None
            results.append(node.create_replacement(Kind.SCALAR, "!!float", tags.format_float(float(value))))
        return ctx.child(results)

    return handler


for _name, _fn in _UNARY_MATH.items():
    operator(_name, num_args=0, precedence=50)(_make_unary_math(_name, _fn))
for _name, _fn in _BINARY_MATH.items():
    operator(_name, num_args=1, precedence=50)(_make_binary_math(_name, _fn))
