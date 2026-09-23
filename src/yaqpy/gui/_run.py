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
from yaqpy.gui._upload import WebUploader
from yaqpy.gui.logo import WINDOW_ICON
from yaqpy.gui.pages.main_page import MainPage
from yaqpy.gui.pages.settings_page import SettingsPage
from yaqpy.gui.state import GuiState, clamp_settings_to_web_limits
from yaqpy.gui.web_assets import is_drop_route
from yaqpy.gui.web_config import WebRuntime

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


async def _main(page: ft.Page, *, initial_path: str | None = None,
                web: WebRuntime | None = None) -> None:
    """1 つの画面（デスクトップの窓、または Web 版のブラウザのタブ 1 つ）を組み立てる。

    Web 版（``web`` あり。v0.6.0）では、この関数がセッション（タブ）ごとに呼ばれる。
    窓の操作・終了ボタン・危険な許可・表示言語の切り替えは出さない（W0・計画書 5-5 節）。
    """
    page.padding = 12
    if web is None:
        page.window.width = 1180
        page.window.height = 880      # 未読込の画面（案内＋貼り付け欄）が収まるように少し広げた
        page.window.min_width = 820
        page.window.min_height = 620
        page.window.icon = str(WINDOW_ICON)     # yaqpy のロゴ（Flet 1.0 では Windows でだけ効く）

    sp = ft.SharedPreferences()             # Web 版ではブラウザ側に保存される（W0）
    page.services.append(sp)

    state = GuiState(web=web.config.limits() if web else None)
    state.settings = await load_settings(sp)   # allow_env / allow_file は既定のまま（U1）
    clamp_settings_to_web_limits(state)        # Web 版：保存値をサーバーの上限まで下げて表示する
    if web is None:
        # 画面を組み立てる前に 1 回だけ（U4）。Web 版はサーバーの起動時に 1 回だけ選ぶ
        # （texts はプロセスで共有されるので、タブごとに選ぶと文言が混ざる）。
        texts.select_language(state.settings.language)
    page.title = texts.APP_TITLE
    presenter = make_presenter(state, run_gate=web.gate if web else None)

    picker = ft.FilePicker()
    page.services.append(picker)           # Flet 1.0: overlay ではなく services
    uploader = (WebUploader(page=page, picker=picker, upload_dir=web.upload_dir)
                if web else None)

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
                         on_open_settings=go_to_settings, uploader=uploader)
    settings_page = SettingsPage(page=page, state=state,
                                 on_changed=lambda: page.run_task(main_page.rerun),
                                 on_persist=persist_settings)
    pages = [main_page, settings_page]

    def ask_quit(e: ft.Event) -> None:
        """要望：終了ボタンはワンクリックで閉じず、確認を挟む。"""

        def cancel(_: ft.Event) -> None:
            page.pop_dialog()

        async def confirm(_: ft.Event) -> None:
            page.pop_dialog()
            # 窓の × と同じ経路（page.window.close() → prevent_close → on_window_event）で終了する。
            await page.window.close()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(texts.DLG_QUIT_TITLE),
            actions=[
                ft.TextButton(content=texts.DLG_QUIT_CANCEL, on_click=cancel, autofocus=True),
                ft.TextButton(content=texts.DLG_QUIT_OK, on_click=confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    nav_items: list[ft.Control] = [
        ft.TextButton(content=nav_texts[0], on_click=lambda e: show(0)),
        ft.TextButton(content=nav_texts[1], on_click=lambda e: show(1)),
    ]
    if web is None:
        # Web 版には閉じる窓が無い（タブを閉じればよい。サーバーは起動した端末で Ctrl+C）
        nav_items += [
            ft.Container(expand=True),
            ft.IconButton(icon=ft.Icons.POWER_SETTINGS_NEW, icon_color=ft.Colors.ERROR,
                          tooltip=texts.BTN_QUIT, on_click=ask_quit),
        ]
    nav_bar = ft.Container(
        content=ft.Row(nav_items, alignment=ft.MainAxisAlignment.START),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )

    async def on_window_event(e: ft.WindowEvent) -> None:
        if e.type != ft.WindowEventType.CLOSE:
            return
        presenter.cancel()                    # 走っている評価を協調的に止める（リスク R9）
        await page.window.destroy()
        if sys.platform == "win32":
            # flet.exe が生き残る既知の不具合（_terminate_process_tree）への対処。macOS / Linux
            # ではこの不具合は報告されておらず、taskkill は Windows 専用コマンドなので他 OS では
            # 呼ばない（U4。実機未確認のため、既知の不具合が無い前提でこの対処に限定する）。
            await asyncio.sleep(CLOSE_GRACE_SECONDS)
            _terminate_process_tree()

    if web is None:
        # 窓を閉じたときに評価を止めてから終了させる。`page.window.on_event` は OS を問わない
        # Flet の API（実測は Windows のみ。macOS / Linux は動作未確認。U4）。
        page.window.prevent_close = True
        page.window.on_event = on_window_event

    def on_close(e: ft.Event) -> None:
        presenter.cancel()                    # セッションが破棄されるときの保険
        if uploader is not None:
            uploader.cleanup()                # Web 版：このタブが受け取ったものを残さない

    page.on_close = on_close

    if web is not None:
        async def on_route_change(e: ft.RouteChangeEvent) -> None:
            """ファイルのドロップ（``yaqpy-drop.js``）の通知。Main 画面に切り替えて開く。"""
            if not is_drop_route(e.route):
                return
            await page.push_route("/")          # 通知用のルートを URL に残さない
            show(0)
            page.update()
            await main_page.add_dropped_files()

        page.on_route_change = on_route_change
    page.theme_mode = ft.ThemeMode.DARK if state.settings.dark_theme else ft.ThemeMode.LIGHT

    show(0)
    page.add(content, nav_bar)
    if initial_path:
        # yaqpy --gui a.yaml（U2）。add() の後で走らせ、画面が組み上がってから開く。
        page.run_task(main_page.open_startup_file, initial_path)


def run_app(*, initial_path: str | None = None) -> None:
    async def main(page: ft.Page) -> None:
        await _main(page, initial_path=initial_path)

    ft.run(main)
