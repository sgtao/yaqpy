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
