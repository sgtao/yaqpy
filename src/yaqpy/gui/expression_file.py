"""式のファイル（``.yaqpy``）の読み書きの規則（Flet 非依存。v0.7.0）。

``.yaqpy`` は**式のテキストそのもの**：UTF-8（BOM なし）・改行は LF・末尾に改行を 1 つ。
CLI の ``yaqpy --from-file sample.yaqpy data.json``（``yaqpy sample.yaqpy data.json`` でも可）で、
そのまま使える。同梱のレシピ（``recipes/builtin/*.yaqpy``）も同じ形式（先頭にコメントの行がある）。

読み込みでは ``.yq``（mikefarah/yq の式ファイル）も受ける。
"""

from __future__ import annotations

import os

EXTENSION = ".yaqpy"
OPEN_EXTENSIONS = ("yaqpy", "yq")            # 読み込みダイアログの絞り込み（ドットなし）
MAX_BYTES = 1024 * 1024
"""式のファイルの上限（1 MiB）。式としては十分に大きく、誤って巨大なファイルを選んだときに固まらない。"""
DEFAULT_FILE_NAME = "expression" + EXTENSION

_BOM = "﻿"


class ExpressionFileError(ValueError):
    """式のファイルとして読めない（大きすぎる・UTF-8 でない）。``str(e)`` は画面に出せる文言。"""


def encode_expression(expression: str) -> str:
    """保存する本文。改行は LF にそろえ、末尾の改行は 1 つにする（式が空なら空行 1 つ）。"""
    return expression.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def decode_expression(raw: bytes | str) -> str:
    """読み込んだ内容から式を取り出す：BOM を除き、CRLF を LF にし、末尾の改行を 1 つだけ取り除く。

    CLI の ``args.py``（``\\r\\n`` を ``\\n`` に直す）と同じ扱い。大きさの検査は ``ensure_size``。
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ExpressionFileError(_not_utf8()) from e
    else:
        text = raw[1:] if raw.startswith(_BOM) else raw
    text = text.replace("\r\n", "\n")
    return text[:-1] if text.endswith("\n") else text


def ensure_size(size: int) -> None:
    """上限（``MAX_BYTES``）を超えるなら ``ExpressionFileError``。中身を読む前に呼ぶ。"""
    if size > MAX_BYTES:
        raise ExpressionFileError(_too_large(size))


def default_expression_file_name(document_name: str = "") -> str:
    """保存ダイアログの初期ファイル名：開いている文書名の拡張子を除いたもの＋``.yaqpy``。

    文書が無い・貼り付け由来（名前が空）なら ``expression.yaqpy``。
    """
    stem = os.path.splitext(os.path.basename(document_name))[0] if document_name else ""
    return f"{stem}{EXTENSION}" if stem else DEFAULT_FILE_NAME


def ensure_extension(path: str) -> str:
    """保存先に拡張子が無ければ ``.yaqpy`` を足す（別の拡張子を指定されたら、そのまま尊重する）。"""
    return path if os.path.splitext(path)[1] else path + EXTENSION


def _too_large(size: int) -> str:
    from yaqpy.gui import texts

    return texts.ERR_EXPR_FILE_TOO_LARGE.format(size=f"{size:,}", limit=f"{MAX_BYTES:,}")


def _not_utf8() -> str:
    from yaqpy.gui import texts

    return texts.ERR_EXPR_FILE_NOT_UTF8
