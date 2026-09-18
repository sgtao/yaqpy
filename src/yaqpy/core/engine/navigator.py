"""The evaluator (Go's ``dataTreeNavigator``), design doc 7-2."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from yaqpy.core.engine.context import Context, EvalEnv
from yaqpy.core.lang.ast import ExprNode, Operation, create_traversal_tree
from yaqpy.core.lang.prefs import AssignPrefs, MultiplyPrefs, TraversePrefs
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import EvaluationError

log = logging.getLogger("yaqpy.engine")


class Navigator:
    __slots__ = ("env", "_depth")

    def __init__(self, env: EvalEnv) -> None:
        self.env = env
        self._depth = 0

    def evaluate(self, ctx: Context, expr: ExprNode | None) -> Context:
        if expr is None:
            return ctx
        self.env.budget.tick()
        handler = expr.operation.spec.handler
        if handler is None:
            raise EvaluationError(f"unknown operator {expr.operation.spec.type}")
        self._depth += 1
        try:
            if self._depth > self.env.limits.max_depth:
                raise EvaluationError("expression nesting too deep")
            if log.isEnabledFor(logging.DEBUG):
                log.debug("Processing Op: %r with %d nodes", expr.operation, len(ctx.nodes))
            return handler(self, ctx, expr)
        finally:
            self._depth -= 1

    def spec(self, name: str) -> object:
        return self.env.operators.get(name)

    def deeply_assign(self, ctx: Context, path: Sequence[str | int], rhs: Node) -> None:
        """Go's ``DeeplyAssign``: build an assignment expression for a path and run it."""
        registry = self.env.operators
        if rhs.kind is Kind.MAPPING:
            assignment = Operation(
                registry.get("MULTIPLY_ASSIGN"),
                prefs=MultiplyPrefs(append_arrays=True,
                                    traverse=TraversePrefs(dont_follow_alias=True),
                                    assign=AssignPrefs()),
            )
        else:
            assignment = Operation(registry.get("ASSIGN"), prefs=AssignPrefs())
        rhs_op = Operation(registry.get("VALUE"), node=rhs)
        tree = ExprNode(
            assignment,
            lhs=create_traversal_tree(list(path), TraversePrefs(), False, registry),
            rhs=ExprNode(rhs_op),
        )
        self.evaluate(ctx, tree)
