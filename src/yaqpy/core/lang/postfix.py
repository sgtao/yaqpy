"""Shunting-yard conversion to postfix (Go's ``expression_postfix.go``)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yaqpy.core.lang.ast import Operation
from yaqpy.core.lang.prefs import TraversePrefs
from yaqpy.core.lang.tokens import Token, TokenKind
from yaqpy.errors import ExpressionSyntaxError

_OPENERS = {
    TokenKind.OPEN_COLLECT: "bad expression, could not find matching `]`",
    TokenKind.OPEN_COLLECT_OBJECT: "bad expression, could not find matching `}`",
    TokenKind.OPEN_BRACKET: "bad expression, could not find matching `)`",
}


def _validate_no_open(token: Token, expression: str) -> None:
    message = _OPENERS.get(token.kind)
    if message is not None:
        raise ExpressionSyntaxError(message, expression=expression, position=token.position)


_OPENER_KINDS = (
    TokenKind.OPEN_BRACKET, TokenKind.OPEN_COLLECT, TokenKind.OPEN_COLLECT_OBJECT,
    TokenKind.TRAVERSE_ARRAY_COLLECT,
)


def _expects_operand(previous: Token | None) -> bool:
    """Is a value expected next (so a following ``-`` is unary), or does ``previous``
    already stand as one on its own (so ``-`` is the binary subtract)?

    E5 (0926-03 3-2 単項 `-`): the lexer has one token for ``-`` (``Subtract``) since Go
    yq's grammar never needed a unary minus; this is the "unary の判定" the plan puts in
    ``postfix.py`` - every other operator's arity already says whether it is still waiting
    for an operand (``num_args >= 1``) or is already a complete value (``num_args == 0``,
    e.g. ``.a``, a literal, ``$x``), so no separate lookup table is needed.
    """
    if previous is None or previous.kind in _OPENER_KINDS:
        return True
    if previous.kind is TokenKind.OPERATION and previous.operation is not None:
        return previous.operation.spec.num_args >= 1
    return False


def _as_negate(token: Token, get_spec: Callable[[str], Any]) -> Token:
    assert token.operation is not None
    op = Operation(get_spec("NEGATE"), string_value=token.operation.string_value)
    return Token(TokenKind.OPERATION, op, position=token.position)


def to_postfix(infix: list[Token], get_spec: Callable[[str], Any],
               expression: str = "") -> list[Operation]:
    result: list[Operation] = []
    op_stack: list[Token] = [Token(TokenKind.OPEN_BRACKET)]
    tokens = [*infix, Token(TokenKind.CLOSE_BRACKET)]
    previous: Token | None = None

    for current in tokens:
        if (current.kind is TokenKind.OPERATION and current.operation is not None
                and current.operation.spec.type == "SUBTRACT" and _expects_operand(previous)):
            current = _as_negate(current, get_spec)
        previous = current
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
            spec = current.operation.spec
            precedence = spec.precedence
            # Equal precedence keeps the old (right-associative) reading unless the incoming
            # operator is one of the few marked left-associative (0926-03 決定 5 / E9): then an
            # equal-precedence run on the stack is popped too, so `1 - 2 - 3` groups left to
            # right (`-4`) instead of right to left (`2`).
            pop_equal = spec.left_assoc
            while (op_stack and op_stack[-1].kind is TokenKind.OPERATION
                   and op_stack[-1].operation is not None
                   and (op_stack[-1].operation.spec.precedence > precedence
                        or (pop_equal and op_stack[-1].operation.spec.precedence == precedence))):
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
