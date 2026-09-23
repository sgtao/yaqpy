"""クリップボードの読み書き。失敗しても画面を止めない（``ft.Clipboard`` を触るのはここだけ）。

W0 の実測で、ブラウザが ``clipboard-write`` を許可していないと
``PlatformException(copy_fail, Clipboard.setData failed.)`` になった。読み取りも権限が
拒まれうる。デスクトップでも OS 側の理由で失敗しうるので、どちらも「失敗」として返し、
呼び出し側が案内を出す。
"""

from __future__ import annotations

import flet as ft


async def set_clipboard(text: str) -> bool:
    """クリップボードに書く。失敗したら False（例外で画面を止めない）。"""
    try:
        await ft.Clipboard().set(text)
    except Exception:                          # noqa: BLE001 - 失敗は利用者への案内で扱う
        return False
    return True


async def get_clipboard() -> str | None:
    """クリップボードの文字列を読む。失敗したら None（空のクリップボードは ``""``）。"""
    try:
        value = await ft.Clipboard().get()
    except Exception:                          # noqa: BLE001 - 失敗は利用者への案内で扱う
        return None
    return value or ""
