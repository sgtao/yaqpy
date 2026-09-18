"""Expression AST (design doc section 6-6) and the operator specification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yaqpy.core.model.node import Node

# The real signature is (Navigator, Context, ExprNode) -> Context; ``Any`` keeps
# core.lang free of an import on core.engine (design doc 4-2).
type OperatorHandler = Callable[[Any, Any, "ExprNode"], Any]


@dataclass(frozen=True, slots=True)
class OperatorSpec:
    """Go's ``operationType``."""

    type: str
    num_args: int
    precedence: int
    handler: OperatorHandler | None = None
    check_for_post_traverse: bool = False

    def with_handler(self, handler: OperatorHandler) -> OperatorSpec:
        return OperatorSpec(self.type, self.num_args, self.precedence, handler,
                            self.check_for_post_traverse)


@dataclass(slots=True)
class Operation:
    """Go's ``Operation``. Mutable while the expression is being built; treated as
    immutable once it is part of a compiled ``Expression``."""

    spec: OperatorSpec
    value: Any = None
    string_value: str = ""
    node: Node | None = None
    prefs: Any = None
    update_assign: bool = False
    position: int = -1

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.spec.type in ("VALUE", "STRING_INT"):
            return f"{self.value!r} ({type(self.value).__name__})"
        if self.spec.type == "TRAVERSE_PATH":
            return f"{self.value}"
        return self.spec.type


@dataclass(slots=True)
class ExprNode:
    operation: Operation
    lhs: ExprNode | None = None
    rhs: ExprNode | None = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        parts = [repr(self.operation)]
        if self.lhs is not None:
            parts.append(f"lhs={self.lhs!r}")
        if self.rhs is not None:
            parts.append(f"rhs={self.rhs!r}")
        return "(" + " ".join(parts) + ")"


def create_traversal_tree(path: list[str | int], traverse_prefs: Any, target_key: bool,
                          registry: Any) -> ExprNode:
    """Go's ``createTraversalTree``: build ``.a.b[0]`` from a path list."""
    from yaqpy.core.lang.prefs import TraversePrefs

    if not path:
        return ExprNode(Operation(registry.get("SELF")))
    if len(path) == 1:
        prefs = traverse_prefs if isinstance(traverse_prefs, TraversePrefs) else TraversePrefs()
        if target_key:
            prefs = TraversePrefs(
                dont_follow_alias=prefs.dont_follow_alias,
                include_map_keys=True,
                dont_auto_create=prefs.dont_auto_create,
                dont_include_map_values=True,
                optional_traverse=prefs.optional_traverse,
                exact_key_match=prefs.exact_key_match,
            )
        op = Operation(registry.get("TRAVERSE_PATH"), value=path[0],
                       string_value=str(path[0]), prefs=prefs)
        return ExprNode(op)
    return ExprNode(
        Operation(registry.get("SHORT_PIPE")),
        lhs=create_traversal_tree(path[:1], traverse_prefs, False, registry),
        rhs=create_traversal_tree(path[1:], traverse_prefs, target_key, registry),
    )
