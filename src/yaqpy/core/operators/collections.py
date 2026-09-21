"""Collect, object construction, keys/entries, map, sort, delete, has, length, path."""

from __future__ import annotations

import functools
from datetime import datetime

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import create_boolean, cross_function, truthy
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode, Operation, create_traversal_tree
from yaqpy.core.lang.prefs import MultiplyPrefs, TraversePrefs
from yaqpy.core.model import tags
from yaqpy.core.model.datetime_util import RFC3339, parse_datetime
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.core.operators.multiply import multiply
from yaqpy.core.operators.registry import operator
from yaqpy.core.operators.traverse import splat, traverse_map
from yaqpy.errors import EvaluationError


# ----------------------------------------------------------------------------- collect

def collect_together(nav: Navigator, ctx: Context, expr: ExprNode | None) -> Node:
    collected = Node.sequence()
    for node in ctx.nodes:
        results = nav.evaluate(ctx.single_readonly_child(node), expr)
        for result in results.nodes:
            collected.add_child(result)
    return collected


@operator("COLLECT")
def collect_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    if not ctx.nodes:
        return ctx.single_child(Node.sequence(value="[]"))
    if ctx.evaluate_all_together():
        return ctx.single_child(collect_together(nav, ctx, expr.rhs))
    results: list[Node] = []
    for node in ctx.nodes:
        collected = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
        inner = nav.evaluate(ctx.single_child(node), expr.rhs)
        for result in inner.nodes:
            collected.add_child(result)
        results.append(collected)
    return ctx.child(results)


# ----------------------------------------------------------------------------- objects

def _list_to_seq(nodes: list[Node]) -> Node:
    seq = Node.sequence()
    for node in nodes:
        seq.add_child(node)
    return seq


def _sequence_for(nav: Navigator, ctx: Context, node: Node | None, expr: ExprNode) -> Node:
    document = filename = None
    file_index = 0
    matches: list[Node] = []
    if node is not None:
        document = node.document()
        filename = node.get_filename()
        file_index = node.get_file_index()
        matches.append(node)

    def make_pair(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        assert lhs is not None and rhs is not None
        pair = Node.mapping()
        pair.add_key_value(lhs, rhs)
        pair.document_index = document or 0
        pair.file_index = file_index
        pair.filename = filename or ""
        return pair

    pairs = cross_function(nav, ctx.child(matches), expr, make_pair, False)
    inner = _list_to_seq(list(pairs.nodes))
    inner.style = Style.FLOW
    inner.document_index = document or 0
    inner.file_index = file_index
    inner.filename = filename or ""
    return inner


@operator("CREATE_MAP")
def create_map_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    sequences: list[Node] = []
    if ctx.nodes:
        for node in ctx.nodes:
            sequences.append(_sequence_for(nav, ctx, node, expr))
    else:
        sequences.append(_sequence_for(nav, ctx, None, expr))
    return ctx.single_child(_list_to_seq(sequences))


def _collect_object(nav: Navigator, ctx: Context, remaining: list[Node]) -> Context:
    if not remaining:
        return ctx
    candidate = remaining.pop(0)
    splatted = splat(nav, ctx.single_child(candidate),
                     TraversePrefs(dont_follow_alias=True, include_map_keys=False))
    if not ctx.nodes:
        return _collect_object(nav, splatted, remaining)
    new_agg: list[Node] = []
    mult = multiply(MultiplyPrefs(append_arrays=False))
    for agg in ctx.nodes:
        for piece in splatted.nodes:
            merged = mult(nav, ctx, agg.copy(), piece)
            assert merged is not None
            new_agg.append(merged)
    return _collect_object(nav, ctx.child(new_agg), remaining)


@operator("COLLECT_OBJECT")
def collect_object_operator(nav: Navigator, original: Context, expr: ExprNode) -> Context:
    ctx = original.writable_clone()
    if not ctx.nodes:
        return ctx.single_child(Node.mapping(value="{}"))
    first = ctx.nodes[0]
    rotated: list[list[Node]] = [[] for _ in first.content]
    for node in ctx.nodes:
        if len(node.content) < len(first.content):
            raise EvaluationError(
                "CollectObject: mismatching node sizes; are you creating a map with mismatching key value pairs?")
        for i in range(len(first.content)):
            rotated[i].append(node.content[i])
    new_object: list[Node] = []
    for i in range(len(first.content)):
        additions = _collect_object(nav, ctx.child([]), rotated[i])
        for addition in additions.nodes:
            clone = addition.copy()
            clone.parent = None
            clone.key = None
            new_object.append(clone)
    return ctx.child(new_object)


# ----------------------------------------------------------------------------- length / keys / has

@operator("LENGTH")
def length_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is Kind.SCALAR:
            length = 0 if node.tag == "!!null" else len(node.value)
        elif node.kind is Kind.MAPPING:
            length = len(node.content) // 2
        elif node.kind is Kind.SEQUENCE:
            length = len(node.content)
        else:
            length = 0
        results.append(node.create_replacement(Kind.SCALAR, "!!int", str(length)))
    return ctx.child(results)


@operator("KEYS")
def keys_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        seq = Node.sequence()
        if node.kind is Kind.MAPPING:
            seq.add_children(node.content[i] for i in range(0, len(node.content), 2))
        elif node.kind is Kind.SEQUENCE:
            seq.add_children(Node.integer(i) for i in range(len(node.content)))
        else:
            raise EvaluationError(f"cannot get keys of {node.tag}, keys only works for maps and arrays")
        results.append(seq)
    return ctx.child(results)


@operator("GET_KEY")
def get_key_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.key for n in ctx.nodes if n.key is not None)


@operator("IS_KEY")
def is_key_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(create_boolean(n, n.is_map_key) for n in ctx.nodes)


@operator("HAS")
def has_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    rhs = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    wanted_key = "null"
    wanted = Node(tag="!!null")
    if rhs.nodes:
        wanted = rhs.nodes[0]
        wanted_key = wanted.value
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is Kind.MAPPING:
            has = any(k.value == wanted_key for k, _ in node.map_items())
        elif node.kind is Kind.SEQUENCE:
            has = False
            if wanted.tag == "!!int":
                number = tags.parse_int(wanted_key)[1]
                has = 0 <= number < len(node.content)
        else:
            has = False
        results.append(create_boolean(node, has))
    return ctx.child(results)


# ----------------------------------------------------------------------------- entries

def _entry(key: Node, value: Node) -> Node:
    entry = Node.mapping()
    entry.add_key_value(Node.string("key"), key)
    entry.add_key_value(Node.string("value"), value)
    return entry


def _to_entries(node: Node) -> Node:
    seq = node.create_replacement_with_comments(Kind.SEQUENCE, "!!seq", Style.NONE)
    if node.kind is Kind.MAPPING:
        for key, value in node.map_items():
            seq.add_child(_entry(key, value))
    else:
        for i, value in enumerate(node.content):
            seq.add_child(_entry(Node.integer(i), value))
    return seq


@operator("TO_ENTRIES")
def to_entries_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind in (Kind.MAPPING, Kind.SEQUENCE):
            results.append(_to_entries(node))
        elif node.tag != "!!null":
            raise EvaluationError(f"{node.tag} has no keys")
    return ctx.child(results)


def _parse_entry(nav: Navigator, ctx: Context, entry: Node, position: int) -> tuple[Node, Node]:
    prefs = TraversePrefs(dont_auto_create=True)
    keys = traverse_map(nav, ctx.readonly_clone(), entry, Node.string("key"), prefs, False)
    if len(keys) != 1:
        raise EvaluationError(
            f"expected to find one 'key' entry but found {len(keys)} in position {position}")
    values = traverse_map(nav, ctx.readonly_clone(), entry, Node.string("value"), prefs, False)
    if len(values) != 1:
        raise EvaluationError(
            f"expected to find one 'value' entry but found {len(values)} in position {position}")
    return keys[0], values[0]


def _from_entries(nav: Navigator, ctx: Context, node: Node) -> Node:
    out = node.copy_without_content()
    for i, entry in enumerate(node.content):
        key, value = _parse_entry(nav, ctx, entry.resolve_alias(), i)
        out.add_key_value(key, value)
    out.kind = Kind.MAPPING
    out.tag = "!!map"
    return out


@operator("FROM_ENTRIES")
def from_entries_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if node.kind is not Kind.SEQUENCE:
            raise EvaluationError("from entries only runs against arrays")
        results.append(_from_entries(nav, ctx, node))
    return ctx.child(results)


@operator("WITH_ENTRIES")
def with_entries_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    entries = to_entries_operator(nav, ctx, expr)
    results: list[Node] = []
    for candidate in entries.nodes:
        splatted = splat(nav, ctx.single_child(candidate), TraversePrefs())
        new_results: list[Node] = []
        for item in splatted.nodes:
            result = nav.evaluate(splatted.single_child(item), expr.rhs)
            new_results.extend(result.nodes)
        self_exp = ExprNode(Operation(nav.env.operators.get("SELF")))
        collected = collect_together(nav, splatted.child(new_results), self_exp)
        collected.leading_content = candidate.leading_content
        collected.head_comment = candidate.head_comment
        collected.foot_comment = candidate.foot_comment
        results.extend(from_entries_operator(nav, ctx.single_child(collected), expr).nodes)
    return ctx.child(results)


# ----------------------------------------------------------------------------- map

@operator("MAP")
def map_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        splatted = splat(nav, ctx.single_child(node), TraversePrefs())
        if not splatted.nodes:
            results.append(node.copy())
            continue
        result = nav.evaluate(splatted, expr.rhs)
        self_exp = ExprNode(Operation(nav.env.operators.get("SELF")))
        collected = collect_together(nav, result, self_exp)
        collected.style = node.style
        results.append(collected)
    return ctx.child(results)


@operator("MAP_VALUES")
def map_values_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    from yaqpy.core.operators.assign import assign_update_operator

    for node in ctx.nodes:
        splatted = splat(nav, ctx.single_child(node), TraversePrefs())
        update = ExprNode(Operation(nav.env.operators.get("ASSIGN"), update_assign=True),
                          rhs=expr.rhs)
        assign_update_operator(nav, splatted, update)
    return ctx


# ----------------------------------------------------------------------------- sort

def _both_datetimes(lhs: Node, rhs: Node, layout: str) -> tuple[datetime, datetime] | None:
    """The two parsed times when both nodes are timestamps in ``layout``, else None."""
    try:
        return parse_datetime(layout, lhs.value), parse_datetime(layout, rhs.value)
    except ValueError:
        return None


def _compare_nodes(lhs: Node, rhs: Node, layout: str = RFC3339) -> int:
    lhs_tag = lhs.guess_tag()
    rhs_tag = rhs.guess_tag()
    is_datetime = lhs_tag == "!!timestamp" and rhs_tag == "!!timestamp"
    if lhs_tag == "!!str" and layout != RFC3339:      # a string may be a time in a custom layout
        is_datetime = _both_datetimes(lhs, rhs, layout) is not None
    if lhs_tag == "!!null" and rhs_tag != "!!null":
        return -1
    if lhs_tag != "!!null" and rhs_tag == "!!null":
        return 1
    if lhs_tag == "!!bool" and rhs_tag != "!!bool":
        return -1
    if lhs_tag != "!!bool" and rhs_tag == "!!bool":
        return 1
    if lhs_tag == "!!bool" and rhs_tag == "!!bool":
        a, b = lhs.is_truthy(), rhs.is_truthy()
        return 0 if a == b else (1 if a else -1)
    if is_datetime:
        times = _both_datetimes(lhs, rhs, layout)
        if times is None:                             # sort by the text instead
            return (lhs.value > rhs.value) - (lhs.value < rhs.value)
        return (times[0] > times[1]) - (times[0] < times[1])
    if lhs_tag == "!!int" and rhs_tag == "!!int":
        a, b = tags.parse_int(lhs.value)[1], tags.parse_int(rhs.value)[1]
        return (a > b) - (a < b)
    if lhs_tag in ("!!int", "!!float") and rhs_tag in ("!!int", "!!float"):
        a, b = tags.parse_float(lhs.value), tags.parse_float(rhs.value)
        return (a > b) - (a < b)
    return (lhs.value > rhs.value) - (lhs.value < rhs.value)


def _compare_contexts(a: tuple[Node, Context], b: tuple[Node, Context], layout: str = RFC3339) -> int:
    lhs_nodes, rhs_nodes = a[1].nodes, b[1].nodes
    for lhs, rhs in zip(lhs_nodes, rhs_nodes):
        result = _compare_nodes(lhs, rhs, layout)
        if result != 0:
            return result
    return (len(lhs_nodes) > len(rhs_nodes)) - (len(lhs_nodes) < len(rhs_nodes))


def sort_by(nav: Navigator, ctx: Context, rhs: ExprNode | None) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        if not node.can_visit_values():
            raise EvaluationError(
                f"node at path [{node.nice_path()}] is not an array or map (it's a {node.tag})")
        sortable: list[tuple[Node, Context]] = []
        for value in node.values():
            compare_ctx = nav.evaluate(ctx.single_readonly_child(value), rhs)
            sortable.append((value, compare_ctx))
        layout = ctx.get_datetime_layout()
        sortable.sort(key=functools.cmp_to_key(lambda a, b: _compare_contexts(a, b, layout)))
        sorted_node = node.copy_without_content()
        if node.kind is Kind.MAPPING:
            for value, _ in sortable:
                assert value.key is not None
                sorted_node.add_key_value(value.key, value)
        else:
            for value, _ in sortable:
                sorted_node.add_child(value)
        results.append(sorted_node)
    return ctx.child(results)


@operator("SORT_BY")
def sort_by_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return sort_by(nav, ctx, expr.rhs)


@operator("SORT")
def sort_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    self_exp = ExprNode(Operation(nav.env.operators.get("SELF")))
    return sort_by(nav, ctx, self_exp)


# ----------------------------------------------------------------------------- delete

def _normalise_empty_collection_comment(node: Node) -> None:
    if node.kind not in (Kind.SEQUENCE, Kind.MAPPING) or node.content or node.line_comment != "":
        return
    key = node.key
    if node.parent is not None and node.parent.kind is Kind.MAPPING:
        for k, v in node.parent.map_items():
            if v is node:
                key = k
                break
    if key is None or key.line_comment == "":
        return
    node.line_comment = key.line_comment
    key.line_comment = ""
    node.style = Style.FLOW


def delete_from_map(node: Node, child_path: str | int) -> None:
    new_content: list[Node] = []
    for key, value in node.map_items():
        if key.value != child_path:
            new_content.extend((key, value))
    node.content = new_content
    _normalise_empty_collection_comment(node)


def delete_from_array(node: Node, child_path: str | int) -> None:
    new_content: list[Node] = []
    for index, value in enumerate(node.content):
        if str(index) != str(child_path):
            assert value.key is not None
            value.key.value = str(len(new_content))
            new_content.append(value)
    node.content = new_content
    _normalise_empty_collection_comment(node)


@operator("DELETE")
def delete_child_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    to_delete = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    for candidate in reversed(to_delete.nodes):
        if candidate.parent is None:
            return ctx.child(n for n in ctx.nodes if n is not candidate)
        parent = candidate.parent
        path = candidate.path()
        child_path = path[-1]
        if parent.kind is Kind.MAPPING:
            delete_from_map(parent, child_path)
        elif parent.kind is Kind.SEQUENCE:
            delete_from_array(parent, child_path)
        else:
            raise EvaluationError(f"cannot delete nodes from parent of tag {parent.tag}")
    return ctx


# ----------------------------------------------------------------------------- path

def _path_node(element: str | int) -> Node:
    if isinstance(element, str):
        return Node.string(element)
    return Node.integer(element)


@operator("GET_PATH")
def get_path_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for node in ctx.nodes:
        seq = node.create_replacement(Kind.SEQUENCE, "!!seq", "")
        seq.add_children(_path_node(p) for p in node.path())
        results.append(seq)
    return ctx.child(results)


def _path_from_node(func: str, node: Node) -> list[str | int]:
    if node.kind is not Kind.SEQUENCE:
        raise EvaluationError(f"{func}: expected path array, but got {node.tag} instead")
    path: list[str | int] = []
    for child in node.content:
        if child.tag == "!!str":
            path.append(child.value)
        elif child.tag == "!!int":
            path.append(tags.parse_int(child.value)[1])
        else:
            raise EvaluationError(
                f"{func}: expected either a !!str or !!int in the path, found {child.tag} instead")
    return path


@operator("SET_PATH")
def set_path_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    assert expr.rhs is not None
    if expr.rhs.operation.spec.type != "BLOCK":
        raise EvaluationError(
            f"SETPATH must be given a block (;), got {expr.rhs.operation.spec.type} instead")
    lhs_ctx = nav.evaluate(ctx.readonly_clone(), expr.rhs.lhs)
    if len(lhs_ctx.nodes) != 1:
        raise EvaluationError(f"SETPATH: expected single path but found {len(lhs_ctx.nodes)} results instead")
    path = _path_from_node("SETPATH", lhs_ctx.nodes[0])
    registry = nav.env.operators
    tree_lhs = create_traversal_tree(path, TraversePrefs(), False, registry)
    for candidate in ctx.nodes:
        target = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs.rhs)
        if len(target.nodes) != 1:
            raise EvaluationError(f"SETPATH: expected single value on RHS but found {len(target.nodes)}")
        assignment = ExprNode(Operation(registry.get("ASSIGN")), lhs=tree_lhs,
                              rhs=ExprNode(Operation(registry.get("REF"), node=target.nodes[0])))
        nav.evaluate(ctx.single_child(candidate), assignment)
    return ctx


@operator("DEL_PATHS")
def del_paths_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    paths_ctx = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    if len(paths_ctx.nodes) != 1:
        raise EvaluationError(f"DELPATHS: expected single value but found {len(paths_ctx.nodes)}")
    paths_node = paths_ctx.nodes[0]
    if paths_node.tag != "!!seq":
        raise EvaluationError(f"DELPATHS: expected a sequence of sequences, but found {paths_node.tag}")
    registry = nav.env.operators
    updated = ctx
    for i, child in enumerate(paths_node.content):
        if child.tag != "!!seq":
            raise EvaluationError(
                f"DELPATHS: expected entry [{i}] to be a sequence, but its a {child.tag}. "
                'Note that delpaths takes an array of path arrays, e.g. [["a", "b"]]')
        path = _path_from_node("DELPATHS", child)
        delete = ExprNode(Operation(registry.get("DELETE")),
                          rhs=create_traversal_tree(path, TraversePrefs(), False, registry))
        updated = nav.evaluate(updated, delete)
    return updated
