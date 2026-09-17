"""Path traversal: ``.a``, ``.[0]``, ``.[]``, ``..`` (Go's ``operator_traverse_path.go``)."""

from __future__ import annotations

from pyyq.core.engine.context import Context
from pyyq.core.engine.helpers import match_key
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode, Operation
from pyyq.core.lang.prefs import RecursiveDescentPrefs, TraversePrefs
from pyyq.core.model import tags
from pyyq.core.model.node import Kind, Node, Style
from pyyq.core.operators.registry import operator
from pyyq.errors import EvaluationError


def _prefs(op: Operation) -> TraversePrefs:
    return op.prefs if isinstance(op.prefs, TraversePrefs) else TraversePrefs()


@operator("TRAVERSE_PATH")
def traverse_path_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    matches: list[Node] = []
    for node in ctx.nodes:
        matches.extend(traverse(nav, ctx, node, expr.operation))
    return ctx.child(matches)


def traverse(nav: Navigator, ctx: Context, node: Node, op: Operation) -> list[Node]:
    node = node.resolve_alias()
    if node.tag == "!!null" and op.value != "[]" and not ctx.read_only:
        # auto-vivify: guess what it should be
        node.kind = Kind.SEQUENCE if isinstance(op.value, int) else Kind.MAPPING
        node.tag = ""
    if node.kind is Kind.MAPPING:
        return traverse_map(nav, ctx, node, Node.string(op.string_value), _prefs(op), False)
    if node.kind is Kind.SEQUENCE:
        return traverse_array_with_indices(node, [Node(value=op.string_value)], _prefs(op))
    return []


@operator("TRAVERSE_ARRAY")
def traverse_array_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    if (expr.rhs is not None and expr.rhs.rhs is not None
            and expr.rhs.rhs.operation.spec.type == "CREATE_MAP"):
        lhs_ctx = nav.evaluate(ctx, expr.lhs)
        from pyyq.core.operators.slice import slice_array_operator

        return slice_array_operator(nav, lhs_ctx, expr.rhs.rhs)
    lhs = nav.evaluate(ctx, expr.lhs)
    rhs = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    prefs = _prefs(expr.operation)
    if not rhs.nodes:
        raise EvaluationError("cannot index: index expression returned nothing")
    indices = rhs.nodes[0].content
    result = traverse_nodes_with_array_indices(nav, lhs, indices, prefs)
    return ctx.child(result.nodes)


def splat(nav: Navigator, ctx: Context, prefs: TraversePrefs) -> Context:
    return traverse_nodes_with_array_indices(nav, ctx, [], prefs)


def traverse_nodes_with_array_indices(nav: Navigator, ctx: Context, indices: list[Node],
                                      prefs: TraversePrefs) -> Context:
    matches: list[Node] = []
    for node in ctx.nodes:
        matches.extend(traverse_array_indices(nav, ctx, node, indices, prefs))
    return ctx.child(matches)


def traverse_array_indices(nav: Navigator, ctx: Context, node: Node, indices: list[Node],
                           prefs: TraversePrefs) -> list[Node]:
    node = node.resolve_alias()
    if node.tag == "!!null":
        node.tag = ""
        node.kind = Kind.SEQUENCE
        if indices and indices[0].tag != "!!int":
            node.kind = Kind.MAPPING
    if node.kind is Kind.SEQUENCE:
        return traverse_array_with_indices(node, indices, prefs)
    if node.kind is Kind.MAPPING:
        return traverse_map_with_indices(nav, ctx, node, indices, prefs)
    return []


def traverse_map_with_indices(nav: Navigator, ctx: Context, node: Node, indices: list[Node],
                              prefs: TraversePrefs) -> list[Node]:
    if not indices:
        return traverse_map(nav, ctx, node, Node.string(""), prefs, True)
    matches: list[Node] = []
    for index_node in indices:
        matches.extend(traverse_map(nav, ctx, node, index_node, prefs, False))
    return matches


def traverse_array_with_indices(node: Node, indices: list[Node], prefs: TraversePrefs) -> list[Node]:
    if not indices:
        return list(node.content)
    matches: list[Node] = []
    for index_node in indices:
        try:
            index = tags.parse_int(index_node.value)[1]
        except ValueError:
            if prefs.optional_traverse:
                continue
            raise EvaluationError(f"cannot index array with '{index_node.value}'") from None
        length = len(node.content)
        while length <= index:
            if length == 0:
                node.style = Style.NONE
            node.add_child(Node.null())
            length = len(node.content)
        index_to_use = index
        if index_to_use < 0:
            index_to_use = length + index_to_use
        if index_to_use < 0:
            raise EvaluationError(f"index [{index}] out of range, array size is {length}")
        matches.append(node.content[index_to_use])
    return matches


def key_matches(key: Node, wanted: str, exact: bool) -> bool:
    if exact:
        return key.value == wanted
    return match_key(key.value, wanted)


def traverse_map(nav: Navigator, ctx: Context, node: Node, key_node: Node,
                 prefs: TraversePrefs, do_splat: bool) -> list[Node]:
    new_matches: dict[str, Node] = {}
    fix_merge = nav.env.options.yaml.fix_merge_anchor_to_spec
    _do_traverse_map(new_matches, node, key_node.value, prefs, do_splat, fix_merge)
    if not do_splat and not prefs.dont_auto_create and not ctx.read_only and not new_matches:
        value_node = node.create_child()
        value_node.kind = Kind.SCALAR
        value_node.tag = "!!null"
        value_node.value = "null"
        if not node.content:
            node.style = Style.NONE
        key_added, value_added = node.add_key_value(key_node, value_node)
        if prefs.include_map_keys:
            new_matches[key_added.identity_key()] = key_added
        if not prefs.dont_include_map_values:
            new_matches[value_added.identity_key()] = value_added
    return list(new_matches.values())


def _do_traverse_map(new_matches: dict[str, Node], node: Node, wanted: str,
                     prefs: TraversePrefs, do_splat: bool, fix_merge: bool) -> None:
    contents = node.content
    if not prefs.dont_follow_alias and fix_merge:
        for index in range(len(contents) - 2, -1, -2):
            key_node = contents[index]
            if key_node.tag == "!!merge":
                _traverse_merge_anchor(new_matches, contents[index + 1], wanted, prefs,
                                       do_splat, fix_merge)
    for index in range(0, len(contents) - 1, 2):
        key = contents[index]
        value = contents[index + 1]
        if key.tag == "!!merge" and not prefs.dont_follow_alias and wanted != key.value:
            if not fix_merge:
                _traverse_merge_anchor(new_matches, value, wanted, prefs, do_splat, fix_merge)
        elif do_splat or key_matches(key, wanted, prefs.exact_key_match):
            if prefs.include_map_keys:
                new_matches[key.identity_key()] = key
            if not prefs.dont_include_map_values:
                new_matches[value.identity_key()] = value


def _traverse_merge_anchor(new_matches: dict[str, Node], merge: Node, wanted: str,
                           prefs: TraversePrefs, do_splat: bool, fix_merge: bool) -> None:
    if merge.kind is Kind.ALIAS:
        merge = merge.resolve_alias()
    if merge.kind is Kind.MAPPING:
        _do_traverse_map(new_matches, merge, wanted, prefs, do_splat, fix_merge)
    elif merge.kind is Kind.SEQUENCE:
        content = list(reversed(merge.content)) if fix_merge else list(merge.content)
        for child in content:
            if child.kind is Kind.ALIAS:
                child = child.resolve_alias()
            if child.kind is not Kind.MAPPING:
                return
            _do_traverse_map(new_matches, child, wanted, prefs, do_splat, fix_merge)


@operator("RECURSIVE_DESCENT")
def recursive_descent_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    if not isinstance(prefs, RecursiveDescentPrefs):
        prefs = RecursiveDescentPrefs(recurse_array=True)
    results: list[Node] = []
    recursive_descent(nav, results, ctx, prefs)
    return ctx.child(results)


def recursive_descent(nav: Navigator, results: list[Node], ctx: Context,
                      prefs: RecursiveDescentPrefs, depth: int = 0) -> None:
    if depth > nav.env.limits.max_depth:
        raise EvaluationError("document nesting too deep")
    for node in ctx.nodes:
        results.append(node)
        if (node.kind is not Kind.ALIAS and node.content
                and (prefs.recurse_array or node.kind is not Kind.SEQUENCE)):
            children = splat(nav, ctx.single_child(node), prefs.traverse)
            recursive_descent(nav, results, children, prefs, depth + 1)
