"""Builtin operators. Importing this package registers every handler."""

from __future__ import annotations

import threading

from yaqpy.core.operators import (  # noqa: F401  (imported for the @operator side effects)
    anchors, arithmetic, assign, basic, collections, logic, meta, multiply, schema, sequences,
    structure, traverse,
)
from yaqpy.core.operators.registry import _BUILTIN_HANDLERS, OperatorRegistry, make_spec, operator

_lock = threading.Lock()
_builtin: OperatorRegistry | None = None


def builtin_registry() -> OperatorRegistry:
    """Return the (frozen, shared) registry of builtin operators.

    Call ``.copy()`` on it to add your own operators (design doc 13-3)."""
    global _builtin
    if _builtin is None:
        with _lock:
            if _builtin is None:
                reg = OperatorRegistry()
                for type_name, handler, overrides in _BUILTIN_HANDLERS:
                    reg.register(make_spec(type_name, handler, overrides))
                _builtin = reg.freeze()
    return _builtin


__all__ = ["OperatorRegistry", "builtin_registry", "operator"]
