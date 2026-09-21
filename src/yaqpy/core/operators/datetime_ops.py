"""Date-time operators: now, tz, from_unix, to_unix, format_datetime, with_dtf
(Go's ``operator_datetime.go``). The layouts are Go's; see ``core/model/datetime_util.py``."""

from __future__ import annotations

import datetime as _dt
import zoneinfo

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.model.datetime_util import (
    RFC3339, format_datetime, parse_datetime, unix_seconds,
)
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError


def _string_parameter(name: str, nav: Navigator, ctx: Context, expr: ExprNode | None) -> str:
    found = nav.evaluate(ctx.readonly_clone(), expr)
    if not found.nodes:
        raise EvaluationError(f"could not find {name} for format_time")
    return found.nodes[0].value


def _parse(node: Node, layout: str, *, with_layout: bool) -> _dt.datetime:
    try:
        return parse_datetime(layout, node.value)
    except ValueError as e:
        where = f"could not parse datetime of [{node.nice_path()}]"
        if with_layout:
            where += f" using layout [{layout}]"
        raise EvaluationError(f"{where}: {e}") from None


# ----------------------------------------------------------------------------- with_dtf

@operator("WITH_DATE_TIME_FORMAT")
def with_datetime_format_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    block = expr.rhs
    if block is None or block.operation.spec.type not in ("BLOCK", "UNION"):
        raise EvaluationError('must provide a date time format string and an expression, e.g. '
                              'with_dtf("Monday, 02-Jan-06 at 3:04PM MST"; <exp>)')
    try:
        layout = _string_parameter("layout", nav, ctx, block.lhs)
    except EvaluationError as e:
        raise EvaluationError(f"could not get date time format: {e}") from None
    return nav.evaluate(ctx.with_datetime_layout(layout), block.rhs)


# ----------------------------------------------------------------------------- now / unix

@operator("NOW")
def now_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    moment = nav.env.clock()
    return ctx.single_child(Node.scalar(format_datetime(moment, RFC3339), "!!timestamp"))


def _local_zone() -> _dt.tzinfo:
    return _dt.datetime.now().astimezone().tzinfo or _dt.timezone.utc


@operator("FROM_UNIX")
def from_unix_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    results: list[Node] = []
    for candidate in ctx.nodes:
        if candidate.guess_tag() not in ("!!int", "!!float"):
            raise EvaluationError(
                f"from_unix only works on numbers, found {candidate.tag} instead")
        try:
            seconds = float(candidate.value)
        except ValueError:
            raise EvaluationError(
                f'strconv.ParseFloat: parsing "{candidate.value}": invalid syntax') from None
        try:
            moment = _dt.datetime.fromtimestamp(int(seconds * 1000) / 1000, tz=_local_zone())
        except (OverflowError, OSError, ValueError):
            raise EvaluationError(f"unix time {candidate.value} is out of range") from None
        results.append(candidate.create_replacement(
            Kind.SCALAR, "!!timestamp", format_datetime(moment, RFC3339)))
    return ctx.child(results)


@operator("TO_UNIX")
def to_unix_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    layout = ctx.get_datetime_layout()
    return ctx.child(
        candidate.create_replacement(
            Kind.SCALAR, "!!int", str(unix_seconds(_parse(candidate, layout, with_layout=True))))
        for candidate in ctx.nodes)


# ----------------------------------------------------------------------------- format / tz

@operator("FORMAT_DATE_TIME")
def format_datetime_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    layout = ctx.get_datetime_layout()
    target = _string_parameter("format", nav, ctx, expr.rhs)
    results: list[Node] = []
    for candidate in ctx.nodes:
        text = format_datetime(_parse(candidate, layout, with_layout=False), target)
        node = _scalar_from_text(nav, text)
        node.parent = candidate.parent
        node.key = candidate.key
        results.append(node)
    return ctx.child(results)


def _scalar_from_text(nav: Navigator, text: str) -> Node:
    """Go's ``parseSnippet``: read the text as a YAML scalar (so ``2001-12-15`` is a timestamp
    and ``12`` an int), and keep it a string when it is anything else."""
    if text == "":
        return Node.null(value="")
    decoder = nav.env.yaml_snippet_decoder
    if decoder is not None:
        try:
            node = decoder(text)
        except Exception:  # noqa: BLE001 - any parse failure means "leave it as a string"
            node = None
        if node is not None and node.kind is Kind.SCALAR:
            return node
    return Node.string(text)


def load_zone(name: str) -> _dt.tzinfo:
    """Go's ``time.LoadLocation``: ``""`` and ``UTC`` are UTC, ``Local`` is this machine's zone,
    anything else is an IANA name (which needs the platform's time zone data)."""
    if name in ("", "UTC"):
        return _dt.timezone.utc
    if name == "Local":
        return _local_zone()
    try:
        return zoneinfo.ZoneInfo(name)
    except zoneinfo.ZoneInfoNotFoundError:
        hint = ""
        if not zoneinfo.TZPATH:
            hint = " (this system has no time zone database; on Windows install the tzdata package)"
        raise EvaluationError(f"unknown time zone {name}{hint}") from None
    except (ValueError, OSError):
        raise EvaluationError(f"unknown time zone {name}") from None


@operator("TIMEZONE")
def timezone_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    name = _string_parameter("timezone", nav, ctx, expr.rhs)
    layout = ctx.get_datetime_layout()
    try:
        zone = load_zone(name)
    except EvaluationError as e:
        raise EvaluationError(f"could not load tz [{name}]: {e}") from None
    results: list[Node] = []
    for candidate in ctx.nodes:
        moment = _parse(candidate, layout, with_layout=True).astimezone(zone)
        results.append(candidate.create_replacement(
            Kind.SCALAR, candidate.tag, format_datetime(moment, layout)))
    return ctx.child(results)
