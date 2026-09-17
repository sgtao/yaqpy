"""OperatorSpec registry and the ``@operator`` decorator (design doc 8-1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyyq.core.lang.ast import OperatorHandler, OperatorSpec
from pyyq.core.lang.specs import BASE_SPECS
from pyyq.errors import ExpressionSyntaxError


class OperatorRegistry:
    """Maps operator type names to specs (with handlers bound)."""

    def __init__(self) -> None:
        self._specs: dict[str, OperatorSpec] = {}
        self._frozen = False

    def register(self, spec: OperatorSpec) -> None:
        if self._frozen:
            raise RuntimeError("registry is frozen; call copy() to extend it")
        self._specs[spec.type] = spec

    def bind(self, type_name: str, handler: OperatorHandler) -> None:
        """Attach a handler to one of the base specs."""
        base = self._specs.get(type_name) or BASE_SPECS[type_name]
        self.register(base.with_handler(handler))

    def get(self, type_name: str) -> OperatorSpec:
        spec = self._specs.get(type_name)
        if spec is None:
            base = BASE_SPECS.get(type_name)
            if base is None:
                raise ExpressionSyntaxError(f"unknown operator {type_name}")
            return base
        return spec

    def has_handler(self, type_name: str) -> bool:
        spec = self._specs.get(type_name)
        return spec is not None and spec.handler is not None

    def freeze(self) -> OperatorRegistry:
        self._frozen = True
        return self

    def copy(self) -> OperatorRegistry:
        new = OperatorRegistry()
        new._specs = dict(self._specs)
        return new

    def names(self) -> list[str]:
        return sorted(self._specs)


# Handlers collected by the @operator decorator, in import order.
_BUILTIN_HANDLERS: list[tuple[str, OperatorHandler, dict[str, Any]]] = []


def operator(type_name: str, *, num_args: int | None = None, precedence: int | None = None,
             check_for_post_traverse: bool | None = None) -> Callable[[OperatorHandler], OperatorHandler]:
    """Register ``fn`` as the handler for ``type_name`` in the builtin registry.

    Arity and precedence come from the base table unless overridden (for
    user-defined operators that are not in the table)."""

    def decorate(fn: OperatorHandler) -> OperatorHandler:
        _BUILTIN_HANDLERS.append((type_name, fn, {
            "num_args": num_args, "precedence": precedence,
            "check_for_post_traverse": check_for_post_traverse,
        }))
        return fn

    return decorate


def make_spec(type_name: str, handler: OperatorHandler, overrides: dict[str, Any]) -> OperatorSpec:
    base = BASE_SPECS.get(type_name)
    if base is None:
        if overrides["num_args"] is None or overrides["precedence"] is None:
            raise ValueError(f"operator {type_name} needs num_args and precedence")
        return OperatorSpec(type_name, overrides["num_args"], overrides["precedence"], handler,
                            bool(overrides["check_for_post_traverse"]))
    return OperatorSpec(
        type_name,
        base.num_args if overrides["num_args"] is None else overrides["num_args"],
        base.precedence if overrides["precedence"] is None else overrides["precedence"],
        handler,
        base.check_for_post_traverse if overrides["check_for_post_traverse"] is None
        else overrides["check_for_post_traverse"],
    )
