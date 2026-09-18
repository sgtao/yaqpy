"""``explode`` and the anchor/alias getters (needed by the printer for JSON output).

``explode_node`` follows Go's two merge-key strategies:

* legacy (default): entries are processed in document order, a merge key
  overrides earlier entries and later entries override the merge; sequences
  of merges are applied in reverse so earlier aliases win.
* ``--yaml-fix-merge-anchor-to-spec``: explicit keys always win and earlier
  merge items take precedence, as the YAML merge-key spec says.
"""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError

_MERGE_ERROR = ("can only use merge anchors with maps (!!map) or sequences (!!seq) of maps, "
                "but got sequence containing {tag}")


@operator("GET_ANCHOR")
def get_anchor_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.create_replacement(Kind.SCALAR, "!!str", n.anchor) for n in ctx.nodes)


@operator("ASSIGN_ANCHOR")
def assign_anchor_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    anchor = ""
    if not expr.operation.update_assign:
        rhs = nav.evaluate(ctx.readonly_clone(), expr.rhs)
        if rhs.nodes:
            anchor = rhs.nodes[0].value
    lhs = nav.evaluate(ctx, expr.lhs)
    for candidate in lhs.nodes:
        if expr.operation.update_assign:
            rhs = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs)
            if rhs.nodes:
                anchor = rhs.nodes[0].value
        candidate.anchor = anchor
    return ctx


@operator("GET_ALIAS")
def get_alias_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(
        n.create_replacement(Kind.SCALAR, "!!str", n.value if n.kind is Kind.ALIAS else "")
        for n in ctx.nodes)


@operator("ASSIGN_ALIAS")
def assign_alias_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    alias = ""
    if not expr.operation.update_assign:
        rhs = nav.evaluate(ctx.readonly_clone(), expr.rhs)
        if rhs.nodes:
            alias = rhs.nodes[0].value
    lhs = nav.evaluate(ctx, expr.lhs)
    for candidate in lhs.nodes:
        if expr.operation.update_assign:
            rhs = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs)
            if rhs.nodes:
                alias = rhs.nodes[0].value
        if alias != "":
            candidate.kind = Kind.ALIAS
            candidate.value = alias
            candidate.content = []
    return ctx


# ----------------------------------------------------------------------------- explode

def explode_node(node: Node, *, fix_merge: bool = False, depth: int = 0,
                 max_depth: int = 1000) -> None:
    if depth > max_depth:
        raise EvaluationError("alias nesting too deep")
    node.anchor = ""
    if node.kind is Kind.SEQUENCE:
        for child in node.content:
            explode_node(child, fix_merge=fix_merge, depth=depth + 1, max_depth=max_depth)
        return
    if node.kind is Kind.ALIAS:
        if node.alias is not None:
            target = node.resolve_alias()
            node.kind = target.kind
            node.style = target.style
            node.tag = target.tag
            node.content = []
            node.add_children(target.content)
            node.value = target.value
            node.alias = None
        return
    if node.kind is Kind.MAPPING:
        has_merge = any(k.tag == "!!merge" for k, _ in node.map_items())
        if has_merge:
            if fix_merge:
                _fixed_reconstruct(node, depth, max_depth)
            else:
                _legacy_reconstruct(node, depth, max_depth)
            return
        for key, value in node.map_items():
            explode_node(key, fix_merge=fix_merge, depth=depth + 1, max_depth=max_depth)
            explode_node(value, fix_merge=fix_merge, depth=depth + 1, max_depth=max_depth)


def _merge_items(value: Node) -> list[Node]:
    sequence = value.resolve_alias() if value.kind is Kind.ALIAS else value
    if sequence.kind is Kind.SEQUENCE:
        return list(sequence.content)
    return [sequence]


def _set_entries(node: Node, entries: list[tuple[Node, Node]]) -> None:
    node.content = []
    for key, value in entries:
        node.add_key_value(key, value)


def _legacy_reconstruct(node: Node, depth: int, max_depth: int) -> None:
    """Go's ``reconstructAliasedMap``: document order, last writer wins."""
    entries: list[tuple[Node, Node]] = []
    original = list(node.map_items())

    def override(key: Node, value: Node, start_index: int) -> None:
        explode_node(value, fix_merge=False, depth=depth + 1, max_depth=max_depth)
        for i, (existing_key, _) in enumerate(entries):
            if existing_key.value == key.value:
                entries[i] = (existing_key, value)
                return
        # a later explicit entry with the same key will override this one
        for later_key, _ in original[start_index + 1:]:
            if later_key.value == key.value and later_key.kind is not Kind.ALIAS:
                return
        explode_node(key, fix_merge=False, depth=depth + 1, max_depth=max_depth)
        entries.append((key, value))

    def apply_alias(target: Node, index: int) -> None:
        target = target.resolve_alias() if target.kind is Kind.ALIAS else target
        if target.kind is not Kind.MAPPING:
            raise EvaluationError(_MERGE_ERROR.format(tag=target.tag))
        for mkey, mvalue in target.map_items():
            override(mkey.copy(), mvalue.copy(), index)

    for index, (key, value) in enumerate(original):
        if key.tag != "!!merge":
            override(key, value, index)
        elif value.kind is Kind.SEQUENCE or (value.kind is Kind.ALIAS
                                              and value.resolve_alias().kind is Kind.SEQUENCE):
            for item in reversed(_merge_items(value)):
                apply_alias(item, index)
        else:
            apply_alias(value, index)
    _set_entries(node, entries)


def _fixed_reconstruct(node: Node, depth: int, max_depth: int) -> None:
    """Go's ``fixedReconstructAliasedMap``: explicit keys win, earlier merges win."""
    entries: list[tuple[Node, Node]] = []
    explicit_keys = {k.value for k, _ in node.map_items() if k.tag != "!!merge"}
    for key, value in node.map_items():
        if key.tag != "!!merge":
            explode_node(key, fix_merge=True, depth=depth + 1, max_depth=max_depth)
            explode_node(value, fix_merge=True, depth=depth + 1, max_depth=max_depth)
            entries.append((key, value))
            continue
        for item in _merge_items(value):
            merged = (item.resolve_alias() if item.kind is Kind.ALIAS else item).copy()
            explode_node(merged, fix_merge=True, depth=depth + 1, max_depth=max_depth)
            if merged.kind is not Kind.MAPPING:
                raise EvaluationError(_MERGE_ERROR.format(tag=merged.tag))
            present = explicit_keys | {k.value for k, _ in entries}
            for mkey, mvalue in merged.map_items():
                if mkey.value not in present:
                    entries.append((mkey, mvalue))
                    present.add(mkey.value)
    _set_entries(node, entries)


@operator("EXPLODE")
def explode_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    fix_merge = nav.env.options.yaml.fix_merge_anchor_to_spec
    for candidate in ctx.nodes:
        rhs = nav.evaluate(ctx.single_child(candidate), expr.rhs)
        for child in rhs.nodes:
            explode_node(child, fix_merge=fix_merge, max_depth=nav.env.limits.max_depth)
    return ctx
