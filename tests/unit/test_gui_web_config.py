"""Web 版の起動設定と同時実行の関門のテスト（改修計画 5-5 節 W1・W2）。flet は要らない。"""

from __future__ import annotations

import pytest

from yaqpy.gui.web_config import (
    DEFAULT_HOST,
    DEFAULT_MAX_INPUT_MIB,
    RunGate,
    WebConfig,
    WebConfigError,
    is_loopback,
)


class WebConfigTests:
    def test_defaults_listen_on_this_pc_only(self) -> None:
        config = WebConfig()
        assert config.host == DEFAULT_HOST == "127.0.0.1"
        assert not config.exposed
        assert config.url == "http://127.0.0.1:8550/"

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "LOCALHOST"])
    def test_loopback_hosts_are_not_exposed(self, host: str) -> None:
        assert is_loopback(host)
        assert not WebConfig(host=host).exposed

    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "my-server.local"])
    def test_other_hosts_are_exposed(self, host: str) -> None:
        """ホスト名は解決せず「公開」側に倒す（警告を出す側が安全）。"""
        assert WebConfig(host=host).exposed

    def test_all_interfaces_still_open_on_loopback(self) -> None:
        assert WebConfig(host="0.0.0.0", port=9000).url == "http://127.0.0.1:9000/"
        assert WebConfig(host="::1", port=9000).url == "http://[::1]:9000/"

    def test_limits_carry_the_caps(self) -> None:
        limits = WebConfig(max_input_mib=3, timeout_seconds=4.5).limits()
        assert limits.max_input_bytes == 3 * 1024 * 1024
        assert limits.timeout_seconds == 4.5

    def test_default_input_cap_fits_the_websocket(self) -> None:
        """W0 の実測：10 MiB は通り、20 MiB で接続が切れた（uvicorn の既定 16 MiB）。"""
        assert DEFAULT_MAX_INPUT_MIB * 1024 * 1024 < 16 * 1024 * 1024

    @pytest.mark.parametrize("kwargs, flag", [
        ({"host": " "}, "--host"),
        ({"port": 0}, "--port"),
        ({"port": 70000}, "--port"),
        ({"language": "fr"}, "--lang"),
        ({"max_input_mib": 0}, "--max-input-mib"),
        ({"timeout_seconds": 0}, "--timeout"),
        ({"max_concurrent_runs": 0}, "--max-concurrent-runs"),
    ])
    def test_bad_values_name_the_flag(self, kwargs: dict[str, object], flag: str) -> None:
        with pytest.raises(WebConfigError, match=flag):
            WebConfig(**kwargs)                  # type: ignore[arg-type]


class RunGateTests:
    def test_refuses_beyond_the_limit_without_waiting(self) -> None:
        gate = RunGate(2)
        assert gate.try_enter()
        assert gate.try_enter()
        assert not gate.try_enter()              # 3 つ目は待たずに断る
        gate.leave()
        assert gate.try_enter()                  # 空いたらまた入れる

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            RunGate(0)
