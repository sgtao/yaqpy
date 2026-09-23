"""ファイルテキストの取り込み口（ダイアログ・ドロップ・貼り付けを 1 つにまとめる）。

読み込み自体は FileSystemPort を通す。サイズの事前確認だけは、
巨大ファイルを読んでしまわないために ``size_of`` コールバックを使う。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from yaqpy.app.ports import FileSystemPort
from yaqpy.gui import texts

DIALOG = "dialog"
DROP = "drop"
PASTE = "paste"
UPLOAD = "upload"          # Web 版：ブラウザから送られた中身（サーバー側のパスは持たない。v0.6.0）


class IntakeError(Exception):
    """取り込めなかった理由（すでに日本語）。"""


@dataclass(frozen=True, slots=True)
class IntakeItem:
    name: str          # 形式の自動判定に使う表示名。貼り付けなら ""
    text: str
    origin: str
    byte_size: int
    path: str | None = None


def _human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} B"


def from_path(fs: FileSystemPort, path: str, *, max_bytes: int,
              size_of: Callable[[str], int] | None = None,
              origin: str = DIALOG) -> IntakeItem:
    """ファイルを 1 つ取り込む。大きすぎる場合は読まずに失敗する。"""
    if not fs.exists_file(path):
        raise IntakeError(texts.ERR_NOT_A_FILE)
    probe = size_of or os.path.getsize
    try:
        size = probe(path)
    except OSError:
        size = 0                       # 測れないときは読んでから測る
    if size > max_bytes:
        raise IntakeError(texts.ERR_TOO_LARGE.format(size=_human(size), limit=_human(max_bytes)))
    try:
        text = fs.read_text(path)
    except UnicodeDecodeError as e:
        raise IntakeError(texts.ERR_NOT_UTF8) from e
    actual = len(text.encode("utf-8"))
    if actual > max_bytes:
        raise IntakeError(texts.ERR_TOO_LARGE.format(size=_human(actual),
                                                     limit=_human(max_bytes)))
    return IntakeItem(name=os.path.basename(path), text=text, origin=origin,
                      byte_size=actual, path=path)


def ensure_size(size: int, *, max_bytes: int) -> None:
    """大きすぎれば IntakeError。Web 版はアップロードの**前に**これで断る（中身を送らせない）。"""
    if size > max_bytes:
        raise IntakeError(texts.ERR_TOO_LARGE.format(size=_human(size), limit=_human(max_bytes)))


def from_bytes(name: str, data: bytes, *, max_bytes: int, origin: str = UPLOAD) -> IntakeItem:
    """ブラウザから届いたファイルの中身を取り込む（Web 版。v0.6.0）。

    ``name`` は形式の自動判定に使う表示名（ブラウザが教える元のファイル名。パスではない）。
    文字コードは ``LocalFileSystem.read_text`` と同じく BOM 付きも読める UTF-8。
    """
    ensure_size(len(data), max_bytes=max_bytes)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise IntakeError(texts.ERR_NOT_UTF8) from e
    return IntakeItem(name=os.path.basename(name), text=text, origin=origin,
                      byte_size=len(text.encode("utf-8")), path=None)


def from_text(text: str, *, name: str = "", origin: str = PASTE) -> IntakeItem:
    """貼り付けられたテキストを取り込む。"""
    return IntakeItem(name=name, text=text, origin=origin,
                      byte_size=len(text.encode("utf-8")), path=None)
