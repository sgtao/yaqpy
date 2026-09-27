"""Lint warnings, static and runtime (E7, 0926-03 5-5): Y001-Y009 and R001/R002.

``lint_expression`` is tested directly against the parsed tree (fast, no engine); the
on/off default and the runtime (R001/R002) checks are tested through ``YqService``, since
the top-level ``yaqpy.evaluate()`` returns only the output text, not ``EvaluateResult``.
"""

from __future__ import annotations

from yaqpy.app.dto import EvaluateRequest, InputSource
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService
from yaqpy.core.lang.lint import lint_expression
from yaqpy.core.lang.parser import parse_expression
from yaqpy.core.operators import builtin_registry
from yaqpy.options import Options

REG = builtin_registry()


def lint(expression: str) -> tuple[str, ...]:
    root = parse_expression(expression, REG.get)
    return lint_expression(root)


def warnings_for(expression: str, text: str = "1\n", *, lint_mode: str = "warn") -> tuple[str, ...]:
    service = YqService(InMemoryFileSystem(), StaticEnvironment({}))
    request = EvaluateRequest(expression=expression, inputs=(InputSource("<text>", text),),
                              options=Options(lint=lint_mode))
    result = service.evaluate(request, MemorySink())
    return result.warnings


class StaticLintTests:
    def test_y001_select_then_constant(self) -> None:
        assert any(w.startswith("Y001") for w in lint('.a | select(. == 1) | "y"'))
        assert not lint('.a | select(. == 1) | .b')     # not a constant: no warning

    def test_y001_fires_at_whichever_pipe_ends_in_a_constant(self) -> None:
        # A later, unrelated pipe stage in the same expression is checked independently.
        assert any(w.startswith("Y001") for w in lint('.a | (select(. == 1) | "y"), .b'))

    def test_y002_wildcard_string_literal(self) -> None:
        assert any(w.startswith("Y002") for w in lint('.a == "x*"'))
        assert not lint('.a == "x"')

    def test_y003_array_or_object_literal(self) -> None:
        assert any(w.startswith("Y003") for w in lint(".a == [1]"))
        assert any(w.startswith("Y003") for w in lint('.a == {"b": 1}'))
        assert not lint(".a == 1")

    def test_y004_unbound_variable(self) -> None:
        assert any(w.startswith("Y004") for w in lint("$nope"))

    def test_y004_bound_by_as_is_not_flagged(self) -> None:
        assert not lint(". as $x | $x")

    def test_y004_bound_only_inside_the_body_not_before_as(self) -> None:
        # $x used on the *source* side of "as" is unbound there, regardless of a later binding.
        assert any(w.startswith("Y004") for w in lint("$x as $y | 1"))

    def test_y004_env_is_never_flagged(self) -> None:
        assert not lint("$ENV")

    def test_y004_bound_by_ireduce(self) -> None:
        assert not lint(".[] as $i ireduce (0; . + $i)")

    def test_y005_pick_with_a_non_array_argument(self) -> None:
        assert any(w.startswith("Y005") for w in lint("pick(.a)"))
        assert not lint('pick(["a"])')

    def test_y006_comma_and_pipe_mixed_without_parens(self) -> None:
        # 0926-02 6-1's own example: yq groups `.b[0], (.b[1] | . * 10)`; jq groups the comma
        # first. Confirmed by printing the actual tree, not assumed.
        assert any(w.startswith("Y006") for w in lint(".b[0], .b[1] | . * 10"))
        assert any(w.startswith("Y006") for w in lint(".a | .c, .b"))
        assert not lint(".a, .b")
        assert not lint("(.a, .b) | .c")     # explicit parens: UNION is not a PIPE's child

    def test_y007_pipe_then_bare_and_or(self) -> None:
        # yq groups `(.a | . > 0) and (. < 5)`; jq groups the whole `and` inside the pipe.
        assert any(w.startswith("Y007") for w in lint(".a | . > 0 and . < 5"))
        assert not lint(".a | (. > 0 and . < 5)")

    def test_y008_and_or_mixed_without_parens(self) -> None:
        assert any(w.startswith("Y008") for w in lint("false and false or true"))
        assert not lint("false and true")

    def test_y008_false_positive_on_an_explicitly_parenthesized_expression(self) -> None:
        # Documented limitation (lint.py's own module docstring): parens leave no trace once
        # the tree is built, so a deliberately-grouped `(A and B) or C` looks exactly like the
        # unparenthesized version that needed the warning. Harmless (explicit parens keep
        # their grouping in either dialect), but not distinguishable here.
        assert any(w.startswith("Y008") for w in lint("(false and false) or true"))

    def test_y009_chained_arithmetic_of_the_same_tier(self) -> None:
        assert any(w.startswith("Y009") for w in lint("1 - 2 - 3"))
        assert any(w.startswith("Y009") for w in lint("1 * 2 / 3"))
        assert not lint("1 - 2")
        assert not lint("1 + 2 * 3")     # different tiers: order was never ambiguous

    def test_no_warnings_for_an_ordinary_expression(self) -> None:
        assert lint(".a.b | select(.c > 1)") == ()

    def test_warnings_are_deduplicated(self) -> None:
        assert lint('(.a == "x*") and (.b == "y*")').count(
            next(w for w in lint('.a == "x*"') if w.startswith("Y002"))) == 1


class LintWiringTests:
    def test_library_default_is_off(self) -> None:
        assert warnings_for('select(. == 2) | "y"', lint_mode="off") == ()

    def test_warn_mode_surfaces_static_and_runtime_findings(self) -> None:
        warnings = warnings_for('select(. == 2) | "y"')
        assert any(w.startswith("Y001") for w in warnings)

    def test_division_by_zero_is_r001(self) -> None:
        warnings = warnings_for("1 / 0")
        assert any(w.startswith("R001") for w in warnings)

    def test_array_equals_is_r002_even_without_a_literal(self) -> None:
        warnings = warnings_for(".a == .a", text="a: [1]\n")
        assert any(w.startswith("R002") for w in warnings)

    def test_r001_is_not_repeated_per_loop_iteration(self) -> None:
        warnings = warnings_for("[.[] | (1 / 0)]", text="[1, 2, 3]\n")
        assert sum(w.startswith("R001") for w in warnings) == 1
