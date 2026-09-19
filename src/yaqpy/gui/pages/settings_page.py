"""設定画面。値は GuiState.settings に即時反映し、必要なら再実行を依頼する。"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui.state import GuiState


class SettingsPage:
    def __init__(self, *, page: ft.Page, state: GuiState,
                 on_changed: Callable[[], None]) -> None:
        self._page = page
        self._state = state
        self._on_changed = on_changed
        s = state.settings

        self._allow_env = ft.Switch(label=texts.SET_ALLOW_ENV, value=s.allow_env,
                                    on_change=self._on_allow_env)
        self._allow_file = ft.Switch(label=texts.SET_ALLOW_FILE, value=s.allow_file,
                                     on_change=self._on_allow_file)
        # Flet 1.0 の Switch には focus() が無いので、導線からは背景色で強調する（focus_capability）
        self._boxes = {
            "env": ft.Container(content=self._allow_env, padding=6, border_radius=8),
            "file": ft.Container(content=self._allow_file, padding=6, border_radius=8),
        }
        self._timeout = ft.TextField(label=texts.SET_TIMEOUT, width=180,
                                     value=str(int(s.timeout_seconds)),
                                     input_filter=ft.NumbersOnlyInputFilter(),
                                     on_change=self._on_timeout, on_blur=self._restore_fields)
        self._max_input = ft.TextField(label=texts.SET_MAX_INPUT, width=180,
                                       value=str(s.max_input_mib),
                                       input_filter=ft.NumbersOnlyInputFilter(),
                                       on_change=self._on_max_input, on_blur=self._restore_fields)
        self._max_lines = ft.TextField(label=texts.SET_MAX_LINES, width=180,
                                       value=str(s.max_display_lines),
                                       input_filter=ft.NumbersOnlyInputFilter(),
                                       on_change=self._on_max_lines, on_blur=self._restore_fields)
        self._dark = ft.Switch(label=texts.SET_DARK, value=s.dark_theme,
                               on_change=self._on_dark)

        self._root = ft.Column([
            ft.Text(texts.SET_TITLE, size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text(texts.SET_SECURITY, weight=ft.FontWeight.W_600),
            ft.Text(texts.SET_SECURITY_NOTE, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            self._boxes["env"],
            self._boxes["file"],
            ft.Text(texts.SET_SYSTEM_NOTE, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Divider(),
            ft.Text(texts.SET_RUN, weight=ft.FontWeight.W_600),
            ft.Row([self._timeout, self._max_input, self._max_lines], spacing=12),
            ft.Divider(),
            ft.Text(texts.SET_VIEW, weight=ft.FontWeight.W_600),
            self._dark,
        ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    @property
    def control(self) -> ft.Control:
        return self._root

    def focus_capability(self, capability: str) -> None:
        """セキュリティエラーからの導線（T3-5）で、該当スイッチを目立たせる。"""
        for name, box in self._boxes.items():
            box.bgcolor = ft.Colors.SECONDARY_CONTAINER if name == capability else None

    def _clear_highlight(self) -> None:
        for box in self._boxes.values():
            box.bgcolor = None

    # ------------------------------------------------------------------ handlers

    def _on_allow_env(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.allow_env = bool(e.control.value)
        self._clear_highlight()
        self._on_changed()

    def _on_allow_file(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.allow_file = bool(e.control.value)
        self._clear_highlight()
        self._on_changed()

    def _on_timeout(self, e: ft.Event[ft.TextField]) -> None:
        value = _positive(e.control.value, self._state.settings.timeout_seconds)
        self._state.settings.timeout_seconds = float(value)

    def _on_max_input(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.max_input_mib = int(
            _positive(e.control.value, self._state.settings.max_input_mib))

    def _on_max_lines(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.max_display_lines = int(
            _positive(e.control.value, self._state.settings.max_display_lines))
        self._on_changed()

    def _restore_fields(self, e: ft.Event[ft.TextField]) -> None:
        """空欄や 0 のまま欄を離れたら、実際に使われている値を表示し直す。"""
        s = self._state.settings
        self._timeout.value = str(int(s.timeout_seconds))
        self._max_input.value = str(s.max_input_mib)
        self._max_lines.value = str(s.max_display_lines)

    def _on_dark(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.dark_theme = bool(e.control.value)
        self._page.theme_mode = ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT


def _positive(raw: str | None, fallback: float) -> float:
    """空欄や 0 で設定を壊さないための受け皿。"""
    try:
        value = float(raw or "")
    except ValueError:
        return fallback
    return value if value > 0 else fallback
