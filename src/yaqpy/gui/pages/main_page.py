"""メイン画面：左に原文、右に変換結果。

Flet 1.0 の実測（``docs/flet-1.0-api-notes.md``）に従う点：

* ``async def`` ハンドラの途中で ``page.update()`` を呼んだら、**終了時にも呼ぶ**
  （呼ばないと最終状態が画面に反映されない）。
* ``Dropdown`` に ``on_change`` は無い。選択は ``on_select``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import extension_for, input_format_choices, output_format_choices
from yaqpy.gui.errors_ja import caret_line
from yaqpy.gui.paths import DEFAULT_MAX_ITEMS, PathCandidate
from yaqpy.gui.presenter import MainPresenter, RunViewModel, ValidationViewModel
from yaqpy.gui.state import GuiState

VALIDATE_DEBOUNCE_SECONDS = 0.3
PASTE_DEBOUNCE_SECONDS = 0.3
PASTE_MIN_LINES = 10             # 未読込のあいだの貼り付け欄の高さ
PANE_HEADER_HEIGHT = 44         # 右見出しの保存ボタンに高さを合わせ、左右の枠の上端を揃える
MONO = ft.TextStyle(font_family="Consolas", size=12)
# props は出力専用（デコーダが無い）なので、開くダイアログには出さない。
OPEN_EXTENSIONS = ["yaml", "yml", "json", "toon"]


def _options(names: list[str]) -> list[ft.DropdownOption]:
    return [ft.DropdownOption(key=n, text=n) for n in names]


class MainPage:
    def __init__(self, *, page: ft.Page, presenter: MainPresenter, state: GuiState,
                 picker: ft.FilePicker,
                 on_open_settings: Callable[[str], None] | None = None) -> None:
        self._on_open_settings = on_open_settings
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
        # 未読込のあいだは貼り付け欄として編集可にする（ドロップが使えない環境の保険）
        self._original = ft.TextField(multiline=True, expand=True, text_style=MONO,
                                      border=ft.OutlineInputBorder())
        # G0 の判定は「v1 はドロップ見送り」。領域は作らず、代わりにクリックで開ける案内を出す。
        self._drop_hint = ft.Container(
            content=ft.Column([
                ft.Icon(icon=ft.Icons.UPLOAD_FILE, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(texts.MSG_NO_DOCUMENT, size=13),
                ft.Text(texts.MSG_DROP_UNSUPPORTED, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Button(content=texts.BTN_OPEN, icon=ft.Icons.FOLDER_OPEN,
                          on_click=self._on_open),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            alignment=ft.Alignment.CENTER, padding=16, on_click=self._on_open,
        )
        self._paste_token = 0
        self._show_unloaded()
        self._converted = ft.TextField(multiline=True, read_only=True, expand=True,
                                       text_style=MONO, border=ft.OutlineInputBorder())
        self._truncated_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)
        self._save_button = ft.Button(content=texts.BTN_SAVE, icon=ft.Icons.SAVE,
                                      on_click=self._on_save, disabled=True)
        self._copy_button = ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=texts.BTN_COPY,
                                          on_click=self._on_copy, disabled=True)

        # --- 状態バー ---
        self._status_icon = ft.Icon(icon=ft.Icons.INFO_OUTLINE, size=16)
        self._status_text = ft.Text("", size=12, selectable=True)
        self._format_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self._pending_capability = ""
        self._settings_link = ft.TextButton(content=texts.BTN_OPEN_SETTINGS,
                                            icon=ft.Icons.SETTINGS, visible=False,
                                            on_click=self._on_open_settings_click)

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
            ft.Column([ft.Row([ft.Text(texts.LBL_ORIGINAL, size=12, weight=ft.FontWeight.W_600)],
                              height=PANE_HEADER_HEIGHT,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER),
                       ft.Column([self._drop_hint, self._original],
                                 scroll=ft.ScrollMode.AUTO, expand=True)],
                      expand=True, spacing=4),
            ft.Column([ft.Row([ft.Text(texts.LBL_CONVERTED, size=12, weight=ft.FontWeight.W_600),
                               ft.Container(expand=True),
                               self._copy_button, self._save_button],
                              height=PANE_HEADER_HEIGHT,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER),
                       ft.Column([self._converted, self._truncated_note],
                                 scroll=ft.ScrollMode.AUTO, expand=True)],
                      expand=True, spacing=4),
        ], expand=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

        status_bar = ft.Row([self._status_icon, self._status_text, self._settings_link,
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
        self._show_loaded()
        self._original.value = vm.original_text
        self._file_label.value = f"{vm.name}  ({vm.byte_size:,} B)"
        self._file_label.tooltip = vm.path or ""
        self._after_open()
        await self._after_load()

    def _after_open(self) -> None:
        """文書を開いた直後の共通処理（ダイアログ経由でも貼り付けでも同じ）。"""
        self._expr_field.value = self._state.query.expression
        self._expr_field.error = None
        self._close_button.disabled = False
        self._run_button.disabled = False
        self._expr_error.visible = False

    async def _after_load(self) -> None:
        await self._run()
        await self._reload_candidates()

    # ------------------------------------------------------------------ 貼り付け（G3）

    def _show_unloaded(self) -> None:
        """未読込：案内を出し、左ペインを貼り付け欄にする。"""
        self._drop_hint.visible = True
        self._original.read_only = False
        self._original.min_lines = PASTE_MIN_LINES
        self._original.hint_text = texts.MSG_PASTE_HERE
        self._original.on_change = self._on_paste
        self._original.value = ""

    def _show_loaded(self) -> None:
        """読込済み：案内を消し、左ペインを読み取り専用の原文表示にする。"""
        self._drop_hint.visible = False
        self._original.read_only = True
        self._original.min_lines = None
        self._original.hint_text = None
        self._original.on_change = None

    def _on_paste(self, e: ft.Event[ft.TextField]) -> None:
        """入力が 300 ms 止まったら、欄の中身を 1 つの文書として取り込む。

        貼り付けは一瞬で終わるが、手で打っている途中で確定すると欄が固まってしまうため。
        """
        self._paste_token += 1
        token = self._paste_token

        async def later() -> None:
            await asyncio.sleep(PASTE_DEBOUNCE_SECONDS)
            if token == self._paste_token:
                await self._open_pasted()

        self._page.run_task(later)

    async def _open_pasted(self) -> None:
        text = self._original.value or ""
        if not text.strip() or self._state.document.is_loaded:
            return
        self._p.open_text(text)
        self._show_loaded()
        self._file_label.value = texts.MSG_PASTED
        self._file_label.tooltip = ""
        self._after_open()
        await self._after_load()
        self._page.update()

    def _on_close(self, e: ft.Event[ft.Button]) -> None:
        self._p.close_document()
        self._show_unloaded()
        self._converted.value = ""
        self._file_label.value = texts.MSG_NO_DOCUMENT
        self._file_label.tooltip = ""
        self._expr_field.value = "."
        self._expr_field.error = None
        self._expr_error.visible = False
        self._close_button.disabled = True
        self._run_button.disabled = True
        self._truncated_note.visible = False
        self._save_button.disabled = True
        self._copy_button.disabled = True
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
        self._settings_link.visible = False

    def _on_open_settings_click(self, e: ft.Event[ft.TextButton]) -> None:
        if self._on_open_settings is not None:
            self._on_open_settings(self._pending_capability)

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
        # 巨大ファイルのデコード・エンコード中は、その処理が終わるまで止まらない（リスク R4）。
        # 押したことが伝わるよう、状態バーで受け付けたことを示す。
        self._cancel_button.disabled = True
        self._status_text.value = texts.MSG_CANCELLING

    # ------------------------------------------------------------------ 保存（G3）

    async def _on_save(self, e: ft.Event[ft.Button]) -> None:
        format_name = self._state.query.output_format
        if format_name in ("", "auto"):
            run = self._p.last_run
            format_name = run.output_format if run else "yaml"
        # save_file はパスを返すだけでファイルは作らない（G0 の実測）。書き込みは Presenter 側。
        path = await self._picker.save_file(
            dialog_title=texts.BTN_SAVE,
            file_name=self._p.default_save_name(),
            allowed_extensions=[extension_for(format_name)],
        )
        if path:
            await self._save_to(path, confirmed=False)
        self._page.update()

    async def _save_to(self, path: str, *, confirmed: bool) -> None:
        vm = await self._p.save(path, confirmed=confirmed)
        if vm.needs_overwrite_confirmation:
            self._ask_overwrite(path)
            return
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._page.show_dialog(ft.SnackBar(ft.Text(texts.MSG_SAVED.format(path=vm.path))))

    def _ask_overwrite(self, path: str) -> None:
        """元ファイルと同じパスを指されたときだけ出す。既定は「やめる」。"""

        def close(_: ft.Event) -> None:
            self._page.pop_dialog()

        async def proceed(_: ft.Event) -> None:
            self._page.pop_dialog()
            await self._save_to(path, confirmed=True)
            self._page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(texts.DLG_OVERWRITE_TITLE),
            content=ft.Text(texts.DLG_OVERWRITE_BODY.format(path=path), selectable=True),
            actions=[
                ft.TextButton(content=texts.DLG_OVERWRITE_CANCEL, on_click=close, autofocus=True),
                ft.TextButton(content=texts.DLG_OVERWRITE_OK, on_click=proceed),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)

    async def _on_copy(self, e: ft.Event[ft.IconButton]) -> None:
        run = self._p.last_run
        if run is None:
            return
        await ft.Clipboard().set(run.full_text)      # 表示用ではなく全量をコピーする
        self._page.show_dialog(ft.SnackBar(ft.Text(texts.MSG_COPIED)))

    # ------------------------------------------------------------------ 実行

    async def rerun(self) -> None:
        """設定が変わったときに外から呼ばれる。"""
        if self._state.document.is_loaded:
            await self._run()

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
            # 実行中は前回の結果を保存・コピーさせない（画面と保存内容をずらさない）
            self._save_button.disabled = True
            self._copy_button.disabled = True
            self._status_icon.icon = ft.Icons.HOURGLASS_TOP
            self._status_icon.color = None
            self._status_text.value = texts.MSG_RUNNING
            self._status_text.color = ft.Colors.ON_SURFACE

    def _apply(self, vm: RunViewModel) -> None:
        if not vm.ok:
            self._converted.value = ""
            self._truncated_note.visible = False
            self._format_text.value = ""
            self._save_button.disabled = True
            self._copy_button.disabled = True
            self._show_error(vm.error.message, vm.error.hint)
            # 許可されていない演算子のときだけ、該当する設定への導線を出す
            self._settings_link.visible = (vm.error.is_security
                                           and self._on_open_settings is not None)
            if self._settings_link.visible:
                self._pending_capability = vm.error.capability
            return
        self._settings_link.visible = False
        self._converted.value = vm.display_text
        self._save_button.disabled = False
        self._copy_button.disabled = False
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
