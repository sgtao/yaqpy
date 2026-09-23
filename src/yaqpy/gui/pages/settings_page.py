"""設定画面。値は GuiState.settings に即時反映し、必要なら再実行を依頼する。"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from yaqpy.gui import run_log, texts
from yaqpy.gui.state import GuiState


class SettingsPage:
    def __init__(self, *, page: ft.Page, state: GuiState,
                 on_changed: Callable[[], None],
                 on_persist: Callable[[], None] | None = None,
                 picker: ft.FilePicker | None = None) -> None:
        self._page = page
        self._picker = picker
        self._state = state
        self._on_changed = on_changed
        self._on_persist = on_persist or (lambda: None)
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
        # 言語名はそれ自身の言語で出す（現在の表示言語には合わせない。「日本語」「English」は不変）
        self._language = ft.Dropdown(
            label=texts.LBL_LANGUAGE, width=180, value=s.language,
            options=[ft.DropdownOption(key="ja", text="日本語"),
                    ft.DropdownOption(key="en", text="English")],
            on_select=self._on_language,
        )
        self._language_note = ft.Text(texts.SET_LANGUAGE_NOTE, size=12,
                                      color=ft.Colors.ON_SURFACE_VARIANT)

        # 実行ログ（v0.7.0。デスクトップ版のみ）。保存先は直接入力もできる（フォルダ選択の実機確認が
        # 取れなかったときの代わりにもなる）。空欄は「既定の保存先」
        default_dir = run_log.default_log_dir()
        self._log_enabled = ft.Switch(label=texts.SET_LOG_ENABLED, value=s.log_enabled,
                                      on_change=self._on_log_enabled)
        self._log_dir = ft.TextField(label=texts.SET_LOG_DIR, value=s.log_dir, expand=True,
                                     helper=texts.SET_LOG_DIR_HINT.format(path=default_dir),
                                     on_change=self._on_log_dir)
        self._log_max_files = ft.TextField(label=texts.SET_LOG_MAX_FILES, width=220,
                                           value=str(s.log_max_files),
                                           input_filter=ft.NumbersOnlyInputFilter(),
                                           on_change=self._on_log_max_files,
                                           on_blur=self._restore_fields)
        self._log_max_entry = ft.TextField(label=texts.SET_LOG_MAX_ENTRY, width=220,
                                           value=str(s.log_max_entry_mib),
                                           input_filter=ft.NumbersOnlyInputFilter(),
                                           on_change=self._on_log_max_entry,
                                           on_blur=self._restore_fields)

        note_color = ft.Colors.ON_SURFACE_VARIANT
        web = state.web
        if web is None:
            security: list[ft.Control] = [
                ft.Text(texts.SET_SECURITY_NOTE, size=12, color=note_color),
                ft.Text(texts.SET_SECURITY_WHY, size=12, color=note_color),
                self._boxes["env"],
                self._boxes["file"],
                ft.Text(texts.SET_SYSTEM_NOTE, size=12, color=note_color),
            ]
            run_notes: list[ft.Control] = []
            language: list[ft.Control] = [self._language, self._language_note]
            log_section: list[ft.Control] = [
                ft.Divider(),
                ft.Text(texts.SET_LOG, weight=ft.FontWeight.W_600),
                self._log_enabled,
                ft.Row([self._log_dir,
                        ft.Button(content=texts.BTN_BROWSE, icon=ft.Icons.FOLDER_OPEN,
                                  on_click=self._on_browse_log_dir),
                        ft.Button(content=texts.BTN_RESET_DEFAULT,
                                  on_click=self._on_reset_log_dir)], spacing=8),
                ft.Row([self._log_max_files, self._log_max_entry], spacing=12),
                ft.Text(texts.SET_LOG_NOTE, size=12, color=note_color),
            ]
        else:
            # Web 版（v0.6.0）：危険な許可のスイッチは**出さない**（計画書 5-5 節の 2）。
            # 表示言語はサーバーの起動時に固定（セッションごとに変えると文言が混ざるため）。
            security = [ft.Text(texts.SET_WEB_SECURITY_NOTE, size=12, color=note_color)]
            run_notes = [ft.Text(texts.SET_WEB_LIMITS_NOTE.format(
                mib=f"{web.max_input_bytes / 1024 / 1024:g}",
                seconds=f"{web.timeout_seconds:g}"), size=12, color=note_color)]
            language = [ft.Text(texts.SET_WEB_LANGUAGE_NOTE, size=12, color=note_color)]
            log_section = []                       # Web 版は実行ログを記録しない（利用者のデータを残さない）

        self._root = ft.Column([
            ft.Text(texts.SET_TITLE, size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text(texts.SET_SECURITY, weight=ft.FontWeight.W_600),
            *security,
            ft.Divider(),
            ft.Text(texts.SET_RUN, weight=ft.FontWeight.W_600),
            ft.Row([self._timeout, self._max_input, self._max_lines], spacing=12),
            *run_notes,
            ft.Divider(),
            ft.Text(texts.SET_VIEW, weight=ft.FontWeight.W_600),
            self._dark,
            *language,
            *log_section,
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
        self._on_persist()

    def _on_max_input(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.max_input_mib = int(
            _positive(e.control.value, self._state.settings.max_input_mib))
        self._on_persist()

    def _on_max_lines(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.max_display_lines = int(
            _positive(e.control.value, self._state.settings.max_display_lines))
        self._on_changed()
        self._on_persist()

    def _restore_fields(self, e: ft.Event[ft.TextField]) -> None:
        """空欄や 0 のまま欄を離れたら、実際に使われている値を表示し直す。"""
        s = self._state.settings
        self._timeout.value = str(int(s.timeout_seconds))
        self._max_input.value = str(s.max_input_mib)
        self._max_lines.value = str(s.max_display_lines)
        self._log_max_files.value = str(s.log_max_files)
        self._log_max_entry.value = str(s.log_max_entry_mib)

    def _on_log_enabled(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.log_enabled = bool(e.control.value)
        self._on_persist()

    def _on_log_dir(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.log_dir = (e.control.value or "").strip()
        self._on_persist()

    async def _on_browse_log_dir(self, e: ft.Event[ft.Button]) -> None:
        """保存先のフォルダを選ぶ。``get_directory_path`` は Flet 1.0 で実機確認が取れていない
        （docs/flet-1.0-api-notes.md）ので、失敗したらパスの直接入力を案内する。"""
        chosen: str | None = None
        try:
            if self._picker is None:
                raise RuntimeError("no picker")
            chosen = await self._picker.get_directory_path(
                dialog_title=texts.SET_LOG_DIR,
                initial_directory=self._state.settings.log_dir or None)
        except Exception:                            # noqa: BLE001 - 直接入力に切り替えてもらう
            self._page.show_dialog(ft.SnackBar(ft.Text(texts.MSG_FOLDER_PICK_FAILED)))
            self._page.update()
            return
        if chosen:
            self._set_log_dir(chosen)

    def _on_reset_log_dir(self, e: ft.Event[ft.Button]) -> None:
        self._set_log_dir("")

    def _set_log_dir(self, path: str) -> None:
        self._state.settings.log_dir = path
        self._log_dir.value = path
        self._on_persist()
        self._page.update()

    def _on_log_max_files(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.log_max_files = int(
            _positive(e.control.value, self._state.settings.log_max_files))
        self._on_persist()

    def _on_log_max_entry(self, e: ft.Event[ft.TextField]) -> None:
        self._state.settings.log_max_entry_mib = int(
            _positive(e.control.value, self._state.settings.log_max_entry_mib))
        self._on_persist()

    def _on_dark(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.dark_theme = bool(e.control.value)
        self._page.theme_mode = ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT
        self._on_persist()

    def _on_language(self, e: ft.Event[ft.Dropdown]) -> None:
        """次回の起動から効く（画面の文字は作り直さないと変わらないため。U4）。"""
        self._state.settings.language = e.control.value or self._state.settings.language
        self._on_persist()


def _positive(raw: str | None, fallback: float) -> float:
    """空欄や 0 で設定を壊さないための受け皿。"""
    try:
        value = float(raw or "")
    except ValueError:
        return fallback
    return value if value > 0 else fallback
