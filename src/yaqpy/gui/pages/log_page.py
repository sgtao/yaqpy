"""ログ画面（v0.7.0。デスクトップ版のみ）。実行ログの一覧・詳細・再実行・削除・式の保存。

左に一覧（新しい順）、右に選んだログの入力・式・全文。一覧はファイル名から作り、選んだときに
初めてファイルを読む。絞り込みの式・入力ファイル名は、ファイルの先頭部分を読んでから照合する。
業務ロジックは ``gui/log_presenter.py``。ここは見せるだけ。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

import flet as ft

from yaqpy.gui import expression_file, texts
from yaqpy.gui.log_presenter import LogDetail, LogPresenter, LogRow, RerunPayload

FILTER_DEBOUNCE_SECONDS = 0.3      # 式欄の検証と同じ
MONO = ft.TextStyle(font_family="Consolas", size=12)
LIST_WIDTH = 300


class LogPage:
    def __init__(self, *, page: ft.Page, presenter: LogPresenter, picker: ft.FilePicker,
                 on_rerun: Callable[[RerunPayload, bool], Awaitable[None]]) -> None:
        self._page = page
        self._p = presenter
        self._picker = picker
        self._on_rerun = on_rerun
        self._rows: list[LogRow] = []
        self._selected: str = ""
        self._detail: LogDetail | None = None
        self._filter_token = 0

        self._search = ft.TextField(label=texts.LBL_LOG_SEARCH, prefix_icon=ft.Icons.SEARCH,
                                    expand=True, dense=True, on_change=self._on_search)
        self._list = ft.ListView(expand=True, spacing=2)
        self._empty_note = ft.Text(texts.MSG_LOG_EMPTY, size=12,
                                   color=ft.Colors.ON_SURFACE_VARIANT)

        self._input_line = ft.Text("", size=13, weight=ft.FontWeight.W_600, selectable=True)
        self._expr_line = ft.Text("", size=12, font_family="Consolas", selectable=True)
        self._notice = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False, selectable=True)
        self._full = ft.TextField(multiline=True, read_only=True, expand=True, text_style=MONO,
                                  border=ft.OutlineInputBorder(), value=texts.MSG_LOG_SELECT)
        self._truncated_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)
        self._rerun_button = ft.Button(content=texts.BTN_LOG_RERUN, icon=ft.Icons.PLAY_ARROW,
                                       on_click=self._on_rerun_click, disabled=True)
        self._save_button = ft.Button(content=texts.BTN_LOG_SAVE_EXPR, icon=ft.Icons.SAVE_ALT,
                                      on_click=self._on_save_expression, disabled=True)
        self._delete_button = ft.Button(content=texts.BTN_LOG_DELETE, icon=ft.Icons.DELETE_OUTLINE,
                                        on_click=self._on_delete_click, disabled=True)
        self._status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True)

        toolbar = ft.Row([
            self._search,
            ft.IconButton(icon=ft.Icons.REFRESH, tooltip=texts.TIP_LOG_REFRESH,
                          on_click=self._on_refresh),
            ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip=texts.TIP_LOG_OPEN_FOLDER,
                          on_click=self._on_open_folder),
            ft.IconButton(icon=ft.Icons.DELETE_SWEEP_OUTLINED, tooltip=texts.TIP_LOG_DELETE_ALL,
                          icon_color=ft.Colors.ERROR, on_click=self._on_delete_all_click),
        ], spacing=4)
        left = ft.Container(content=ft.Column([self._list, self._empty_note], spacing=4,
                                              expand=True), width=LIST_WIDTH)
        right = ft.Column([
            ft.Row([ft.Text(texts.LBL_LOG_INPUT, size=13), self._input_line], spacing=4, wrap=True),
            ft.Row([ft.Text(texts.LBL_LOG_EXPRESSION, size=13), self._expr_line], spacing=4,
                   wrap=True),
            self._notice,
            self._full,
            self._truncated_note,
            ft.Row([self._rerun_button, self._save_button, self._delete_button], spacing=8,
                   wrap=True),
        ], expand=True, spacing=6)
        self._root = ft.Column([toolbar, ft.Row([left, right], expand=True, spacing=12,
                                                vertical_alignment=ft.CrossAxisAlignment.STRETCH),
                                ft.Divider(height=1), self._status], expand=True, spacing=8)

    @property
    def control(self) -> ft.Control:
        return self._root

    # ------------------------------------------------------------------ 一覧

    async def on_show(self) -> None:
        """タブを開いたとき：一覧を読み直す（ファイル名の走査だけなので軽い）。"""
        await self._reload()
        self._page.update()

    async def _reload(self) -> None:
        self._p.refresh()
        await self._apply_filter()

    async def _apply_filter(self) -> None:
        query = self._search.value or ""
        if query.strip() and self._p.pending_heads():
            self._render(self._p.filter(query))          # まず名前で絞ったものを見せる
            self._page.update()
            await self._p.load_heads()                   # 式・入力ファイル名のために先頭を読む
        self._render(self._p.filter(query))

    def _render(self, rows: list[LogRow]) -> None:
        self._rows = rows
        self._list.controls = [self._tile(row) for row in rows]
        self._empty_note.visible = not rows
        self._empty_note.value = texts.MSG_LOG_EMPTY if self._p.total == 0 else texts.MSG_LOG_NO_MATCH
        self._status.value = texts.MSG_LOG_STATUS.format(total=self._p.total, shown=len(rows),
                                                         path=self._p.directory)
        if self._selected and not any(r.file.path == self._selected for r in rows):
            self._clear_detail()

    def _tile(self, row: LogRow) -> ft.Control:
        return ft.ListTile(title=ft.Text(row.title, size=13),
                           subtitle=ft.Text(row.subtitle, size=12),
                           selected=(row.file.path == self._selected), dense=True,
                           on_click=self._select_handler(row.file.path))

    def _select_handler(self, path: str) -> Callable[[ft.Event], None]:
        def handler(e: ft.Event) -> None:
            self._page.run_task(self._select, path)
        return handler

    def _on_search(self, e: ft.Event[ft.TextField]) -> None:
        """入力のたびに（300 ms のデバウンス）絞り込む。"""
        self._filter_token += 1
        token = self._filter_token

        async def later() -> None:
            await asyncio.sleep(FILTER_DEBOUNCE_SECONDS)
            if token != self._filter_token:
                return
            await self._apply_filter()
            self._page.update()

        self._page.run_task(later)

    async def _on_refresh(self, e: ft.Event[ft.IconButton]) -> None:
        await self._reload()
        self._page.update()

    def _on_open_folder(self, e: ft.Event[ft.IconButton]) -> None:
        try:
            self._p.open_folder()
        except Exception as ex:                        # noqa: BLE001 - 理由を出す
            self._snack(texts.MSG_LOG_FOLDER_FAILED.format(reason=str(ex) or type(ex).__name__))

    # ------------------------------------------------------------------ 詳細

    async def _select(self, path: str) -> None:
        self._selected = path
        detail = await self._p.read_detail(path)
        if self._selected != path:                     # 読んでいる間に別のものが選ばれた
            return
        self._detail = detail
        if detail.error and detail.parsed is None:
            self._clear_detail(keep_selection=True)
            self._notice.value = texts.MSG_LOG_READ_FAILED.format(reason=detail.error)
            self._notice.visible = True
            self._delete_button.disabled = False           # 読めないログも消せるように
        else:
            self._show_detail(detail)
        self._render(self._rows)
        self._page.update()

    def _show_detail(self, detail: LogDetail) -> None:
        self._input_line.value = detail.input_summary
        self._expr_line.value = detail.expression
        broken = detail.parsed is not None and not detail.parsed.ok
        self._notice.value = texts.MSG_LOG_BROKEN.format(reason=detail.error) if broken else ""
        self._notice.visible = broken
        self._full.value = detail.display_text
        self._truncated_note.visible = detail.truncated_lines > 0
        self._truncated_note.value = texts.MSG_TRUNCATED.format(n=f"{detail.truncated_lines:,}")
        self._rerun_button.disabled = not detail.can_rerun
        self._save_button.disabled = not detail.can_save_expression
        self._delete_button.disabled = False

    def _clear_detail(self, *, keep_selection: bool = False) -> None:
        if not keep_selection:
            self._selected = ""
        self._detail = None
        self._input_line.value = ""
        self._expr_line.value = ""
        self._notice.visible = False
        self._full.value = texts.MSG_LOG_SELECT
        self._truncated_note.visible = False
        self._rerun_button.disabled = True
        self._save_button.disabled = True
        self._delete_button.disabled = True

    # ------------------------------------------------------------------ 再実行（7-5 節）

    async def _on_rerun_click(self, e: ft.Event[ft.Button]) -> None:
        detail = self._detail
        if detail is None:
            return
        payload = await self._p.build_rerun(detail)
        if isinstance(payload, str):
            self._snack(payload)
            return
        if payload.needs_replace_confirmation:
            self._confirm(texts.DLG_LOG_REPLACE_TITLE, texts.DLG_LOG_REPLACE_BODY,
                          texts.BTN_REPLACE_RERUN, lambda: self._rerun(payload, True))
            return
        await self._rerun(payload, False)

    async def _rerun(self, payload: RerunPayload, replace: bool) -> None:
        await self._on_rerun(payload, replace)

    # ------------------------------------------------------------------ 式を .yaqpy に保存（7-6 節）

    async def _on_save_expression(self, e: ft.Event[ft.Button]) -> None:
        detail = self._detail
        if detail is None:
            return
        path = await self._picker.save_file(
            dialog_title=texts.BTN_LOG_SAVE_EXPR, file_name=self._p.default_expression_name(detail),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=[expression_file.EXTENSION.lstrip(".")])
        if not path:
            return
        try:
            saved = await self._p.save_expression(detail, path)
        except Exception as ex:                        # noqa: BLE001 - 理由を出す
            self._snack(str(ex) or type(ex).__name__)
            return
        self._snack(texts.MSG_EXPR_SAVED.format(path=saved))

    # ------------------------------------------------------------------ 削除（決定 N）

    def _on_delete_click(self, e: ft.Event[ft.Button]) -> None:
        path = self._selected
        if not path:
            return
        self._confirm(texts.DLG_LOG_DELETE_TITLE,
                      texts.DLG_LOG_DELETE_BODY.format(name=os.path.basename(path)),
                      texts.BTN_DELETE_OK, lambda: self._delete_one(path))

    async def _delete_one(self, path: str) -> None:
        if self._p.delete(path):
            self._snack(texts.MSG_LOG_DELETED)
        self._clear_detail()
        await self._reload()
        self._page.update()

    def _on_delete_all_click(self, e: ft.Event[ft.IconButton]) -> None:
        total = self._p.total
        if total == 0:
            return
        self._confirm(texts.DLG_LOG_DELETE_ALL_TITLE, texts.DLG_LOG_DELETE_ALL_BODY.format(n=total),
                      texts.BTN_DELETE_OK, self._delete_all)

    async def _delete_all(self) -> None:
        removed = self._p.delete_all()
        self._snack(texts.MSG_LOG_DELETED_ALL.format(n=removed))
        self._clear_detail()
        await self._reload()
        self._page.update()

    # ------------------------------------------------------------------ 共通

    def _confirm(self, title: str, body: str, ok_label: str,
                 action: Callable[[], Awaitable[None]]) -> None:
        """確認ダイアログ。既定の操作は「やめる」。"""

        def cancel(_: ft.Event) -> None:
            self._page.pop_dialog()

        async def proceed(_: ft.Event) -> None:
            self._page.pop_dialog()
            await action()

        self._page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text(title), content=ft.Text(body, selectable=True),
            actions=[ft.TextButton(content=texts.BTN_DIALOG_CANCEL, on_click=cancel, autofocus=True),
                     ft.TextButton(content=ok_label, on_click=proceed)],
            actions_alignment=ft.MainAxisAlignment.END))

    def _snack(self, message: str) -> None:
        self._page.show_dialog(ft.SnackBar(ft.Text(message)))
        self._page.update()
