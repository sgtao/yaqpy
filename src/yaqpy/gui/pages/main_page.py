"""メイン画面：左に原文、右に変換結果。

Flet 1.0 の実測（``docs/flet-1.0-api-notes.md``）に従う点：

* ``async def`` ハンドラの途中で ``page.update()`` を呼んだら、**終了時にも呼ぶ**
  （呼ばないと最終状態が画面に反映されない）。
* ``Dropdown`` に ``on_change`` は無い。選択は ``on_select``。
"""

from __future__ import annotations

import asyncio

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import input_format_choices, output_format_choices
from yaqpy.gui.errors_ja import caret_line
from yaqpy.gui.paths import DEFAULT_MAX_ITEMS, PathCandidate
from yaqpy.gui.presenter import MainPresenter, RunViewModel, ValidationViewModel
from yaqpy.gui.state import GuiState

VALIDATE_DEBOUNCE_SECONDS = 0.3
MONO = ft.TextStyle(font_family="Consolas", size=12)
# props は出力専用（デコーダが無い）なので、開くダイアログには出さない。
OPEN_EXTENSIONS = ["yaml", "yml", "json", "toon"]


def _options(names: list[str]) -> list[ft.DropdownOption]:
    return [ft.DropdownOption(key=n, text=n) for n in names]


class MainPage:
    def __init__(self, *, page: ft.Page, presenter: MainPresenter, state: GuiState,
                 picker: ft.FilePicker) -> None:
        self._page = page
        self._p = presenter
        self._state = state
        self._picker = picker
        self._rerun_requested = False
        self._validate_token = 0

        # --- ファイルバー ---
        self._file_label = ft.Text(texts.MSG_NO_DOCUMENT, size=12, selectable=True)
        self._close_button = ft.Button(content=texts.BTN_CLOSE, icon=ft.Icons.CLOSE,
                                       on_click=self._on_close, disabled=True)

        # --- 形式バー ---
        self._input_dd = ft.Dropdown(label=texts.LBL_INPUT_FORMAT, width=170,
                                     value=state.query.input_format,
                                     options=_options(input_format_choices()),
                                     on_select=self._on_input_format)
        self._output_dd = ft.Dropdown(label=texts.LBL_OUTPUT_FORMAT, width=170,
                                      value=state.query.output_format,
                                      options=_options(output_format_choices()),
                                      on_select=self._on_output_format)
        self._indent_field = ft.TextField(label=texts.LBL_INDENT, width=110,
                                          value=str(state.query.indent),
                                          input_filter=ft.NumbersOnlyInputFilter(),
                                          on_change=self._on_indent)
        self._pretty_switch = ft.Switch(label=texts.LBL_PRETTY, value=state.query.pretty_print,
                                        on_change=self._on_pretty)

        # --- プロパティ行（G2）---
        # 絞り込みは Flet 組み込みの enable_filter に任せる（G0 の実測）。
        # on_text_change で options を差し替えると、キーボードフォーカスが外れて 2 文字目以降が
        # 打てなくなるため、options は候補の全件を一度だけ入れて触らない。
        self._property_dd = ft.Dropdown(
            label=texts.LBL_PROPERTY,
            editable=True,
            enable_filter=True,
            expand=True,
            options=[],
            on_select=self._on_property_select,
            disabled=True,
        )
        self._add_button = ft.Button(content=texts.BTN_ADD_TO_EXPR, icon=ft.Icons.ADD,
                                     on_click=self._on_add_to_expression, disabled=True)
        self._candidate_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)
        self._selected_candidate = ""

        # --- 式バー ---
        self._expr_field =ft.TextField(label=texts.LBL_EXPRESSION, value=state.query.expression,
                                        hint_text=texts.PH_EXPRESSION, expand=True,
                                        text_style=MONO,
                                        on_change=self._on_expression_change,
                                        on_submit=self._on_run)
        self._expr_error = ft.Text("", color=ft.Colors.ERROR, size=12, selectable=True,
                                   visible=False, font_family="Consolas")
        self._run_button = ft.Button(content=texts.BTN_RUN, icon=ft.Icons.PLAY_ARROW,
                                     on_click=self._on_run, disabled=True)
        self._cancel_button = ft.Button(content=texts.BTN_CANCEL, icon=ft.Icons.STOP,
                                        on_click=self._on_cancel, disabled=True)
        self._progress = ft.ProgressBar(visible=False)

        # --- 2 ペイン ---
        self._original = ft.TextField(multiline=True, read_only=True, expand=True,
                                      text_style=MONO, border=ft.OutlineInputBorder())
        self._converted = ft.TextField(multiline=True, read_only=True, expand=True,
                                       text_style=MONO, border=ft.OutlineInputBorder())
        self._truncated_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)

        # --- 状態バー ---
        self._status_icon = ft.Icon(icon=ft.Icons.INFO_OUTLINE, size=16)
        self._status_text = ft.Text("", size=12, selectable=True)
        self._format_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        self._root = self._build()

    # ------------------------------------------------------------------ 組み立て

    @property
    def control(self) -> ft.Control:
        return self._root

    def _build(self) -> ft.Control:
        file_bar = ft.Row([
            ft.Button(content=texts.BTN_OPEN, icon=ft.Icons.FOLDER_OPEN, on_click=self._on_open),
            self._file_label,
            self._close_button,
        ], alignment=ft.MainAxisAlignment.START, spacing=12)

        format_bar = ft.Row([self._input_dd, self._output_dd, self._indent_field,
                             self._pretty_switch], spacing=12)

        filter_bar = ft.Column([
            ft.Row([self._property_dd, self._add_button], spacing=8),
            self._candidate_note,
            ft.Row([self._expr_field, self._run_button, self._cancel_button], spacing=8),
            self._expr_error,
        ], spacing=2)

        # 複数行 TextField は内容の高さになるので、スクロールする Column で包む。
        # こうすると窓の高さを使い切り、長い文書は枠の中でスクロールする。
        panes = ft.Row([
            ft.Column([ft.Text(texts.LBL_ORIGINAL, size=12, weight=ft.FontWeight.W_600),
                       ft.Column([self._original], scroll=ft.ScrollMode.AUTO, expand=True)],
                      expand=True, spacing=4),
            ft.Column([ft.Text(texts.LBL_CONVERTED, size=12, weight=ft.FontWeight.W_600),
                       ft.Column([self._converted, self._truncated_note],
                                 scroll=ft.ScrollMode.AUTO, expand=True)],
                      expand=True, spacing=4),
        ], expand=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

        status_bar = ft.Row([self._status_icon, self._status_text,
                             ft.Container(expand=True), self._format_text], spacing=8)

        return ft.Column([file_bar, ft.Divider(height=1), format_bar, filter_bar,
                          self._progress, panes, ft.Divider(height=1), status_bar],
                         expand=True, spacing=8)

    # ------------------------------------------------------------------ 操作

    async def _on_open(self, e: ft.Event[ft.Button]) -> None:
        files = await self._picker.pick_files(
            dialog_title=texts.BTN_OPEN,
            allow_multiple=False,
            allowed_extensions=OPEN_EXTENSIONS,
        )
        if files:
            await self._load(files[0].path)
        self._page.update()                 # async ハンドラは終了時にも update する

    async def _load(self, path: str) -> None:
        vm = await self._p.open_path(path)
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._original.value = vm.original_text
        self._file_label.value = f"{vm.name}  ({vm.byte_size:,} B)"
        self._file_label.tooltip = vm.path or ""
        self._expr_field.value = self._state.query.expression
        self._expr_field.error = None
        self._close_button.disabled = False
        self._run_button.disabled = False
        self._expr_error.visible = False
        await self._run()
        await self._reload_candidates()

    def _on_close(self, e: ft.Event[ft.Button]) -> None:
        self._p.close_document()
        self._original.value = ""
        self._converted.value = ""
        self._file_label.value = texts.MSG_NO_DOCUMENT
        self._file_label.tooltip = ""
        self._expr_field.value = "."
        self._expr_field.error = None
        self._expr_error.visible = False
        self._close_button.disabled = True
        self._run_button.disabled = True
        self._truncated_note.visible = False
        self._property_dd.options = []
        self._property_dd.value = None
        self._property_dd.disabled = True
        self._add_button.disabled = True
        self._candidate_note.visible = False
        self._selected_candidate = ""
        self._status_icon.icon = ft.Icons.INFO_OUTLINE
        self._status_icon.color = None
        self._status_text.value = ""
        self._format_text.value = ""

    def _on_input_format(self, e: ft.Event[ft.Dropdown]) -> None:
        self._state.query.input_format = e.control.value or "auto"
        # 入力形式を直すと、壊れていた文書が読めるようになることがある。候補も作り直す。
        self._page.run_task(self._run_and_reload_candidates)

    def _on_output_format(self, e: ft.Event[ft.Dropdown]) -> None:
        self._state.query.output_format = e.control.value or "auto"
        self._page.run_task(self._run)

    def _on_indent(self, e: ft.Event[ft.TextField]) -> None:
        try:
            self._state.query.indent = max(0, int(e.control.value or "2"))
        except ValueError:
            return
        self._page.run_task(self._run)

    def _on_pretty(self, e: ft.Event[ft.Switch]) -> None:
        self._state.query.pretty_print = bool(e.control.value)
        self._page.run_task(self._run)

    def _on_expression_change(self, e: ft.Event[ft.TextField]) -> None:
        """入力中は検証だけ（再実行はしない）。最後の打鍵から 300 ms 後に 1 回だけ走る。"""
        self._state.query.expression = e.control.value or ""
        self._validate_token += 1
        token = self._validate_token

        async def later() -> None:
            await asyncio.sleep(VALIDATE_DEBOUNCE_SECONDS)
            if token != self._validate_token:
                return                       # もっと新しい入力が来たので捨てる
            self._apply_validation(self._p.validate(self._state.query.expression))
            self._page.update()

        self._page.run_task(later)

    def _apply_validation(self, result: ValidationViewModel) -> None:
        if result.valid:
            self._expr_field.error = None
            self._expr_error.visible = False
            return
        # メッセージは入力欄の赤枠に出るので、下段には「式＋下線」だけを出す（二重表示を避ける）。
        self._expr_field.error = result.message
        caret = caret_line(result.position)
        self._expr_error.value = f"{self._state.query.expression}\n{caret}" if caret else ""
        self._expr_error.visible = bool(caret)

    # ------------------------------------------------------------------ プロパティ候補（G2）

    async def _run_and_reload_candidates(self) -> None:
        await self._run()
        await self._reload_candidates()
        self._page.update()

    async def _reload_candidates(self) -> None:
        vm = await self._p.build_candidates()
        self._set_candidates(self._p.filter_candidates(limit=DEFAULT_MAX_ITEMS))
        self._property_dd.value = None
        self._selected_candidate = ""
        self._property_dd.disabled = vm.is_empty
        self._add_button.disabled = vm.is_empty
        if vm.note:
            self._candidate_note.value = vm.note
            self._candidate_note.visible = True
        elif vm.truncated:
            self._candidate_note.value = texts.MSG_TOO_MANY_CANDIDATES
            self._candidate_note.visible = True
        else:
            self._candidate_note.visible = False

    def _set_candidates(self, candidates: list[PathCandidate]) -> None:
        self._property_dd.options = [
            ft.DropdownOption(key=c.expression, text=c.label) for c in candidates
        ]

    def _on_property_select(self, e: ft.Event[ft.Dropdown]) -> None:
        """一覧から選んだとき。式欄を置き換えてすぐ実行する（式欄が唯一の真実）。"""
        expression = e.control.value or ""
        if not expression:
            return
        self._selected_candidate = expression
        self._expr_field.value = self._p.apply_candidate(expression)
        self._expr_field.error = None
        self._expr_error.visible = False
        self._page.run_task(self._run)

    def _on_add_to_expression(self, e: ft.Event[ft.Button]) -> None:
        expression = self._selected_candidate or (self._property_dd.value or "")
        if not expression:
            return
        self._expr_field.value = self._p.apply_candidate(expression, append=True)
        self._expr_field.error = None
        self._expr_error.visible = False
        self._page.run_task(self._run)

    async def _on_run(self, e: ft.Event) -> None:
        self._validate_token += 1            # 走りかけのデバウンスを無効化
        self._apply_validation(self._p.validate(self._state.query.expression))
        await self._run()

    def _on_cancel(self, e: ft.Event[ft.Button]) -> None:
        self._p.cancel()

    # ------------------------------------------------------------------ 実行

    async def _run(self) -> None:
        """実行する。実行中に再要求が来たら、いまの実行が終わってからもう 1 回だけ実行する。

        こうしないと、実行中に形式を切り替えたときに古い設定の結果が画面に残る。
        """
        if not self._state.document.is_loaded:
            return
        if self._state.running:
            self._rerun_requested = True
            return
        while True:
            self._rerun_requested = False
            self._set_running(True)
            self._page.update()             # 実行前に「実行中」を見せる
            vm = await self._p.run()
            self._set_running(False)
            self._apply(vm)
            self._page.update()             # 実行後にも update する（Flet 1.0 の実測）
            if not self._rerun_requested:
                return

    def _set_running(self, running: bool) -> None:
        self._progress.visible = running
        self._run_button.disabled = running
        self._cancel_button.disabled = not running
        if running:
            self._status_icon.icon = ft.Icons.HOURGLASS_TOP
            self._status_icon.color = None
            self._status_text.value = texts.MSG_RUNNING
            self._status_text.color = ft.Colors.ON_SURFACE

    def _apply(self, vm: RunViewModel) -> None:
        if not vm.ok:
            self._converted.value = ""
            self._truncated_note.visible = False
            self._format_text.value = ""
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._converted.value = vm.display_text
        self._truncated_note.visible = vm.truncated_lines > 0
        self._truncated_note.value = texts.MSG_TRUNCATED.format(n=f"{vm.truncated_lines:,}")
        # ドロップダウンは「auto」のまま。判定結果は右下に出す。
        self._format_text.value = f"{vm.input_format} → {vm.output_format}"
        self._status_icon.icon = ft.Icons.CHECK_CIRCLE_OUTLINE
        self._status_icon.color = ft.Colors.GREEN
        self._status_text.color = ft.Colors.ON_SURFACE
        self._status_text.value = (f"{vm.document_count} document / {vm.elapsed_ms:.1f} ms / "
                                   f"出力 {len(vm.full_text.encode('utf-8')):,} bytes")

    def _show_error(self, message: str, hint: str = "") -> None:
        self._status_icon.icon = ft.Icons.ERROR_OUTLINE
        self._status_icon.color = ft.Colors.ERROR
        self._status_text.color = ft.Colors.ERROR
        self._status_text.value = f"{message}（{hint}）" if hint else message
