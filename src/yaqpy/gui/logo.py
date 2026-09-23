"""yaqpy のロゴ（窓のアイコン・ブラウザのタブのアイコン）の置き場所。v0.6.0。Flet 非依存。

原本はリポジトリの ``assets/images/``（``yaqpy-logo.ico`` / ``.png`` / ``.svg``）。wheel に入れる
ため、使うものだけをこのパッケージの ``assets/`` に**そのままコピー**している（内容が原本と
同じことは ``tests/unit/test_gui_logo.py`` が確かめる。原本を差し替えたらコピーも差し替える）。

* デスクトップ：``page.window.icon`` に ``.ico`` を渡す（Flet 1.0 では Windows でだけ効く）。
* Web：``flet.fastapi.app(assets_dir=WEB_ASSETS_DIR)``。Flet は、同梱の Web クライアントより先に
  ``assets_dir`` のファイルを返すので、``favicon.png``（タブのアイコン）と
  ``icons/loading-animation.png``（読み込み中の画面）が yaqpy のロゴに置き換わる。
"""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
WINDOW_ICON = ASSETS_DIR / "yaqpy-logo.ico"
WEB_ASSETS_DIR = ASSETS_DIR / "web"
FAVICON = WEB_ASSETS_DIR / "favicon.png"
LOADING_IMAGE = WEB_ASSETS_DIR / "icons" / "loading-animation.png"
