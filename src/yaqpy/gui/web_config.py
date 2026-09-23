"""Web 版（``yaqpy-gui --web``）の起動設定と、サーバーが強制する上限（改修計画 5-5 節 W1・W2）。

**このモジュールは flet を import しない**（引数の検査・上限の計算を単体テストするため）。

Web で公開するときに守ること（計画書 5-5 節の 4 項目）のうち、ここが受け持つのは次の 2 つ：

1. 既定は自分の PC からのみ（``127.0.0.1``）。それ以外は ``exposed`` で判定し、起動側が警告を出す。
3. 入力サイズ・実行時間・同時実行数の上限（``WebConfig`` の値と ``RunGate``）。

2（危険な演算子の強制無効）は ``gui/_di.py`` の ``make_web_service`` と ``gui/state.py`` の
``build_options``、4（ログに中身を残さない）は ``gui/_web.py`` が受け持つ。
"""

from __future__ import annotations

import ipaddress
import threading
from dataclasses import dataclass

from yaqpy.gui import texts
from yaqpy.gui.state import WebLimits

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8550
DEFAULT_MAX_INPUT_MIB = 10
"""1 ファイル・1 回の貼り付けの上限（MiB）。W0 の実測で、Flet の WebSocket（uvicorn の既定
16 MiB）に 10 MiB の送信が通ることを確かめた値。アップロードは HTTP なのでこの制約を受けないが、
貼り付け・原文の追加編集は WebSocket で届くため、既定はこの値に揃える。"""
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_CONCURRENT_RUNS = 2
"""サーバー全体で同時に走らせる評価の数。自分だけで使う前提（着手時の確認）なので小さめ。"""


class WebConfigError(ValueError):
    """起動引数の誤り（メッセージは画面ではなく標準エラー出力に出す）。"""


def is_loopback(host: str) -> bool:
    """自分の PC からしか届かない待ち受けアドレスか。``localhost`` も含める。"""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False                      # ホスト名などは「公開」側に倒す（警告を出す）


@dataclass(frozen=True, slots=True)
class WebConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    language: str = texts.DEFAULT_LANGUAGE
    open_browser: bool = True
    max_input_mib: int = DEFAULT_MAX_INPUT_MIB
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_concurrent_runs: int = DEFAULT_MAX_CONCURRENT_RUNS

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise WebConfigError("--host must not be empty")
        if not 1 <= self.port <= 65535:
            raise WebConfigError(f"--port must be between 1 and 65535 (got {self.port})")
        if self.language not in texts.LANGUAGES:
            raise WebConfigError(f"--lang must be one of {', '.join(texts.LANGUAGES)}")
        if self.max_input_mib < 1:
            raise WebConfigError("--max-input-mib must be 1 or more")
        if self.timeout_seconds <= 0:
            raise WebConfigError("--timeout must be greater than 0")
        if self.max_concurrent_runs < 1:
            raise WebConfigError("--max-concurrent-runs must be 1 or more")

    @property
    def exposed(self) -> bool:
        """ほかの端末から届きうる待ち受け（``0.0.0.0`` など）か。起動時に警告を出す。"""
        return not is_loopback(self.host)

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mib * 1024 * 1024

    @property
    def url(self) -> str:
        host = self.host
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"             # 全インターフェースで待つときも、自分は loopback で開く
        elif ":" in host:
            host = f"[{host}]"             # IPv6 の数値表記
        return f"http://{host}:{self.port}/"

    def limits(self) -> WebLimits:
        return WebLimits(max_input_bytes=self.max_input_bytes,
                         timeout_seconds=self.timeout_seconds)


class RunGate:
    """サーバー全体の同時実行数の上限（全セッションで 1 つを共有する）。

    待たせずに断る：評価はスレッドで走り、止めるのは協調的な中止だけなので、待ち行列を作ると
    放置されたセッションの分まで詰まりうる。空きがなければ「混み合っています」と返す。
    """

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be 1 or more")
        self._semaphore = threading.BoundedSemaphore(limit)

    def try_enter(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def leave(self) -> None:
        self._semaphore.release()
