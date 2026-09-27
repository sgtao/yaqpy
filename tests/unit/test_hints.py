"""'Not Supported' hints for jq words yaqpy doesn't read yet (E7, 0926-03 5-6)."""

from __future__ import annotations

import pytest
from yaqpy import ExpressionSyntaxError
from yaqpy.core.lang.hints import hint_for


class HintForTests:
    def test_a_planned_word_says_not_supported_yet(self) -> None:
        assert hint_for("if true then 1 else 2 end", 0) == (
            "Not Supported (yet): `if` - planned for v0.9 (`if … then … elif … else … end`). "
            "Today: write a rewrite with assignment, or `select`.")

    def test_a_deliberately_unsupported_word_says_not_supported(self) -> None:
        hint = hint_for("def f: 1; f", 0)
        assert hint is not None
        assert hint.startswith("Not Supported: `def`")

    def test_an_unrelated_word_has_no_hint(self) -> None:
        assert hint_for("unknownword", 0) is None

    def test_a_non_word_position_has_no_hint(self) -> None:
        assert hint_for("123", 0) is None

    def test_looks_up_the_word_starting_at_position_not_the_whole_string(self) -> None:
        assert hint_for(". | if true", 4) is not None


class TokenizeHintWiringTests:
    def test_syntax_error_message_includes_the_hint(self) -> None:
        import yaqpy

        with pytest.raises(ExpressionSyntaxError) as raised:
            yaqpy.evaluate("try 1 catch 2", "1")
        assert "unexpected character" in str(raised.value)
        assert "Not Supported (yet): `try`" in str(raised.value)

    def test_an_ordinary_syntax_error_is_unchanged(self) -> None:
        import yaqpy

        with pytest.raises(ExpressionSyntaxError) as raised:
            yaqpy.evaluate("totally-not-a-word !!!", "1")
        assert "Not Supported" not in str(raised.value)
