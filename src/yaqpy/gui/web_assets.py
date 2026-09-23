"""Web 版の静的ファイル（ブラウザに配るもの）の組み立て。v0.7.0。Flet 非依存。

Flet の ``assets_dir`` は、そこに ``index.html`` があれば同梱のものより先に使う（実測：
``flet_web/fastapi/flet_static_files.py``）。そこで Flet 同梱の ``index.html`` に、
ドラッグ＆ドロップを受ける ``yaqpy-drop.js`` の読み込みを**1 行だけ足した**ものを作り、
ロゴのファイルと一緒に一時フォルダへ置く。同梱のものを写して加工するので、
Flet が ``index.html`` を更新しても（``<!-- fletAppConfig -->`` などの目印が残る限り）追随できる。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from yaqpy.gui.logo import WEB_ASSETS_DIR

DROP_SCRIPT_NAME = "yaqpy-drop.js"
DROP_SCRIPT_TAG = f'<script src="{DROP_SCRIPT_NAME}"></script>'
_BODY_END = "</body>"


def add_drop_script(index_html: str) -> str:
    """``index.html`` の ``</body>`` の直前に、ドロップ用のスクリプトの読み込みを足す。

    足す場所が見つからなければ ``ValueError``（黙って足さないままにしない）。
    すでに足してあれば何もしない。
    """
    if DROP_SCRIPT_TAG in index_html:
        return index_html
    position = index_html.rfind(_BODY_END)
    if position < 0:
        raise ValueError("index.html に </body> が見つかりません")
    return f"{index_html[:position]}  {DROP_SCRIPT_TAG}\n{index_html[position:]}"


def build_assets_dir(dest: str | Path, *, flet_index: str | Path,
                     source: Path = WEB_ASSETS_DIR) -> Path:
    """``dest`` に、yaqpy の Web 用ファイル一式（ロゴ・ドロップ用スクリプト・``index.html``）を作る。"""
    dest_path = Path(dest)
    shutil.copytree(source, dest_path, dirs_exist_ok=True)
    html = Path(flet_index).read_text(encoding="utf-8")
    (dest_path / "index.html").write_text(add_drop_script(html), encoding="utf-8", newline="\n")
    return dest_path


DROP_ROUTE = "__yaqpy_drop"
"""``yaqpy-drop.js`` がドロップを知らせるときに使うルート名（JS 側の ``DROP_ROUTE`` と同じ）。"""


def is_drop_route(route: str | None) -> bool:
    """Flet の ``on_route_change`` の ``route`` が、ドロップの通知か。"""
    return bool(route) and route.strip("/").split("/")[-1] == DROP_ROUTE
