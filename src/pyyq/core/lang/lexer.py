"""Tokeniser plus Go's ``postProcessTokens`` (design doc 6-2 / 6-3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyyq.core.lang.ast import Operation
from pyyq.core.lang.lex_rules import DEFAULT_RULESET, LexRuleSet
from pyyq.core.lang.tokens import Token, TokenKind
from pyyq.core.model.node import Node
from pyyq.errors import ExpressionSyntaxError


def tokenize(expression: str, get_spec: Callable[[str], Any],
             ruleset: LexRuleSet = DEFAULT_RULESET) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    n = len(expression)
    while pos < n:
        found = ruleset.match(expression, pos)
        if found is None:
            raise ExpressionSyntaxError(
                f"unexpected character {expression[pos]!r} at position {pos}",
                expression=expression, position=pos,
            )
        rule, m = found
        text = m.group(0)
        if rule.action is not None:
            token = rule.action(text, get_spec)
            token.position = pos
            tokens.append(token)
        pos = m.end()
    return post_process_tokens(tokens, get_spec)


def _value_token(value: Any, text: str, get_spec: Callable[[str], Any]) -> Token:
    op = Operation(get_spec("VALUE"), value=value, string_value=text,
                   node=Node.from_value(value, text))
    return Token(TokenKind.OPERATION, op)


def post_process_tokens(tokens: list[Token], get_spec: Callable[[str], Any]) -> list[Token]:
    """Insert the implicit operators Go adds in ``handleToken``."""
    out: list[Token] = []
    skip_next = False
    for index in range(len(tokens)):
        if skip_next:
            skip_next = False
            continue
        skip_next = _handle_token(tokens, index, out, get_spec)
    return out


def _handle_token(tokens: list[Token], index: int, out: list[Token],
                  get_spec: Callable[[str], Any]) -> bool:
    skip_next = False
    current = tokens[index]
    last = index == len(tokens) - 1

    if current.kind is TokenKind.TRAVERSE_ARRAY_COLLECT:
        # `.[exp]` => SELF TRAVERSE_ARRAY [ exp ]
        out.append(Token(TokenKind.OPERATION, Operation(get_spec("SELF"), string_value="SELF")))
        out.append(Token(TokenKind.OPERATION,
                         Operation(get_spec("TRAVERSE_ARRAY"), string_value="TRAVERSE_ARRAY")))
        current = Token(TokenKind.OPEN_COLLECT, position=current.position)

    if current.is_op("CREATE_MAP"):
        # slice without a start: `.[:2]` or `.a[:2]`
        if index > 0 and tokens[index - 1].kind is TokenKind.TRAVERSE_ARRAY_COLLECT:
            out.append(_value_token(0, "0", get_spec))
        elif (
            index >= 2
            and tokens[index - 1].kind is TokenKind.OPEN_COLLECT
            and tokens[index - 2].kind in (
                TokenKind.OPERATION, TokenKind.CLOSE_COLLECT, TokenKind.CLOSE_COLLECT_OBJECT
            )
        ):
            out.append(_value_token(0, "0", get_spec))

    if (not last and current.assign_operation is not None
            and tokens[index + 1].is_op("ASSIGN")):
        # `tag = "!!str"` -> the getter becomes its assign counterpart
        nxt = tokens[index + 1]
        assert nxt.operation is not None
        current.operation = current.assign_operation
        current.operation.update_assign = nxt.operation.update_assign
        skip_next = True

    out.append(current)

    if current.is_op("CREATE_MAP"):
        # slice without an end: `.[1:]`
        if not last and tokens[index + 1].kind is TokenKind.CLOSE_COLLECT:
            out.append(Token(TokenKind.OPERATION, Operation(get_spec("LENGTH"))))

    if not last and (
        (current.kind is TokenKind.OPEN_COLLECT
         and tokens[index + 1].kind is TokenKind.CLOSE_COLLECT)
        or (current.kind is TokenKind.OPEN_COLLECT_OBJECT
            and tokens[index + 1].kind is TokenKind.CLOSE_COLLECT_OBJECT)
    ):
        out.append(Token(TokenKind.OPERATION, Operation(get_spec("EMPTY"), string_value="EMPTY")))

    if not last and current.check_for_post_traverse and (
        tokens[index + 1].is_op("TRAVERSE_PATH")
        or tokens[index + 1].kind is TokenKind.TRAVERSE_ARRAY_COLLECT
    ):
        out.append(Token(TokenKind.OPERATION,
                         Operation(get_spec("SHORT_PIPE"), value="PIPE", string_value=".")))

    if (not last and current.check_for_post_traverse
            and tokens[index + 1].kind is TokenKind.OPEN_COLLECT):
        out.append(Token(TokenKind.OPERATION, Operation(get_spec("TRAVERSE_ARRAY"))))

    return skip_next
