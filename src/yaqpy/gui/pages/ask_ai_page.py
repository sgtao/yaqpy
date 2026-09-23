"""「AI に相談」画面（v0.7.0）。CLI の ``--guide-prompt`` を、組み立てながら使える形にした画面。

左に「あなたの入力（データ例・やりたい変換）」、右に「AI への相談文」。左の入力は
[＋プロンプトに反映] を押したときだけ右へ差し込む（一方向。``gui/ask_ai.py``）。
相談文は表示したときに 1 回だけ作る（例の実行を含むので、開くたびには作らない）。
"""

from __future__ import annotations

import asyncio

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui.ask_ai import apply_user_input
from yaqpy.gui.pages.clipboard import get_clipboard, set_clipboard
from yaqpy.gui.presenter import MainPresenter

MONO = ft.TextStyle(font_family="Consolas", size=12)
COPY_FEEDBACK_SECONDS = 1.5      # ボタン文字を「コピーしました！」に変えておく時間


class AskAiPage:
    def __init__(self, *, page: ft.Page, presenter: MainPresenter) -> None:
        self._page = page
        self._p = presenter
        self._initial_prompt = ""            # 「初期状態に戻す」で使う、作りたての相談文
        self._loaded = False

        self._user_input = ft.TextField(
            multiline=True, expand=True, text_style=MONO, border=ft.OutlineInputBorder(),
            hint_text=texts.PH_ASK_AI_INPUT, min_lines=8)
        self._prompt = ft.TextField(
            multiline=True, expand=True, text_style=MONO, border=ft.OutlineInputBorder(),
            hint_text=texts.MSG_PROMPT_LOADING, min_lines=8)
        self._copy_button = ft.Button(content=texts.BTN_COPY, icon=ft.Icons.CONTENT_COPY,
                                      on_click=self._on_copy)

        left_buttons = ft.Row([
            ft.Button(content=texts.BTN_PASTE, icon=ft.Icons.CONTENT_PASTE,
                      on_click=self._on_paste),
            ft.Button(content=texts.BTN_CLEAR, icon=ft.Icons.CLEAR, on_click=self._on_clear_input),
            ft.Button(content=texts.BTN_APPLY_TO_PROMPT, icon=ft.Icons.ARROW_FORWARD,
                      on_click=self._on_apply),
        ], spacing=8, wrap=True)
        right_buttons = ft.Row([
            ft.Button(content=texts.BTN_CLEAR, icon=ft.Icons.CLEAR, on_click=self._on_clear_prompt),
            ft.Button(content=texts.BTN_RESET_PROMPT, icon=ft.Icons.RESTART_ALT,
                      on_click=self._on_reset),
            self._copy_button,
        ], spacing=8, wrap=True)

        self._root = ft.Column([
            ft.Text(texts.ASK_AI_TITLE, size=20, weight=ft.FontWeight.BOLD),
            ft.Text(texts.ASK_AI_HINT, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([
                ft.Column([ft.Text(texts.LBL_ASK_AI_INPUT, size=12, weight=ft.FontWeight.W_600),
                           self._user_input, left_buttons], expand=True, spacing=6),
                ft.Column([ft.Text(texts.LBL_ASK_AI_PROMPT, size=12, weight=ft.FontWeight.W_600),
                           self._prompt, right_buttons], expand=True, spacing=6),
            ], expand=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        ], expand=True, spacing=8)

    @property
    def control(self) -> ft.Control:
        return self._root

    async def on_show(self) -> None:
        """この画面に切り替わったとき。相談文を、最初の 1 回だけ作る。"""
        if self._loaded:
            return
        self._loaded = True
        await self._load_initial_prompt()
        self._page.update()

    async def _load_initial_prompt(self) -> None:
        self._initial_prompt = await self._p.guide_prompt()
        self._prompt.value = self._initial_prompt
        self._prompt.hint_text = None

    # ------------------------------------------------------------------ 左の欄

    async def _on_paste(self, e: ft.Event[ft.Button]) -> None:
        text = await get_clipboard()
        if text is None:
            self._notify(texts.MSG_PASTE_FAILED)
            return
        self._user_input.value = text
        self._page.update()

    def _on_clear_input(self, e: ft.Event[ft.Button]) -> None:
        self._user_input.value = ""
        self._page.update()

    def _on_apply(self, e: ft.Event[ft.Button]) -> None:
        """左の入力を、右の相談文へ反映する（案内の一文の置き換え。無ければ末尾に追記）。"""
        user_text = self._user_input.value or ""
        if not user_text.strip():
            self._notify(texts.MSG_APPLY_EMPTY)
            return
        self._prompt.value = apply_user_input(self._prompt.value or "", user_text)
        self._page.update()

    # ------------------------------------------------------------------ 右の欄

    def _on_clear_prompt(self, e: ft.Event[ft.Button]) -> None:
        self._prompt.value = ""
        self._page.update()

    async def _on_reset(self, e: ft.Event[ft.Button]) -> None:
        """相談文を、作りたての状態に戻す（編集・反映の内容は捨てる）。"""
        await self._load_initial_prompt()
        self._loaded = True
        self._page.update()

    async def _on_copy(self, e: ft.Event[ft.Button]) -> None:
        if not await set_clipboard(self._prompt.value or ""):
            self._notify(texts.MSG_COPY_FAILED)
            return
        self._copy_button.content = texts.MSG_COPIED_SHORT
        self._page.update()
        await asyncio.sleep(COPY_FEEDBACK_SECONDS)
        self._copy_button.content = texts.BTN_COPY
        self._page.update()

    def _notify(self, message: str) -> None:
        self._page.show_dialog(ft.SnackBar(ft.Text(message)))
        self._page.update()
