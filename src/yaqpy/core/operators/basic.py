"""Structural operators: self, pipe, union, value, variables, block, empty."""

from __future__ import annotations

from collections.abc import Mapping

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.helpers import yaml_string
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.lang.prefs import AssignVarPrefs, ExpressionPrefs
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError


@operator("SELF")
def self_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx


@operator("EMPTY")
def empty_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child([])


def _error_message(nav: Navigator, node: Node) -> str:
    if node.tag == "!!null":
        return "null (null)"
    if node.kind is Kind.SCALAR:
        return node.value
    return yaml_string(nav, node)


@operator("ERROR")
@operator("ERROR_BARE", num_args=0, precedence=50)
def error_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    """jq's ``error`` / ``error(msg)`` (yq has neither): raise, ending the whole evaluation.

    ``error(msg)`` raises the (first) result of ``msg``; bare ``error`` raises the current
    input itself (a string as-is, anything else rendered as YAML), matching jq's ``error/0``
    and ``error/1``. Two lexer words (``error(`` vs bare ``error``) share this handler because
    the postfix builder decides argument count from the token's own spec, and one word cannot
    be both 0- and 1-ary at once (see ``core.lang.lex_rules._word_call`` / ``_word_bare``).
    """
    if expr.rhs is None:
        node = ctx.nodes[0] if ctx.nodes else Node(tag="!!null")
        raise EvaluationError(_error_message(nav, node))
    message_ctx = nav.evaluate(ctx.readonly_clone(), expr.rhs)
    node = message_ctx.nodes[0] if message_ctx.nodes else Node(tag="!!null")
    raise EvaluationError(_error_message(nav, node))


@operator("BLOCK")
def block_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child([])


@operator("VALUE")
def value_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    literal = expr.operation.node
    assert literal is not None
    if not ctx.nodes:
        return ctx.single_child(literal.copy())
    return ctx.child(literal.copy() for _ in ctx.nodes)


@operator("STRING_INT")
def string_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    # String interpolation `\(exp)` is phase 2; behave like a plain literal.
    return value_operator(nav, ctx, expr)


@operator("REF")
def reference_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    assert expr.operation.node is not None
    return ctx.single_child(expr.operation.node)


@operator("PIPE")
def pipe_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    assert expr.lhs is not None
    if expr.lhs.operation.spec.type == "ASSIGN_VARIABLE":
        return variable_loop(nav, ctx, expr)
    lhs = nav.evaluate(ctx, expr.lhs)
    rhs = nav.evaluate(ctx.child(lhs.nodes), expr.rhs)
    return ctx.child(rhs.nodes)


@operator("SHORT_PIPE")
def short_pipe_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return pipe_operator(nav, ctx, expr)


@operator("UNION")
def union_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    lhs = nav.evaluate(ctx, expr.lhs)
    rhs = nav.evaluate(ctx, expr.rhs)
    results = list(lhs.nodes)
    if rhs.nodes is not lhs.nodes:
        results.extend(rhs.nodes)
    return lhs.child(results)


def _environ_node(environ: Mapping[str, str]) -> Node:
    node = Node.mapping()
    for key, value in environ.items():
        node.add_key_value(Node.string(key), Node.string(value))
    return node


@operator("GET_VARIABLE")
def get_variable_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    name = expr.operation.string_value
    result = ctx.get_variable(name)
    if result is None and name == "ENV":
        # `$ENV` / bare `env` (E3/E5, 0926-03 3-6): built here, not pre-seeded into every
        # root Context, so it stays live if `os.environ` changes between calls and so a
        # user's own `... as $ENV | ...` (bound above, in ctx.variables) still shadows it.
        if not nav.env.security.allow_env:
            return ctx.child([])
        return ctx.child([_environ_node(nav.env.environ)])
    # list(...) forces a fresh tuple so union's identity check does not collapse `$x, $x`
    return ctx.child(list(result or ()))


@operator("ASSIGN_VARIABLE")
def assign_variable_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    raise EvaluationError("must use variable with a pipe, e.g. `exp as $x | ...`")


def variable_loop(nav: Navigator, ctx: Context, original: ExprNode) -> Context:
    if ctx.evaluate_all_together():
        return _variable_loop_single(nav, ctx, original)
    results: list[Node] = []
    for node in ctx.nodes:
        results.extend(_variable_loop_single(nav, ctx.single_child(node), original).nodes)
    return ctx.child(results)


def _variable_loop_single(nav: Navigator, ctx: Context, original: ExprNode) -> Context:
    variable_exp = original.lhs
    assert variable_exp is not None
    lhs = nav.evaluate(ctx.readonly_clone(), variable_exp.lhs)
    if variable_exp.rhs is None or variable_exp.rhs.operation.spec.type != "GET_VARIABLE":
        raise EvaluationError("RHS of 'as' operator must be a variable name e.g. $foo")
    name = variable_exp.rhs.operation.string_value
    prefs = variable_exp.operation.prefs
    is_reference = isinstance(prefs, AssignVarPrefs) and prefs.is_reference
    results: list[Node] = []
    for node in lhs.nodes:
        value = (node,) if is_reference else (node.copy(),)
        new_ctx = ctx.child(ctx.nodes).with_variable(name, value)
        rhs = nav.evaluate(new_ctx, original.rhs)
        results.extend(rhs.nodes)
    if not lhs.nodes:
        return nav.evaluate(ctx, original.rhs)
    return ctx.child(results)


@operator("EXP")
def expression_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    assert isinstance(prefs, ExpressionPrefs)
    from yaqpy.core.lang.parser import parse_expression

    tree = parse_expression(prefs.expression, nav.env.operators.get)
    return nav.evaluate(ctx, tree)
