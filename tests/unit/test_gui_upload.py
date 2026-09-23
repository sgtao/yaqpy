"""Web 版のアップロード受け取り（gui/_upload.py）のテスト（v0.6.0）。

本物のブラウザの代わりに、W0 で実測した Flet クライアントの振る舞いをまねる偽の picker を使う：
アップロードが済んだファイルは選択一覧から**取り除かれ**、``id`` は一覧の添字として引かれる。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

pytestmark = pytest.mark.skipif(ft is None, reason="flet is not installed")


class FakeClientPicker:
    """Flet の Dart 側 ``FilePicker.uploadFiles`` をまねる（W0 でソースを確認）。"""

    def __init__(self, root: Path, picks: list[tuple[str, bytes]], *,
                 server_limit: int | None = None, silent: bool = False) -> None:
        self.root = root
        self.picks = picks
        self.server_limit = server_limit
        self.silent = silent                   # 完了の通知を送らない（タイムアウトの試験）
        self.on_upload = None
        self._files: list[tuple[str, bytes]] = []
        self.uploaded_order: list[str] = []

    async def pick_files(self, **kwargs: object) -> list[ft.FilePickerFile]:
        self._files = list(self.picks)
        return [ft.FilePickerFile(id=i, name=n, size=len(d)) for i, (n, d) in enumerate(self.picks)]

    async def upload(self, files: list[ft.FilePickerUploadFile]) -> None:
        for uf in files:
            found = self._files[uf.id] if uf.id is not None and uf.id < len(self._files) else None
            if found is None:
                found = next((f for f in self._files if f[0] == uf.name), None)
            if found is None:
                continue                          # クライアントは「not found」を出すだけ
            name, data = found
            self.uploaded_order.append(name)
            target = parse_qs(urlsplit(uf.upload_url).query)["f"][0]
            path = self.root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.server_limit is not None and len(data) > self.server_limit:
                path.write_bytes(data[: self.server_limit])     # 413：書きかけが残る（W0）
                self._event(name, None, "Upload endpoint returned code 413")
                continue
            path.write_bytes(data)
            self._files.remove(found)             # 済んだものを一覧から取り除く（添字がずれる）
            if not self.silent:
                self._event(name, 1.0, None)

    def _event(self, name: str, progress: float | None, error: str | None) -> None:
        self.on_upload(ft.FilePickerUploadEvent(name="upload", control=mock.MagicMock(),
                                                file_name=name, progress=progress, error=error))


def make(tmp_path: Path, picks: list[tuple[str, bytes]], **kwargs: object):
    from yaqpy.gui._upload import WebUploader

    picker = FakeClientPicker(tmp_path, picks, **kwargs)     # type: ignore[arg-type]
    page = mock.MagicMock()
    page.get_upload_url = lambda target, seconds: f"upload?f={target}&e=x&s=y"
    uploader = WebUploader(page=page, picker=picker, upload_dir=str(tmp_path))  # type: ignore[arg-type]
    return uploader, picker


def no_limit(size: int) -> str:
    return ""


def leftovers(root: Path) -> list[str]:
    return [str(p) for p in root.rglob("*") if p.is_file()]


class WebUploaderTests:
    async def test_several_files_arrive_in_the_order_they_were_picked(self, tmp_path: Path) -> None:
        uploader, picker = make(tmp_path, [("a.yaml", b"a: 1\n"), ("b.json", b'{"b": 2}'),
                                           ("c.toml", b"c = 3\n")])
        items = await uploader.pick(check_size=no_limit)
        assert [(i.name, i.data) for i in items] == [
            ("a.yaml", b"a: 1\n"), ("b.json", b'{"b": 2}'), ("c.toml", b"c = 3\n")]
        assert picker.uploaded_order == ["c.toml", "b.json", "a.yaml"]   # id の大きい順（W0）
        assert leftovers(tmp_path) == []                                 # 読んだら消す

    async def test_too_large_files_are_refused_without_being_sent(self, tmp_path: Path) -> None:
        uploader, picker = make(tmp_path, [("big.yaml", b"x" * 100), ("ok.yaml", b"a: 1\n")])
        items = await uploader.pick(check_size=lambda size: "too large" if size > 10 else "")
        assert items[0].error == "too large" and items[0].data is None
        assert items[1].data == b"a: 1\n"
        assert picker.uploaded_order == ["ok.yaml"]

    async def test_a_server_refusal_leaves_no_partial_file(self, tmp_path: Path) -> None:
        uploader, _ = make(tmp_path, [("big.yaml", b"x" * 100)], server_limit=10)
        items = await uploader.pick(check_size=no_limit)
        assert not items[0].ok
        assert "big.yaml" in items[0].error
        assert leftovers(tmp_path) == []           # 413 の書きかけも消す

    async def test_no_completion_event_times_out_into_an_error(self, tmp_path: Path,
                                                               monkeypatch) -> None:
        from yaqpy.gui import _upload

        monkeypatch.setattr(_upload, "UPLOAD_WAIT_SECONDS", 0.1)
        uploader, _ = make(tmp_path, [("a.yaml", b"a: 1\n")], silent=True)
        items = await uploader.pick(check_size=no_limit)
        assert not items[0].ok
        assert leftovers(tmp_path) == []

    async def test_cancel_returns_nothing(self, tmp_path: Path) -> None:
        uploader, _ = make(tmp_path, [])
        started = mock.MagicMock()
        assert await uploader.pick(check_size=no_limit, on_start=started) == []
        started.assert_not_called()

    async def test_on_start_is_called_once_files_are_chosen(self, tmp_path: Path) -> None:
        uploader, _ = make(tmp_path, [("a.yaml", b"a: 1\n")])
        started = mock.MagicMock()
        await uploader.pick(check_size=no_limit, on_start=started)
        started.assert_called_once()

    async def test_cleanup_removes_the_session_folder(self, tmp_path: Path) -> None:
        uploader, _ = make(tmp_path, [("a.yaml", b"a: 1\n")])
        await uploader.pick(check_size=no_limit)
        sessions = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(sessions) == 1
        uploader.cleanup()
        assert not os.path.exists(sessions[0])

    async def test_two_sessions_use_different_folders(self, tmp_path: Path) -> None:
        first, _ = make(tmp_path, [("a.yaml", b"a: 1\n")])
        second, _ = make(tmp_path, [("a.yaml", b"a: 2\n")])
        a = await first.pick(check_size=no_limit)
        b = await second.pick(check_size=no_limit)
        assert (a[0].data, b[0].data) == (b"a: 1\n", b"a: 2\n")
        assert len([p for p in tmp_path.iterdir() if p.is_dir()]) == 2
