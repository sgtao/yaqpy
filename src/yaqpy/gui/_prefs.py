"""設定の保存・復元。``ft.SharedPreferences`` を触るのはこのモジュールだけにする（U1）。

保存するのは「安全な設定」だけ（``yaqpy.gui.state.settings_to_dict``）。
``allow_env`` / ``allow_file`` は既定（不許可）に戻る。危険な許可を持ち越さないため。
"""

from __future__ import annotations

import json

import flet as ft

from yaqpy.gui.state import SettingsState, settings_from_dict, settings_to_dict

_KEY = "yaqpy.gui.settings"


async def load_settings(sp: ft.SharedPreferences) -> SettingsState:
    try:
        raw = await sp.get(_KEY)
    except Exception:                            # noqa: BLE001 - 読めなくても既定値で起動する
        return SettingsState()
    if not raw:
        return SettingsState()
    try:
        data = json.loads(raw)
    except ValueError:
        return SettingsState()
    if not isinstance(data, dict):
        return SettingsState()
    return settings_from_dict(data)


async def save_settings(sp: ft.SharedPreferences, settings: SettingsState) -> None:
    try:
        await sp.set(_KEY, json.dumps(settings_to_dict(settings)))
    except Exception:                            # noqa: BLE001 - 保存に失敗しても操作は続けられる
        pass
