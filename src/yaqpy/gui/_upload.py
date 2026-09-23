"""Web 版のファイル受け取り（ブラウザ → サーバーのアップロード）。v0.6.0。

W0 の実測（``docs/flet-1.0-api-notes.md`` 7 章）に従う：

* ``pick_files()`` は Web では ``path`` を返さない。``with_data=True`` は中身を WebSocket の 1 通で
  送るので、**サイズを確かめる前に全量が届き**、大きいと接続が切れる。そこで中身なしで選ばせて
  ``size`` を確かめ、上限内のものだけを ``upload()``（HTTP の PUT）で送らせる。
* 複数ファイルは **``id`` の大きい順**にアップロードする（クライアントが済んだものを一覧から
  取り除き、添字が前詰めにずれるため）。``name`` も渡す。
* サーバー側の上限（413）で断られても途中のファイルが残るので、**成功・失敗を問わず消す**。

受け取ったファイルはメモリに読んだらすぐ消す。セッションが終わるときに、そのセッションの
フォルダごと消す（``cleanup``）。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from yaqpy.gui import texts

UPLOAD_URL_SECONDS = 120        # 署名つきアップロード URL の有効期限
UPLOAD_WAIT_SECONDS = 120       # 1 ファイルのアップロードの完了を待つ上限
COMPLETE_POLL_SECONDS = 0.05    # 完了通知のあと、ファイルが書き終わるのを待つ間隔
COMPLETE_POLL_LIMIT = 40        # 〃 の回数（合計 2 秒）


@dataclass(frozen=True, slots=True)
class Uploaded:
    """受け取った 1 件。``error`` が空でなければ ``data`` は None。"""

    name: str
    data: bytes | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.data is not None


class WebUploader:
    """1 セッション（ブラウザのタブ）に 1 個。"""

    def __init__(self, *, page: ft.Page, picker: ft.FilePicker, upload_dir: str) -> None:
        self._page = page
        self._picker = picker
        self._root = os.path.realpath(upload_dir)
        self._session = uuid.uuid4().hex          # 元のファイル名はパスに使わない
        self._current: tuple[str, asyncio.Future[str]] | None = None
        picker.on_upload = self._on_upload

    async def pick(self, *, check_size: Callable[[int], str],
                   on_start: Callable[[], None] | None = None,
                   dialog_title: str | None = None, allow_multiple: bool = True,
                   allowed_extensions: list[str] | None = None) -> list[Uploaded]:
        """ファイルを選ばせ、上限内のものをアップロードさせて中身を返す（選んだ順）。

        ``check_size`` はバイト数を受け取り、断る理由（空なら受け付ける）を返す。
        キャンセルなら空のリスト。式のファイル（``.yaqpy``。v0.7.0）を 1 件だけ受け取るときは、
        ``allow_multiple=False`` と ``allowed_extensions`` を渡す。
        """
        custom = {"file_type": ft.FilePickerFileType.CUSTOM,
                  "allowed_extensions": allowed_extensions} if allowed_extensions else {}
        files = await self._picker.pick_files(dialog_title=dialog_title or texts.BTN_ADD_FILE,
                                              allow_multiple=allow_multiple, **custom)
        if not files:
            return []
        if on_start is not None:
            on_start()
        results: dict[int, Uploaded] = {}
        accepted: list[tuple[int, ft.FilePickerFile]] = []
        for order, picked in enumerate(files):
            reason = check_size(picked.size)
            if reason:
                results[order] = Uploaded(name=picked.name, error=reason)
            else:
                accepted.append((order, picked))
        for order, picked in sorted(accepted, key=lambda pair: pair[1].id, reverse=True):
            results[order] = await self._upload_one(picked)
        return [results[order] for order in range(len(files))]

    async def _upload_one(self, picked: ft.FilePickerFile) -> Uploaded:
        stored = uuid.uuid4().hex
        target = f"{self._session}/{stored}"          # upload_dir からの相対（URL に載る）
        path = os.path.join(self._root, self._session, stored)
        loop = asyncio.get_running_loop()
        done: asyncio.Future[str] = loop.create_future()
        self._current = (picked.name, done)
        try:
            url = self._page.get_upload_url(target, UPLOAD_URL_SECONDS)
            await self._picker.upload([ft.FilePickerUploadFile(upload_url=url, id=picked.id,
                                                               name=picked.name)])
            error = await asyncio.wait_for(done, UPLOAD_WAIT_SECONDS)
            if error:
                return Uploaded(name=picked.name, error=texts.ERR_UPLOAD_FAILED.format(name=picked.name))
            data = await self._read_when_complete(path, picked.size)
            if data is None:
                return Uploaded(name=picked.name, error=texts.ERR_UPLOAD_FAILED.format(name=picked.name))
            return Uploaded(name=picked.name, data=data)
        except (TimeoutError, RuntimeError, OSError):
            return Uploaded(name=picked.name, error=texts.ERR_UPLOAD_FAILED.format(name=picked.name))
        finally:
            self._current = None
            _remove_quietly(path)                 # 成功でも失敗（413 の書きかけ）でも残さない

    async def _read_when_complete(self, path: str, size: int) -> bytes | None:
        """完了の通知のあと、選んだときの大きさまで書き終わっていれば中身を返す。"""
        for _ in range(COMPLETE_POLL_LIMIT):
            try:
                if os.path.getsize(path) >= size:
                    return await asyncio.to_thread(_read_bytes, path)
            except OSError:
                pass
            await asyncio.sleep(COMPLETE_POLL_SECONDS)
        return None

    def _on_upload(self, e: ft.FilePickerUploadEvent) -> None:
        current = self._current
        if current is None:
            return
        name, done = current
        if e.file_name != name or done.done():
            return
        if e.error:
            done.set_result(e.error)
        elif e.progress is not None and e.progress >= 1.0:
            done.set_result("")

    def cleanup(self) -> None:
        """このセッションが受け取ったものを消す（セッションの終了時）。"""
        shutil.rmtree(os.path.join(self._root, self._session), ignore_errors=True)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
