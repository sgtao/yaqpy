"""flet を実際に起動する層。ここから先だけが flet に依存する。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import make_presenter
from yaqpy.gui._prefs import load_settings, save_settings
from yaqpy.gui.pages.main_page import MainPage
from yaqpy.gui.pages.settings_page import SettingsPage
from yaqpy.gui.state import GuiState

# 窓を閉じてから、クライアントの後始末を待つ時間（秒）
CLOSE_GRACE_SECONDS = 0.3


def _terminate_process_tree() -> None:
    """自分自身と子プロセス（Flet のクライアント）をまとめて終了させる。

    Flet 1.0.0 の Windows 版では、ファイルダイアログでファイルを選んだあとに窓を閉じても、
    ``flet.exe`` と Python が終了せずに残る（最小の Flet アプリでも再現する）。
    そのため窓の CLOSE イベントで自分から終了させる。``/T`` で子のクライアントも道連れにする。
    """
    subprocess.Popen(
        ["taskkill", "/F", "/T", "/PID", str(os.getpid())],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    os._exit(0)                               # taskkill が間に合わなかったときの保険


async def _main(page: ft.Page) -> None:
    page.title = texts.APP_TITLE
    page.padding = 12
    page.window.width = 1180
    page.window.height = 820
    page.window.min_width = 820
    page.window.min_height = 560

    sp = ft.SharedPreferences()
    page.services.append(sp)

    state = GuiState()
    state.settings = await load_settings(sp)   # allow_env / allow_file は既定のまま（U1）
    presenter = make_presenter(state)

    picker = ft.FilePicker()
    page.services.append(picker)           # Flet 1.0: overlay ではなく services

    def persist_settings() -> None:
        async def _save() -> None:
            await save_settings(sp, state.settings)

        page.run_task(_save)

    content = ft.Container(expand=True)
    nav_labels = [texts.NAV_MAIN, texts.NAV_SETTINGS]
    # ft.ButtonStyle は Flet 1.0 で色を受け取れないので、押しているページは文字の色と太さで示す
    nav_texts = [ft.Text(label) for label in nav_labels]

    def show(index: int) -> None:
        content.content = pages[index].control
        for i, label in enumerate(nav_texts):
            active = i == index
            label.color = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
            label.weight = ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL

    def go_to_settings(capability: str = "") -> None:
        show(1)
        if capability:
            settings_page.focus_capability(capability)
        page.update()

    main_page = MainPage(page=page, presenter=presenter, state=state, picker=picker,
                         on_open_settings=go_to_settings)
    settings_page = SettingsPage(page=page, state=state,
                                 on_changed=lambda: page.run_task(main_page.rerun),
                                 on_persist=persist_settings)
    pages = [main_page, settings_page]

    nav_bar = ft.Container(
        content=ft.Row([
            ft.TextButton(content=nav_texts[0], on_click=lambda e: show(0)),
            ft.TextButton(content=nav_texts[1], on_click=lambda e: show(1)),
        ], alignment=ft.MainAxisAlignment.START),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )

    async def on_window_event(e: ft.WindowEvent) -> None:
        if e.type != ft.WindowEventType.CLOSE:
            return
        presenter.cancel()                    # 走っている評価を協調的に止める（リスク R9）
        await page.window.destroy()
        await asyncio.sleep(CLOSE_GRACE_SECONDS)
        _terminate_process_tree()

    if sys.platform == "win32":
        # 窓を閉じたときに自分で終了させる（理由は _terminate_process_tree）。
        page.window.prevent_close = True
        page.window.on_event = on_window_event

    def on_close(e: ft.Event) -> None:
        presenter.cancel()                    # セッションが破棄されるときの保険（Windows 以外はこちら）

    page.on_close = on_close
    page.theme_mode = ft.ThemeMode.DARK if state.settings.dark_theme else ft.ThemeMode.LIGHT

    show(0)
    page.add(content, nav_bar)


def run_app() -> None:
    ft.run(_main)
