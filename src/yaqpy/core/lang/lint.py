"""Static warnings for likely-mistaken expressions (E7, 0926-03 5-5).

Pure tree inspection - no dependency on ``core.engine`` - so it runs once at compile time and
its result is cached on ``Expression`` alongside the tree itself (``core.lang.parser``).

Y006/Y007/Y008 (mixing `,`/`|`/`and`/`or` without parentheses, where yq's precedence groups
them differently from jq's) are not implemented here: telling "no parens were written" from a
tree that has already been built with *yq's* precedence would need a side-by-side comparison
against jq's own precedence table, which does not exist yet - that is v0.9's dialect groundwork
(the plan's 5-2 dialect setup and 5-4 P1). R001/R002 (division by zero; array/object `==`) are
runtime, not static, and are raised by the operators themselves (arithmetic.py, logic.py) into
``EvalEnv.lint_warnings`` - see ``core.engine.context.EvalEnv``.
"""

from __future__ import annotations

from yaqpy.core.lang.ast import ExprNode

_LITERAL_TYPES = frozenset({"VALUE", "STRING_INT"})
_LITERAL_CONTAINER_TYPES = frozenset({"COLLECT", "COLLECT_OBJECT"})
_PIPE_TYPES = ("PIPE", "SHORT_PIPE")
# Equal-precedence tiers (0926-03 決定 5 / E9): a node of one of these types whose own lhs/rhs
# is also one of the same tier is a chain whose left-to-right order changed in v0.8.0.
_ARITHMETIC_TIERS: dict[str, frozenset[str]] = {
    "ADD": frozenset({"ADD", "SUBTRACT"}),
    "SUBTRACT": frozenset({"ADD", "SUBTRACT"}),
    "MULTIPLY": frozenset({"MULTIPLY", "DIVIDE", "MODULO"}),
    "DIVIDE": frozenset({"MULTIPLY", "DIVIDE", "MODULO"}),
    "MODULO": frozenset({"MULTIPLY", "DIVIDE", "MODULO"}),
}

Y001 = ("Y001: '... | select(cond) | <定数>' は、条件が偽でも定数が出ます。"
       "代入で書くと防げます: '(EXPR | select(cond)) = <値>'")
Y002 = ("Y002: 文字列リテラルの中の '*' は、'==' '!=' ではワイルドカードとして扱われます "
       "(そのままの文字として比べたいなら、比較の意図を確かめてください)")
Y003 = "Y003: 配列・オブジェクトのリテラルとの '==' '!=' は、常に偽になります"
Y005 = ("Y005: 'pick' の引数は配列にしてください (例: pick([\"a\"]))。"
       "配列でないと、黙って {} になります")
Y009 = ("Y009 (v0.8.x の間だけ): 括弧なしの連続した算術は、v0.8.0 から計算の順序が変わりました "
       "(左から、'* / %' が '+ -' より先。前の版と結果が違うことがあります)")


def _op_type(node: ExprNode | None) -> str | None:
    return None if node is None else node.operation.spec.type


def _is_literal(node: ExprNode | None) -> bool:
    return _op_type(node) in _LITERAL_TYPES


def _is_wildcard_string(node: ExprNode | None) -> bool:
    return (_op_type(node) == "STRING_INT"
            and "*" in node.operation.string_value)     # type: ignore[union-attr]


def _tail_type(node: ExprNode | None) -> str | None:
    """The type of the last operator in a pipe chain (``a | b | select(...)`` -> "SELECT")."""
    while node is not None and node.operation.spec.type in _PIPE_TYPES:
        node = node.rhs
    return _op_type(node)


def _is_literal_container(node: ExprNode | None) -> bool:
    # `[1]` is a bare COLLECT node; `{"a": 1}` is SHORT_PIPE(CREATE_MAP, COLLECT_OBJECT) - both
    # end (`_tail_type`) at the COLLECT/COLLECT_OBJECT that actually builds the value.
    return _tail_type(node) in _LITERAL_CONTAINER_TYPES


def _bound_name(assign_variable: ExprNode) -> str | None:
    """``EXPR as $x`` (or REDUCE's ``S as $x``): the name bound by an ASSIGN_VARIABLE node."""
    if assign_variable.rhs is not None and assign_variable.rhs.operation.spec.type == "GET_VARIABLE":
        return assign_variable.rhs.operation.string_value
    return None


def _walk(node: ExprNode | None, bound: frozenset[str], out: list[str]) -> None:
    if node is None:
        return
    op_type = node.operation.spec.type

    if op_type in _PIPE_TYPES and node.lhs is not None and node.lhs.operation.spec.type == "ASSIGN_VARIABLE":
        # `EXPR as $x | BODY`: $x is bound only inside BODY, not EXPR itself.
        assign_variable = node.lhs
        _walk(assign_variable.lhs, bound, out)
        name = _bound_name(assign_variable)
        _walk(node.rhs, (bound | {name}) if name else bound, out)
        return

    if op_type == "REDUCE" and node.lhs is not None and node.rhs is not None:
        # `S as $x ireduce (init; upd)`: $x is bound only inside upd, not S or init.
        assign_variable = node.lhs
        _walk(assign_variable.lhs, bound, out)
        _walk(node.rhs.lhs, bound, out)
        name = _bound_name(assign_variable)
        _walk(node.rhs.rhs, (bound | {name}) if name else bound, out)
        return

    if op_type in _PIPE_TYPES:
        if _is_literal(node.rhs) and _tail_type(node.lhs) == "SELECT":
            out.append(Y001)
    elif op_type in ("EQUALS", "NOT_EQUALS"):
        if _is_wildcard_string(node.lhs) or _is_wildcard_string(node.rhs):
            out.append(Y002)
        if _is_literal_container(node.lhs) or _is_literal_container(node.rhs):
            out.append(Y003)
    elif op_type == "GET_VARIABLE":
        name = node.operation.string_value
        if name not in bound and name != "ENV":
            out.append(f"Y004: 束縛されていない変数 '${name}' は、黙って空になります")
    elif op_type == "PICK":
        if node.rhs is not None and node.rhs.operation.spec.type != "COLLECT":
            out.append(Y005)
    elif op_type in _ARITHMETIC_TIERS:
        tier = _ARITHMETIC_TIERS[op_type]
        if _op_type(node.lhs) in tier or _op_type(node.rhs) in tier:
            out.append(Y009)

    _walk(node.lhs, bound, out)
    _walk(node.rhs, bound, out)


def lint_expression(root: ExprNode | None) -> tuple[str, ...]:
    """Every warning that applies to ``root``, each at most once, in the order first found."""
    found: list[str] = []
    _walk(root, frozenset(), found)
    seen: set[str] = set()
    unique: list[str] = []
    for message in found:
        if message not in seen:
            seen.add(message)
            unique.append(message)
    return tuple(unique)
