"""Web 版のサーバー（``yaqpy-web`` / ``yaqpy --web``）。v0.6.0。**ここだけが uvicorn に依存する**。

``ft.run(view=WEB_BROWSER)`` を使わず、``flet.fastapi.app`` を uvicorn で自分で起動する。
理由（W0 の実測。``docs/flet-1.0-api-notes.md`` 7 章）：

* ``ft.run`` は ``host`` を省くと**全インターフェース**（``0.0.0.0`` と ``::``）で待ち受けた。
  ここでは ``WebConfig.host``（既定 ``127.0.0.1``）を必ず渡す。
* ``ft.run(upload_dir=…)`` はアップロードに必要な ``upload_endpoint_path``・``secret_key`` を
  渡さないため、``page.get_upload_url`` が使えない。

計画書 5-5 節「Web で公開するときに必ず守ること」の 4（ログに式や文書の中身を残さない）は
ここで守る：uvicorn のアクセスログを切り、ログの段階を warning にする。yaqpy 自身は式や文書を
ログに書かない。
"""

from __future__ import annotations

import asyncio
import secrets
import shutil
import tempfile
import threading
import time
import webbrowser
from typing import TextIO

import flet as ft
import flet.fastapi as flet_fastapi
import uvicorn

from yaqpy.gui import texts
from yaqpy.gui._run import _main
from yaqpy.gui.web_config import RunGate, WebConfig, WebRuntime

UPLOAD_ENDPOINT = "upload"          # 先頭に "/" を付けない（付けると "//upload" になり 405。W0）
WS_DEFAULT_MAX_SIZE = 16 * 1024 * 1024    # uvicorn の既定
WS_MARGIN = 1024 * 1024
BROWSER_WAIT_SECONDS = 10.0


def ws_max_size(config: WebConfig) -> int:
    """WebSocket の 1 通の上限。貼り付け・原文の追加編集は WebSocket で届くので、入力の上限より
    少し大きくしておく（上限いっぱいの貼り付けで接続が切れないように。W0）。"""
    return max(WS_DEFAULT_MAX_SIZE, config.max_input_bytes + WS_MARGIN)


def build_app(runtime: WebRuntime):
    """Flet の FastAPI アプリを組み立てる（テストからも呼ぶ）。"""

    async def main(page: ft.Page) -> None:
        await _main(page, web=runtime)

    return flet_fastapi.app(
        main,
        upload_dir=runtime.upload_dir,
        upload_endpoint_path=UPLOAD_ENDPOINT,
        max_upload_size=runtime.config.max_input_bytes,   # 画面の事前確認をすり抜けても 413
        secret_key=secrets.token_urlsafe(32),             # アップロード URL の署名（起動ごとに作る）
        # CDN を使わないと日本語のフォントが無く「□」になった（v0.6.0 の実測）。既定は Flet と同じ
        # CDN。オフライン向けに --no-cdn（その場合は --lang en を勧める）。
        no_cdn=not runtime.config.use_cdn,
        app_name=texts.APP_TITLE,
    )


def make_server(runtime: WebRuntime) -> uvicorn.Server:
    """uvicorn のサーバーを組み立てる（まだ起動しない。テストからも呼ぶ）。"""
    config = runtime.config
    return uvicorn.Server(uvicorn.Config(
        build_app(runtime),
        host=config.host,                        # 省かない（省くと全インターフェースになる。W0）
        port=config.port,
        ws="websockets-sansio",                  # flet-web 自身の起動と同じ実装
        ws_max_size=ws_max_size(config),
        log_level="warning",
        access_log=False,                        # URL も残さない（安全要件 4）
    ))


def new_runtime(config: WebConfig) -> WebRuntime:
    return WebRuntime(config=config, gate=RunGate(config.max_concurrent_runs),
                      upload_dir=tempfile.mkdtemp(prefix="yaqpy-web-"))


def serve(config: WebConfig, *, stderr: TextIO) -> int:
    """サーバーを起動し、Ctrl+C で止まるまで戻らない。戻り値は終了コード（0 / 1）。"""
    texts.select_language(config.language)      # 全セッション共通（タブごとには選ばない）
    runtime = new_runtime(config)
    upload_dir = runtime.upload_dir
    server = make_server(runtime)
    if config.exposed:
        stderr.write(texts.WEB_EXPOSED_WARNING.format(host=config.host))
        stderr.flush()
    threading.Thread(target=_announce_when_started, args=(server, config, stderr),
                     daemon=True).start()
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        pass
    except SystemExit:
        # uvicorn は待ち受けられない（ポートが使用中など）と、理由をログに出して
        # sys.exit(3) する。yaqpy の終了コードの規約（誤りは 1）にそろえる。
        stderr.write(texts.WEB_START_FAILED.format(host=config.host, port=config.port))
        return 1
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)
    return 0


def _announce_when_started(server: uvicorn.Server, config: WebConfig, stderr: TextIO) -> None:
    """待ち受けが**始まってから**案内を出し、ブラウザを開く（始まらなければ何もしない）。

    先に案内を出すと、ポートが使用中で起動できなかったときにも「起動しました」と出てしまう。
    """
    deadline = time.monotonic() + BROWSER_WAIT_SECONDS
    while not server.started:
        if time.monotonic() > deadline or server.should_exit:
            return
        time.sleep(0.1)
    stderr.write(texts.WEB_STARTED.format(url=config.url))
    stderr.flush()
    if config.open_browser:
        webbrowser.open(config.url)
