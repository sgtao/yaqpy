"""jq に寄せて v0.8.0 で足した書き方（改修計画 21_docs/0926-03 の 6-1 節）。

既定（yq 方言）のままで動くようにしたものだけをここに置く。既存の演算子の挙動は変えない。
"""

from __future__ import annotations

import pytest
import yaqpy
from yaqpy import EvaluationError, ExpressionSyntaxError


class ErrorTests:
    def test_error_with_a_message_raises_it(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            yaqpy.query('error("boom")', 1)
        assert str(raised.value) == "boom"

    def test_bare_error_raises_the_input_as_a_string(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            yaqpy.query("error", "boom")
        assert str(raised.value) == "boom"

    def test_bare_error_renders_a_non_string_input_as_yaml(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            yaqpy.query("error", {"a": 1})
        assert str(raised.value) == "a: 1"

    def test_error_on_null_input(self) -> None:
        with pytest.raises(EvaluationError) as raised:
            yaqpy.query("error", None)
        assert str(raised.value) == "null (null)"

    def test_select_or_error_is_the_documented_pattern(self) -> None:
        # Go yq's doc/operators/error.md: `select(cond) or error(msg)` raises only when the
        # condition is false - the ``or`` itself always yields a boolean, not the input.
        assert yaqpy.query('select(. == "howdy") or error("expected howdy, got \\(.)")',
                            "howdy") == [True]
        with pytest.raises(EvaluationError) as raised:
            yaqpy.query('select(. == "howdy") or error("expected howdy, got \\(.)")', "bye")
        assert str(raised.value) == "expected howdy, got bye"


class EmptyTests:
    def test_empty_produces_no_output(self) -> None:
        assert yaqpy.query("empty", 1) == []

    def test_empty_inside_a_pipe_drops_the_value(self) -> None:
        assert yaqpy.query(".[] | (select(. > 1) // empty)", [1, 2, 3]) == [2, 3]

    def test_empty_is_a_full_word_not_a_prefix_match(self) -> None:
        # "empty" must not be swallowed by an unrelated rule that starts the same way.
        assert yaqpy.query("empty", 1) == []
        with pytest.raises(ExpressionSyntaxError):
            yaqpy.query("emptyish", 1)


class BareFirstTests:
    def test_bare_first_takes_the_first_child(self) -> None:
        assert yaqpy.query("first", [1, 2, 3]) == [1]

    def test_bare_first_after_a_pipe(self) -> None:
        assert yaqpy.query(".a | first", {"a": [1, 2, 3]}) == [1]

    def test_bare_first_of_an_empty_array_is_no_result(self) -> None:
        assert yaqpy.query("first", []) == []

    def test_first_with_a_condition_still_works(self) -> None:
        assert yaqpy.query("first(. > 1)", [1, 2, 3]) == [2]
        assert yaqpy.query(".a | first(. > 1)", {"a": [1, 2, 3]}) == [2]


class ArithmeticTests:
    """0926-03 決定 5 (E9): left-associative arithmetic, `* / %` tighter than `+ -`."""

    @pytest.mark.parametrize(("expression", "expected"), [
        ("1 - 2 - 3", -4),
        ("8 / 2 / 2", 2),
        ("2 * 3 + 1", 7),
        ("1 + 2 * 3", 7),
        ("10 - 4 + 1", 7),
        ("2 * 3 * 4", 24),
        ("10 % 4 - 1", 1),
    ])
    def test_left_to_right_with_multiply_first(self, expression: str, expected: int) -> None:
        assert yaqpy.query(expression, None) == [expected]

    def test_string_repeat_still_binds_tighter_than_add(self) -> None:
        assert yaqpy.query('"a" + "b" * 2', None) == ["abb"]

    def test_alternative_mixed_with_arithmetic_is_unaffected(self) -> None:
        assert yaqpy.query(".a // 5", {}) == [5]


class AddNullTests:
    """`+`'s A＋C row: adding null is now a value (jq's identity), not an error."""

    def test_number_plus_null_is_unchanged(self) -> None:
        assert yaqpy.query("1 + null", None) == [1]

    def test_null_plus_number_is_unchanged(self) -> None:
        assert yaqpy.query("null + 1", None) == [1]

    def test_string_plus_null_already_worked_and_still_does(self) -> None:
        assert yaqpy.query('"a" + null', None) == ["a"]


class UnaryMinusTests:
    """0926-03 3-2 単項 `-` (E5): a `-` is unary wherever an operand is expected -
    ``core.lang.postfix._expects_operand`` decides from the previous token's arity."""

    def test_unary_minus_on_a_path(self) -> None:
        assert yaqpy.query("-.a", {"a": 5}) == [-5]

    def test_unary_minus_after_a_pipe(self) -> None:
        assert yaqpy.query(".a | -.", {"a": 5}) == [-5]

    def test_unary_minus_on_a_variable(self) -> None:
        assert yaqpy.query("1 as $x | -$x", None) == [-1]

    def test_unary_minus_binds_tighter_than_multiply(self) -> None:
        assert yaqpy.query("-2 * 3", None) == [-6]
        assert yaqpy.query("2 * -3", None) == [-6]

    def test_unary_minus_negates_the_whole_traversal_chain(self) -> None:
        assert yaqpy.query("-.a.b", {"a": {"b": 5}}) == [-5]

    def test_binary_minus_after_a_value_is_unaffected(self) -> None:
        assert yaqpy.query(".a - 1", {"a": 5}) == [4]
        assert yaqpy.query("1 - -2", None) == [3]

    def test_unary_minus_in_a_comparison_and_object_value(self) -> None:
        assert yaqpy.query(".a == -1", {"a": -1}) == [True]
        assert yaqpy.query('{"a": -1}', None) == [{"a": -1}]

    def test_unary_minus_on_a_float(self) -> None:
        assert yaqpy.query("-.a", {"a": 1.5}) == [-1.5]

    def test_unary_minus_on_a_non_number_is_an_error(self) -> None:
        with pytest.raises(EvaluationError):
            yaqpy.query("-.a", {"a": "x"})


class CompoundAssignTests:
    """`//= /= %=` (E5): new to yaqpy - Go yq only ever had `+= -= *=`."""

    def test_divide_assign(self) -> None:
        assert yaqpy.query(".a /= .b", {"a": 10, "b": 4}) == [{"a": 2.5, "b": 4}]

    def test_modulo_assign(self) -> None:
        assert yaqpy.query(".a %= .b", {"a": 10, "b": 3}) == [{"a": 1, "b": 3}]

    def test_alternative_assign_fills_in_only_when_null(self) -> None:
        assert yaqpy.query(".c //= 5", {"c": None}) == [{"c": 5}]
        assert yaqpy.query(".a //= 5", {"a": 10}) == [{"a": 10}]
