"""Node metadata operators: tag, style, comments, document/file index, parent, env, test."""

from __future__ import annotations

import re

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.lang.prefs import CommentPrefs, EnvPrefs, ParentPrefs
from yaqpy.core.model.leading import render_leading_content
from yaqpy.core.model.node import Kind, Node, Style, parse_style, style_name
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError, SecurityError


def _first_value(ctx: Context) -> str | None:
    return ctx.nodes[0].value if ctx.nodes else None


# ----------------------------------------------------------------------------- tag

@operator("GET_TAG")
def get_tag_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.create_replacement(Kind.SCALAR, "!!str", n.tag) for n in ctx.nodes)


@operator("ASSIGN_TAG")
def assign_tag_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    tag = ""
    if not expr.operation.update_assign:
        tag = _first_value(nav.evaluate(ctx.readonly_clone(), expr.rhs)) or ""
    lhs = nav.evaluate(ctx, expr.lhs)
    for candidate in lhs.nodes:
        if expr.operation.update_assign:
            value = _first_value(nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs))
            if value is not None:
                tag = value
        candidate.tag = tag
    return ctx


@operator("GET_KIND")
def get_kind_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.create_replacement(Kind.SCALAR, "!!str", n.kind.value) for n in ctx.nodes)


# ----------------------------------------------------------------------------- style

@operator("GET_STYLE")
def get_style_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(
        n.create_replacement(Kind.SCALAR, "!!str", style_name(n.style)) for n in ctx.nodes)


@operator("ASSIGN_STYLE")
def assign_style_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    style = Style.NONE
    if not expr.operation.update_assign:
        value = _first_value(nav.evaluate(ctx.readonly_clone(), expr.rhs))
        if value is not None:
            style = parse_style(value)
    lhs = nav.evaluate(ctx, expr.lhs)
    for candidate in lhs.nodes:
        if expr.operation.update_assign:
            value = _first_value(nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs))
            if value is not None:
                style = parse_style(value)
        candidate.style = style
    return ctx


# ----------------------------------------------------------------------------- comments

_START_COMMENT = re.compile(r"^# ")
_SUBSEQUENT_COMMENT = re.compile(r"\n# ")


@operator("ASSIGN_COMMENT")
def assign_comments_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    lhs = nav.evaluate(ctx, expr.lhs)
    prefs = expr.operation.prefs
    assert isinstance(prefs, CommentPrefs)
    comment = ""
    if not expr.operation.update_assign:
        comment = _first_value(nav.evaluate(ctx.readonly_clone(), expr.rhs)) or ""
    for candidate in lhs.nodes:
        if expr.operation.update_assign:
            value = _first_value(nav.evaluate(ctx.single_readonly_child(candidate), expr.rhs))
            if value is not None:
                comment = value
        if prefs.line_comment:
            candidate.line_comment = comment
        if prefs.head_comment:
            candidate.head_comment = comment
            candidate.leading_content = ""
        if prefs.foot_comment:
            candidate.foot_comment = comment
    return ctx


def leading_content_as_comment(content: str) -> str:
    """Render leading content the way the YAML encoder would, minus the trailing newline."""
    text = render_leading_content(content, print_doc_separators=False)
    return text[:-1] if text.endswith("\n") else text


@operator("GET_COMMENT")
def get_comments_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    assert isinstance(prefs, CommentPrefs)
    results: list[Node] = []
    for candidate in ctx.nodes:
        comment = ""
        if prefs.line_comment:
            comment = candidate.line_comment
        elif prefs.head_comment and candidate.leading_content != "":
            comment = leading_content_as_comment(candidate.leading_content)
        elif prefs.head_comment:
            comment = candidate.head_comment
        elif prefs.foot_comment:
            comment = candidate.foot_comment
        comment = _START_COMMENT.sub("", comment)
        comment = _SUBSEQUENT_COMMENT.sub("\n", comment)
        result = candidate.create_replacement(Kind.SCALAR, "!!str", comment)
        if candidate.is_map_key:
            result.is_map_key = False
            result.key = candidate
        results.append(result)
    return ctx.child(results)


# ----------------------------------------------------------------------------- document / file

@operator("GET_DOCUMENT_INDEX")
def get_document_index_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(
        n.create_replacement(Kind.SCALAR, "!!int", str(n.document())) for n in ctx.nodes)


@operator("GET_FILENAME")
def get_filename_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(
        n.create_replacement(Kind.SCALAR, "!!str", n.get_filename()) for n in ctx.nodes)


@operator("GET_FILE_INDEX")
def get_file_index_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(
        n.create_replacement(Kind.SCALAR, "!!int", str(n.get_file_index())) for n in ctx.nodes)


@operator("LINE")
def line_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.create_replacement(Kind.SCALAR, "!!int", str(n.line)) for n in ctx.nodes)


@operator("COLUMN")
def column_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    return ctx.child(n.create_replacement(Kind.SCALAR, "!!int", str(n.column)) for n in ctx.nodes)


# ----------------------------------------------------------------------------- parent

@operator("GET_PARENT")
def get_parent_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    level = prefs.level if isinstance(prefs, ParentPrefs) else 1
    results: list[Node] = []
    for candidate in ctx.nodes:
        levels = level
        if level < 0:
            total = 0
            temp = candidate.parent
            while temp is not None:
                total += 1
                temp = temp.parent
            levels = max(total + level + 1, 0)
        node: Node | None = candidate
        current = 0
        while current < levels and node is not None:
            node = node.parent
            current += 1
        if node is not None:
            results.append(node)
    return ctx.child(results)


@operator("GET_PARENTS")
def get_parents_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        parents = Node.sequence()
        parent = candidate.parent
        while parent is not None:
            parents.add_child(parent)
            parent = parent.parent
        results.append(parents)
    return ctx.child(results)


# ----------------------------------------------------------------------------- env

@operator("ENV")
def env_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    if not nav.env.security.allow_env:
        raise SecurityError("env operations have been disabled", capability="env")
    assert expr.operation.node is not None
    name = expr.operation.node.value
    raw = nav.env.environ.get(name, "")
    prefs = expr.operation.prefs
    if isinstance(prefs, EnvPrefs) and prefs.string_value:
        node = Node.string(raw)
    elif raw == "":
        raise EvaluationError(f"value for env variable '{name}' not provided in env()")
    else:
        if nav.env.yaml_snippet_decoder is None:
            raise EvaluationError("env(): no YAML decoder available")
        node = nav.env.yaml_snippet_decoder(raw)
    return ctx.single_child(node)
