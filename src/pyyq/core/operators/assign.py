"""Assignment: ``=``, ``|=`` and attribute assignment (Go's ``operator_assign.go``)."""

from __future__ import annotations

from pyyq.core.engine.context import Context
from pyyq.core.engine.helpers import cross_function, get_assign_prefs
from pyyq.core.engine.navigator import Navigator
from pyyq.core.lang.ast import ExprNode
from pyyq.core.lang.prefs import AssignPrefs
from pyyq.core.model.node import Node
from pyyq.core.operators.registry import operator


def _assign_update(prefs: AssignPrefs):
    def calc(nav: Navigator, ctx: Context, lhs: Node | None, rhs: Node | None) -> Node | None:
        assert lhs is not None and rhs is not None
        if not prefs.only_write_null or lhs.tag == "!!null":
            lhs.update_from(rhs, dont_overwrite_anchor=prefs.dont_overwrite_anchor,
                            clobber_custom_tags=prefs.clobber_custom_tags)
        return lhs

    return calc


@operator("ASSIGN")
def assign_update_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    lhs = nav.evaluate(ctx, expr.lhs)
    prefs = get_assign_prefs(expr.operation.prefs)
    if not expr.operation.update_assign:
        cross_function(nav, ctx.readonly_clone(), expr, _assign_update(prefs), False)
        return ctx
    # traverse backwards so children are updated before parents (`.. |= [.]`)
    for candidate in reversed(lhs.nodes):
        rhs = nav.evaluate(ctx.single_child(candidate), expr.rhs)
        if rhs.nodes:
            candidate.update_from(rhs.nodes[0], dont_overwrite_anchor=prefs.dont_overwrite_anchor,
                                  clobber_custom_tags=prefs.clobber_custom_tags)
    return ctx


@operator("ASSIGN_ATTRIBUTES")
def assign_attributes_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    lhs = nav.evaluate(ctx, expr.lhs)
    for candidate in lhs.nodes:
        rhs = nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs)
        if rhs.nodes:
            prefs = expr.operation.prefs if isinstance(expr.operation.prefs, AssignPrefs) else AssignPrefs()
            if not prefs.only_write_null or candidate.tag == "!!null":
                candidate.update_attributes_from(
                    rhs.nodes[0], dont_overwrite_anchor=prefs.dont_overwrite_anchor,
                    clobber_custom_tags=prefs.clobber_custom_tags)
    return ctx
