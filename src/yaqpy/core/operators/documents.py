"""Document operators: split_doc (Go's ``operator_split_document.go``)."""

from __future__ import annotations

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.operators.registry import operator


@operator("SPLIT_DOC")
def split_document_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """Give every matched node its own document, so each is printed after a ``---``."""
    for index, candidate in enumerate(ctx.nodes):
        candidate.document_index = index
        candidate.parent = None
    return ctx
