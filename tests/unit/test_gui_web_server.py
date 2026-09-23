"""Web 版のサーバー（gui/_web.py）のテスト。実際に uvicorn を起動して確かめる（v0.6.0）。

flet-web（``[web]`` extra）が無い環境では飛ばす。
"""

from __future__ import annotations

import http.client
import importlib.util
import os
import shutil
import socket
import threading
import time
from typing import Self

import pytest

from yaqpy.gui.web_config import WebConfig

pytestmark = pytest.mark.skipif(
    not all(importlib.util.find_spec(n) for n in ("flet", "flet_web", "uvicorn")),
    reason="the web extra (flet-web) is not installed")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RunningServer:
    def __init__(self, **config: object) -> None:
        from yaqpy.gui import _web

        self.config = WebConfig(port=free_port(), open_browser=False, **config)  # type: ignore[arg-type]
        self.runtime = _web.new_runtime(self.config)
        self.server = _web.make_server(self.runtime)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> Self:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("the web server did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)
        shutil.rmtree(self.runtime.upload_dir, ignore_errors=True)

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.config.port, timeout=10)
        try:
            conn.request(method, path, body=body)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def bound_addresses(self) -> set[str]:
        return {sock.getsockname()[0] for srv in self.server.servers for sock in srv.sockets}


class WebServerTests:
    def test_listens_on_loopback_only_by_default(self) -> None:
        """W0：ft.run は host を省くと 0.0.0.0 と :: で待ち受けた。yaqpy は 127.0.0.1 だけ。"""
        with RunningServer() as running:
            assert running.bound_addresses() == {"127.0.0.1"}

    def test_serves_the_bundled_web_client(self) -> None:
        with RunningServer() as running:
            status, body = running.request("GET", "/")
        assert status == 200
        assert b"flutter" in body.lower()

    def test_an_unsigned_upload_is_refused(self) -> None:
        """アップロードは署名つき URL だけ（ブラウザを開いた誰かが勝手に置けない）。"""
        with RunningServer() as running:
            status, _ = running.request("PUT", "/upload?f=x&e=2099-01-01T00:00:00%2B00:00&s=bad",
                                        body=b"a: 1\n")
            assert status == 403
            assert os.listdir(running.runtime.upload_dir) == []

    def test_the_upload_dir_is_a_fresh_temporary_folder(self) -> None:
        with RunningServer() as running:
            assert os.path.isdir(running.runtime.upload_dir)
            assert os.path.basename(running.runtime.upload_dir).startswith("yaqpy-web-")


class WsMaxSizeTests:
    def test_default_keeps_uvicorn_default(self) -> None:
        from yaqpy.gui._web import WS_DEFAULT_MAX_SIZE, ws_max_size

        assert ws_max_size(WebConfig()) == WS_DEFAULT_MAX_SIZE

    def test_grows_with_a_larger_input_cap(self) -> None:
        from yaqpy.gui._web import ws_max_size

        assert ws_max_size(WebConfig(max_input_mib=30)) > 30 * 1024 * 1024
