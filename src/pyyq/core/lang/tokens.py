"""Tokens produced by the lexer (Go's ``token``)."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from pyyq.core.lang.ast import Operation


class TokenKind(enum.Enum):
    OPERATION = "op"
    OPEN_BRACKET = "("
    CLOSE_BRACKET = ")"
    OPEN_COLLECT = "["
    CLOSE_COLLECT = "]"
    OPEN_COLLECT_OBJECT = "{"
    CLOSE_COLLECT_OBJECT = "}"
    TRAVERSE_ARRAY_COLLECT = ".["


@dataclass(slots=True)
class Token:
    kind: TokenKind
    operation: Operation | None = None
    assign_operation: Operation | None = None
    check_for_post_traverse: bool = False
    match: str = ""
    position: int = -1

    def is_op(self, type_name: str) -> bool:
        return (
            self.kind is TokenKind.OPERATION
            and self.operation is not None
            and self.operation.spec.type == type_name
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.kind is TokenKind.OPERATION:
            return repr(self.operation)
        return self.kind.value
