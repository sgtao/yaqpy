"""Shunting-yard conversion to postfix (Go's ``expression_postfix.go``)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyyq.core.lang.ast import Operation
from pyyq.core.lang.prefs import TraversePrefs
from pyyq.core.lang.tokens import Token, TokenKind
from pyyq.errors import ExpressionSyntaxError

_OPENERS = {
    TokenKind.OPEN_COLLECT: "bad expression, could not find matching `]`",
    TokenKind.OPEN_COLLECT_OBJECT: "bad expression, could not find matching `}`",
    TokenKind.OPEN_BRACKET: "bad expression, could not find matching `)`",
}


def _validate_no_open(token: Token, expression: str) -> None:
    message = _OPENERS.get(token.kind)
    if message is not None:
        raise ExpressionSyntaxError(message, expression=expression, position=token.position)


def to_postfix(infix: list[Token], get_spec: Callable[[str], Any],
               expression: str = "") -> list[Operation]:
    result: list[Operation] = []
    op_stack: list[Token] = [Token(TokenKind.OPEN_BRACKET)]
    tokens = [*infix, Token(TokenKind.CLOSE_BRACKET)]

    for current in tokens:
        kind = current.kind
        if kind in (TokenKind.OPEN_BRACKET, TokenKind.OPEN_COLLECT, TokenKind.OPEN_COLLECT_OBJECT):
            op_stack.append(current)
        elif kind in (TokenKind.CLOSE_COLLECT, TokenKind.CLOSE_COLLECT_OBJECT):
            if kind is TokenKind.CLOSE_COLLECT_OBJECT:
                opener = TokenKind.OPEN_COLLECT_OBJECT
                collect_op = "COLLECT_OBJECT"
            else:
                opener = TokenKind.OPEN_COLLECT
                collect_op = "COLLECT"
            while op_stack and op_stack[-1].kind is not opener:
                _validate_no_open(op_stack[-1], expression)
                popped = op_stack.pop()
                assert popped.operation is not None
                result.append(popped.operation)
            if not op_stack:
                raise ExpressionSyntaxError(
                    "bad path expression, got close collect brackets without matching opening bracket",
                    expression=expression, position=current.position,
                )
            op_stack.pop()
            prefs = TraversePrefs(optional_traverse=current.match.endswith("?"))
            result.append(Operation(get_spec(collect_op)))
            if opener is not TokenKind.OPEN_COLLECT:
                result.append(Operation(get_spec("SHORT_PIPE")))
            if (op_stack and op_stack[-1].operation is not None
                    and op_stack[-1].operation.spec.type == "TRAVERSE_ARRAY"):
                popped = op_stack.pop()
                assert popped.operation is not None
                popped.operation.prefs = prefs
                result.append(popped.operation)
        elif kind is TokenKind.CLOSE_BRACKET:
            while op_stack and op_stack[-1].kind is not TokenKind.OPEN_BRACKET:
                _validate_no_open(op_stack[-1], expression)
                popped = op_stack.pop()
                assert popped.operation is not None
                result.append(popped.operation)
            if not op_stack:
                raise ExpressionSyntaxError(
                    "bad expression, got close brackets without matching opening bracket",
                    expression=expression, position=current.position,
                )
            op_stack.pop()
        else:
            assert current.operation is not None
            precedence = current.operation.spec.precedence
            while (op_stack and op_stack[-1].kind is TokenKind.OPERATION
                   and op_stack[-1].operation is not None
                   and op_stack[-1].operation.spec.precedence > precedence):
                popped = op_stack.pop()
                assert popped.operation is not None
                result.append(popped.operation)
            op_stack.append(current)

    if op_stack:
        top = op_stack[-1]
        raise ExpressionSyntaxError(
            f"bad expression - probably missing close bracket on {top!r}",
            expression=expression, position=top.position,
        )
    return result
