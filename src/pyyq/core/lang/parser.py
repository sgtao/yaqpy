"""Tree building and the public ``compile`` entry point (design doc 6-5)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from pyyq.core.lang.ast import ExprNode, Operation
from pyyq.core.lang.lex_rules import DEFAULT_RULESET, LexRuleSet
from pyyq.core.lang.lexer import tokenize
from pyyq.core.lang.postfix import to_postfix
from pyyq.errors import ExpressionSyntaxError


def build_tree(postfix: list[Operation], expression: str = "") -> ExprNode | None:
    if not postfix:
        return None
    stack: list[ExprNode] = []
    for operation in postfix:
        node = ExprNode(operation)
        num_args = operation.spec.num_args
        if num_args == 1:
            if not stack:
                if operation.spec.type == "FIRST":
                    stack.append(node)
                    continue
                raise ExpressionSyntaxError(
                    f"'{operation.string_value.strip()}' expects 1 arg but received none",
                    expression=expression, position=operation.position,
                )
            node.rhs = stack.pop()
        elif num_args == 2:
            if len(stack) < 2:
                raise ExpressionSyntaxError(
                    f"'{operation.string_value.strip()}' expects 2 args but there is {len(stack)}",
                    expression=expression, position=operation.position,
                )
            node.rhs = stack.pop()
            node.lhs = stack.pop()
        stack.append(node)
    if len(stack) != 1:
        raise ExpressionSyntaxError("bad expression, please check expression syntax",
                                    expression=expression)
    return stack[0]


def parse_expression(expression: str, get_spec: Callable[[str], Any],
                     ruleset: LexRuleSet = DEFAULT_RULESET) -> ExprNode | None:
    tokens = tokenize(expression, get_spec, ruleset)
    postfix = to_postfix(tokens, get_spec, expression)
    return build_tree(postfix, expression)


class Expression:
    """A compiled expression. Immutable; safe to share between threads."""

    __slots__ = ("source", "root", "_registry_id")

    def __init__(self, source: str, root: ExprNode | None, registry_id: int) -> None:
        self.source = source
        self.root = root
        self._registry_id = registry_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Expression({self.source!r})"


class ExpressionCompiler:
    """Caches compiled expressions per (registry, ruleset)."""

    def __init__(self, get_spec: Callable[[str], Any], ruleset: LexRuleSet = DEFAULT_RULESET,
                 *, cache_size: int = 256) -> None:
        self._get_spec = get_spec
        self._ruleset = ruleset
        self._cached = functools.lru_cache(maxsize=cache_size)(self._compile_uncached)

    def _compile_uncached(self, expression: str) -> Expression:
        root = parse_expression(expression, self._get_spec, self._ruleset)
        return Expression(expression, root, id(self))

    def compile(self, expression: str) -> Expression:
        return self._cached(expression)
