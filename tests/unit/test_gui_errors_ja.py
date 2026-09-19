"""例外 → 日本語 ViewModel の変換テスト（GUI 設計書 5-8）。"""

from __future__ import annotations

import unittest

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


class ErrorMappingTests(unittest.TestCase):
    def test_expression_syntax_keeps_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("閉じ括弧がありません", position=6))
        self.assertEqual(vm.code, "expression_syntax")
        self.assertIn("7 文字目", vm.message)
        self.assertEqual(vm.position, 6)

    def test_expression_syntax_without_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("だめ"))
        self.assertIn("式のエラー", vm.message)
        self.assertEqual(vm.position, -1)

    def test_yaml_syntax_shows_line_and_column(self) -> None:
        vm = to_view_model(YamlSyntaxError("bad indent", line=12, column=3))
        self.assertEqual(vm.code, "yaml_syntax")
        self.assertIn("12 行 3 列", vm.message)

    def test_unknown_format(self) -> None:
        vm = to_view_model(UnknownFormatError("unknown format 'xml'", format="xml"))
        self.assertEqual(vm.code, "unknown_format")

    def test_security_points_at_the_setting(self) -> None:
        vm = to_view_model(SecurityError("env operations have been disabled", capability="env"))
        self.assertEqual(vm.code, "security")
        self.assertTrue(vm.is_security)
        self.assertEqual(vm.capability, "env")
        self.assertIn("環境変数", vm.message)

    def test_cancelled(self) -> None:
        vm = to_view_model(EvaluationLimitError("evaluation was cancelled", limit="cancelled"))
        self.assertEqual(vm.limit, "cancelled")
        self.assertIn("中止", vm.message)

    def test_timeout(self) -> None:
        vm = to_view_model(EvaluationLimitError("too slow", limit="timeout_seconds"))
        self.assertIn("時間切れ", vm.message)
        self.assertTrue(vm.hint)

    def test_evaluation_error_mentions_operator(self) -> None:
        vm = to_view_model(EvaluationError("cannot compare", operator="COMPARE"))
        self.assertIn("COMPARE", vm.message)

    def test_plain_format_error(self) -> None:
        vm = to_view_model(FormatError("broken"))
        self.assertEqual(vm.code, "format")

    def test_unexpected_exception_keeps_traceback(self) -> None:
        vm = to_view_model(ValueError("boom"))
        self.assertEqual(vm.code, "unexpected")
        self.assertIn("ValueError", vm.detail)

    def test_caret_line(self) -> None:
        self.assertEqual(caret_line(3), "   ^")
        self.assertEqual(caret_line(-1), "")


if __name__ == "__main__":
    unittest.main()
