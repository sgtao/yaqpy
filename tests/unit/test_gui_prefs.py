"""設定の保存・復元（GUI 改修計画 5-4 節 U1）。

``ft.SharedPreferences`` と同じ形（``async get(key)`` / ``async set(key, value)``）の
フェイクで検証する（flet が無い環境では飛ばす。他の ``test_gui_*`` と同じ方針）。
"""

from __future__ import annotations

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from yaqpy.gui.state import SettingsState


class _FakePreferences:
    """``ft.SharedPreferences`` の ``get`` / ``set`` だけを真似た二重（テスト用）。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class SettingsPersistenceTests:
    async def test_round_trip(self) -> None:
        from yaqpy.gui._prefs import load_settings, save_settings

        sp = _FakePreferences()
        settings = SettingsState(timeout_seconds=30.0, max_input_mib=10,
                                 max_display_lines=100, dark_theme=True,
                                 allow_env=True, allow_file=True)
        await save_settings(sp, settings)
        restored = await load_settings(sp)
        assert restored.timeout_seconds == 30.0
        assert restored.max_input_mib == 10
        assert restored.max_display_lines == 100
        assert restored.dark_theme is True

    async def test_security_switches_are_never_persisted(self) -> None:
        """allow_env / allow_file は毎回既定（不許可）に戻す（5-4 節 U1 の注意）。"""
        from yaqpy.gui._prefs import load_settings, save_settings

        sp = _FakePreferences()
        await save_settings(sp, SettingsState(allow_env=True, allow_file=True))
        restored = await load_settings(sp)
        assert restored.allow_env is False
        assert restored.allow_file is False

    async def test_first_launch_falls_back_to_defaults(self) -> None:
        from yaqpy.gui._prefs import load_settings

        restored = await load_settings(_FakePreferences())
        assert restored == SettingsState()

    async def test_corrupted_value_falls_back_to_defaults(self) -> None:
        from yaqpy.gui._prefs import load_settings

        sp = _FakePreferences()
        await sp.set("yaqpy.gui.settings", "not json")
        restored = await load_settings(sp)
        assert restored == SettingsState()

    async def test_read_error_falls_back_to_defaults(self) -> None:
        """SharedPreferences 側が例外を投げても GUI の起動は落とさない。"""
        from yaqpy.gui._prefs import load_settings

        class _Failing:
            async def get(self, key: str) -> str:
                raise RuntimeError("boom")

        restored = await load_settings(_Failing())
        assert restored == SettingsState()


class SettingsDictTests:
    def test_round_trip_via_plain_dict(self) -> None:
        from yaqpy.gui.state import settings_from_dict, settings_to_dict

        settings = SettingsState(timeout_seconds=5.0, max_input_mib=1, max_display_lines=1,
                                 dark_theme=True, allow_env=True, allow_file=True)
        data = settings_to_dict(settings)
        assert "allow_env" not in data
        assert "allow_file" not in data
        restored = settings_from_dict(data)
        assert restored.timeout_seconds == 5.0
        assert restored.max_input_mib == 1
        assert restored.max_display_lines == 1
        assert restored.dark_theme is True
        assert restored.allow_env is False
        assert restored.allow_file is False

    def test_bad_types_fall_back_to_defaults(self) -> None:
        from yaqpy.gui.state import settings_from_dict

        restored = settings_from_dict({"timeout_seconds": "not a number", "max_input_mib": -1,
                                       "max_display_lines": None})
        defaults = SettingsState()
        assert restored.timeout_seconds == defaults.timeout_seconds
        assert restored.max_input_mib == defaults.max_input_mib
        assert restored.max_display_lines == defaults.max_display_lines
