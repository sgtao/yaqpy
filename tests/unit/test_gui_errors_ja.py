"""例外 → 日本語 ViewModel の変換テスト（GUI 設計書 5-8）。"""

from __future__ import annotations

from yaqpy.errors import (
    EvaluationError,
    EvaluationLimitError,
    ExpressionSyntaxError,
    FormatError,
    SecurityError,
    UnknownFormatError,
    YamlSyntaxError,
)
from yaqpy.gui.errors_ja import caret_line, to_view_model


class ErrorMappingTests:
    def test_expression_syntax_keeps_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("閉じ括弧がありません", position=6))
        assert vm.code == "expression_syntax"
        assert "7 文字目" in vm.message
        assert vm.position == 6

    def test_expression_syntax_without_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("だめ"))
        assert "式のエラー" in vm.message
        assert vm.position == -1

    def test_yaml_syntax_shows_line_and_column(self) -> None:
        vm = to_view_model(YamlSyntaxError("bad indent", line=12, column=3))
        assert vm.code == "yaml_syntax"
        assert "12 行 3 列" in vm.message

    def test_unknown_format(self) -> None:
        vm = to_view_model(UnknownFormatError("unknown format 'xml'", format="xml"))
        assert vm.code == "unknown_format"

    def test_security_points_at_the_setting(self) -> None:
        vm = to_view_model(SecurityError("env operations have been disabled", capability="env"))
        assert vm.code == "security"
        assert vm.is_security
        assert vm.capability == "env"
        assert "環境変数" in vm.message

    def test_cancelled(self) -> None:
        vm = to_view_model(EvaluationLimitError("evaluation was cancelled", limit="cancelled"))
        assert vm.limit == "cancelled"
        assert "中止" in vm.message

    def test_timeout(self) -> None:
        vm = to_view_model(EvaluationLimitError("too slow", limit="timeout_seconds"))
        assert "時間切れ" in vm.message
        assert vm.hint

    def test_evaluation_error_mentions_operator(self) -> None:
        vm = to_view_model(EvaluationError("cannot compare", operator="COMPARE"))
        assert "COMPARE" in vm.message

    def test_plain_format_error(self) -> None:
        vm = to_view_model(FormatError("broken"))
        assert vm.code == "format"

    def test_unexpected_exception_keeps_traceback(self) -> None:
        vm = to_view_model(ValueError("boom"))
        assert vm.code == "unexpected"
        assert "ValueError" in vm.detail

    def test_caret_line(self) -> None:
        assert caret_line(3) == "   ^"
        assert caret_line(-1) == ""
