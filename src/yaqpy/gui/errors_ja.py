"""yaqpy の例外を、画面に出せる日本語の ViewModel に畳む（Flet 非依存）。"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from yaqpy.errors import (
    EvaluationError,
    EvaluationLimitError,
    ExpressionSyntaxError,
    FormatError,
    SecurityError,
    UnknownFormatError,
    YamlSyntaxError,
    YqError,
)
from yaqpy.gui import texts

# capability 名 → 設定画面での呼び名
_CAPABILITY_JA = {"env": "環境変数（env / strenv）", "file": "ファイル読み込み（load / loadstr）"}


@dataclass(frozen=True, slots=True)
class ErrorViewModel:
    code: str
    message: str
    hint: str = ""
    position: int = -1        # ExpressionSyntaxError のときだけ 0 以上
    capability: str = ""      # SecurityError のときだけ "env" / "file"
    limit: str = ""           # EvaluationLimitError のときだけ
    detail: str = ""          # 想定外の例外のトレース

    @property
    def is_security(self) -> bool:
        return self.code == "security"


def caret_line(position: int) -> str:
    """式の何文字目かを指す下線。position が負なら空文字。"""
    return "" if position < 0 else " " * position + "^"


def to_view_model(exc: BaseException) -> ErrorViewModel:
    """例外 1 個を ErrorViewModel にする。判定は具体的なものから順に見る。"""
    if isinstance(exc, ExpressionSyntaxError):
        where = f"式の {exc.position + 1} 文字目でエラー" if exc.position >= 0 else "式のエラー"
        return ErrorViewModel("expression_syntax", f"{where}：{exc.message}",
                              hint=texts.HINT_EXPRESSION, position=exc.position)

    if isinstance(exc, YamlSyntaxError):
        where = f"{exc.line} 行 {exc.column} 列" if exc.line else "入力"
        return ErrorViewModel("yaml_syntax", f"YAML の {where} でエラー：{exc.message}",
                              hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, UnknownFormatError):
        return ErrorViewModel("unknown_format", exc.message, hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, SecurityError):
        name = _CAPABILITY_JA.get(exc.capability, exc.capability or "この機能")
        return ErrorViewModel("security", f"この式は {name} を使いますが、許可されていません",
                              hint=texts.HINT_SECURITY.format(capability=name),
                              capability=exc.capability)

    if isinstance(exc, EvaluationLimitError):
        if exc.limit == "cancelled":
            return ErrorViewModel("evaluation_limit", texts.HINT_CANCELLED, limit=exc.limit)
        if exc.limit == "timeout_seconds":
            return ErrorViewModel("evaluation_limit", "時間切れで中断しました",
                                  hint=texts.HINT_TIMEOUT, limit=exc.limit)
        return ErrorViewModel("evaluation_limit", f"上限に達しました：{exc.message}",
                              limit=exc.limit)

    if isinstance(exc, EvaluationError):
        suffix = f"（演算子 {exc.operator}）" if exc.operator else ""
        return ErrorViewModel("evaluation", f"評価エラー：{exc.message}{suffix}")

    if isinstance(exc, FormatError):
        return ErrorViewModel("format", f"読み書きに失敗しました：{exc.message}",
                              hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, YqError):
        return ErrorViewModel(exc.code, exc.message)

    if isinstance(exc, OSError):
        return ErrorViewModel("io", f"ファイルを扱えませんでした：{exc.strerror or exc}")

    return ErrorViewModel("unexpected", texts.ERR_UNEXPECTED, hint=texts.HINT_REPORT,
                          detail="".join(traceback.format_exception(exc)).strip())
