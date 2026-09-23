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
from yaqpy.gui._upload import WebUploader
from yaqpy.gui.errors_ja import caret_line
from yaqpy.gui.paths import DEFAULT_MAX_ITEMS, PathCandidate
from yaqpy.gui.presenter import MainPresenter, RunViewModel, ValidationViewModel
from yaqpy.gui.state import AUTO, GuiState

VALIDATE_DEBOUNCE_SECONDS = 0.3
PASTE_DEBOUNCE_SECONDS = 0.3
EDIT_DEBOUNCE_SECONDS = 0.5      # 読み込み後の追加編集：打ち終わってから取り込むまでの間
COPY_FEEDBACK_SECONDS = 1.5      # ボタン文字を「コピーしました！」に変えておく時間
PASTE_MIN_LINES = 4              # 未読込のあいだの貼り付け欄の高さ（画面に収まるよう控えめに）
PANE_HEADER_HEIGHT = 44         # 右見出しの保存ボタンに高さを合わせ、左右の枠の上端を揃える
MONO = ft.TextStyle(font_family="Consolas", size=12)
BUTTON_TEXT_SIZE = 14           # Flet のボタン文字（labelLarge）と同じ大きさ。ファイル名の表示に使う
FILTER_ROW_SPACING = 14         # 「プロパティ」行と「式」行のあいだ（ラベルが重ならないように）


def _format_badge() -> tuple[ft.Container, ft.Text]:
    """見出しの横に、いま採用している形式を出す小さな札。空のときは隠す。"""
    text = ft.Text("", size=11, weight=ft.FontWeight.W_600,
                   color=ft.Colors.ON_SECONDARY_CONTAINER)
    badge = ft.Container(content=text, visible=False, bgcolor=ft.Colors.SECONDARY_CONTAINER,
                         border_radius=10, padding=ft.Padding.symmetric(horizontal=8, vertical=2))
    return badge, text


def _options(names: list[str]) -> list[ft.DropdownOption]:
    return [ft.DropdownOption(key=n, text=n) for n in names]


def _output_format_options(names: list[str]) -> list[ft.DropdownOption]:
    """出力形式の選択肢。「auto」は「入力と同じ」だと分かる表示にする（key は auto のまま）。

    入力形式の「auto」は「中身から自動判定」という別の意味なので、そちらは変えない。
    """
    return [ft.DropdownOption(key=n, text=texts.LBL_AUTO_SAME_AS_INPUT if n == AUTO else n)
            for n in names]


async def _set_clipboard(text: str) -> bool:
    """クリップボードに書く。失敗したら False（例外で画面を止めない）。

    W0 の実測で、ブラウザが ``clipboard-write`` を許可していないと
    ``PlatformException(copy_fail, Clipboard.setData failed.)`` になった。デスクトップでも
    OS 側の理由で失敗しうるので、どちらも同じく案内に切り替える。
    """
    try:
        await ft.Clipboard().set(text)
    except Exception:                          # noqa: BLE001 - 失敗は利用者への案内で扱う
        return False
    return True


class MainPage:
    def __init__(self, *, page: ft.Page, presenter: MainPresenter, state: GuiState,
                 picker: ft.FilePicker,
                 on_open_settings: Callable[[str], None] | None = None,
                 uploader: WebUploader | None = None) -> None:
        self._on_open_settings = on_open_settings
        self._page = page
        self._p = presenter
        self._state = state
        self._picker = picker
        # Web 版（v0.6.0）：開くのはアップロード、保存はダウンロード。サーバー側のパスは扱わない
        self._uploader = uploader
        self._web = state.is_web
        self._rerun_requested = False
        self._validate_token = 0

        # --- ファイルバー ---
        # 「ファイルを開く」と「＋ファイルを追加」は 1 つのボタンに統一した（要望）。
        # 何も開いていなければ最初の 1 件として開き、すでにあれば閉じずに増やす。
        # 最初から有効：0 件のときに無効化すると何も開けなくなってしまうため。
        self._file_label = ft.Text(texts.MSG_NO_DOCUMENT, size=BUTTON_TEXT_SIZE,
                                   weight=ft.FontWeight.BOLD, selectable=True)
        self._add_file_button = ft.Button(content=texts.BTN_ADD_FILE, icon=ft.Icons.ADD,
                                          on_click=self._on_add_file)
        self._close_button = ft.Button(content=texts.BTN_CLOSE, icon=ft.Icons.CLOSE,
                                       on_click=self._on_close, disabled=True)

        # --- 複数ファイル（U3）：2 件以上のときだけ出す。タブで切り替えるだけで、
        # 「まとめて評価 (eval-all)」のトグルは撤去した（形式が違うと変換に失敗する組み合わせが
        # ありえ、ユースケースを精査してからにする。ロジックは presenter 側に残したまま）。
        self._files_row = ft.Row([], spacing=6, wrap=True, visible=False)

        # --- 形式バー ---
        self._input_dd = ft.Dropdown(label=texts.LBL_INPUT_FORMAT, width=170,
                                     value=state.query.input_format,
                                     options=_options(input_format_choices()),
                                     on_select=self._on_input_format)
        self._output_dd = ft.Dropdown(label=texts.LBL_OUTPUT_FORMAT, width=170,
                                      value=state.query.output_format,
                                      options=_output_format_options(output_format_choices()),
                                      on_select=self._on_output_format)
        # インデントは数字欄に直接打つほか、±ボタンでも操作できる（要望）。Flet に専用の
        # スピナー部品は無いので、IconButton を左右に添える形で組む。
        self._indent_field = ft.TextField(label=texts.LBL_INDENT, width=100,
                                          text_align=ft.TextAlign.CENTER,
                                          value=str(state.query.indent),
                                          input_filter=ft.NumbersOnlyInputFilter(),
                                          on_change=self._on_indent)
        self._indent_minus = ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="-1",
                                           on_click=self._on_indent_minus)
        self._indent_plus = ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, tooltip="+1",
                                          on_click=self._on_indent_plus)
        self._indent_stepper = ft.Row([self._indent_minus, self._indent_field, self._indent_plus],
                                      spacing=0, vertical_alignment=ft.CrossAxisAlignment.END)

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
        # 式欄の末尾に「 | 」を足すだけのボタン（プロパティの選択とは独立。v0.7.0）
        self._add_button = ft.Button(content=texts.BTN_ADD_PIPE, on_click=self._on_add_pipe,
                                     disabled=not state.query.expression.strip())
        self._candidate_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)

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
        # 式が難しいときに AI へ相談する文面を出す（CLI の --guide-prompt の GUI 版。要望）。
        # 文書の有無に関わらず使えるので、無効化しない。
        self._guide_button = ft.IconButton(icon=ft.Icons.SMART_TOY_OUTLINED,
                                           tooltip=texts.BTN_GUIDE_PROMPT,
                                           on_click=self._on_open_guide_prompt)
        self._progress = ft.ProgressBar(visible=False)

        # --- 2 ペイン ---
        # 見出しの横：入力形式・出力形式が auto でも指定でも、実際に採る形式名を出す
        self._original_badge, self._original_format = _format_badge()
        self._converted_badge, self._converted_format = _format_badge()
        # 読み込み後も原文欄は編集できる（追加編集。書き換えたら赤字で目立たせる。要望）。
        self._edited_label = ft.Text(texts.LBL_EDITED, size=11, weight=ft.FontWeight.BOLD,
                                     color=ft.Colors.ERROR, visible=False)
        # 未読込のあいだは貼り付け欄として編集可にする（ドロップが使えない環境の保険）
        self._original = ft.TextField(multiline=True, expand=True, text_style=MONO,
                                      border=ft.OutlineInputBorder())
        self._edit_token = 0
        # G0 の判定は「v1 はドロップ見送り」。領域は作らず、代わりにクリックで開ける案内を出す。
        # アイコン・余白は控えめにして、未読込の画面が窓の高さに収まりやすくしている。
        self._drop_hint = ft.Container(
            content=ft.Column([
                ft.Icon(icon=ft.Icons.UPLOAD_FILE, size=28, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(texts.MSG_NO_DOCUMENT, size=13),
                ft.Text(texts.MSG_WEB_HINT if self._web else texts.MSG_DROP_UNSUPPORTED,
                        size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            alignment=ft.Alignment.CENTER, padding=10, on_click=self._on_add_file,
        )
        self._paste_token = 0
        self._show_unloaded()
        self._converted = ft.TextField(multiline=True, read_only=True, expand=True,
                                       text_style=MONO, border=ft.OutlineInputBorder())
        self._truncated_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)
        self._save_button = ft.Button(content=texts.BTN_DOWNLOAD if self._web else texts.BTN_SAVE,
                                      icon=ft.Icons.DOWNLOAD if self._web else ft.Icons.SAVE,
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
            self._file_label,
            self._add_file_button,
            self._close_button,
        ], alignment=ft.MainAxisAlignment.START, spacing=12)

        files_bar = ft.Row([self._files_row], spacing=16)

        format_bar = ft.Row([self._input_dd, self._output_dd, self._indent_stepper], spacing=12)

        filter_bar = ft.Column([
            ft.Row([self._property_dd, self._add_button], spacing=8),
            self._candidate_note,
            ft.Row([self._expr_field, self._guide_button, self._run_button, self._cancel_button],
                  spacing=8),
            self._expr_error,
        ], spacing=FILTER_ROW_SPACING)

        # 複数行 TextField は内容の高さになるので、スクロールする Column で包む。
        # こうすると窓の高さを使い切り、長い文書は枠の中でスクロールする。
        panes = ft.Row([
            ft.Column([ft.Row([ft.Text(texts.LBL_ORIGINAL, size=12, weight=ft.FontWeight.W_600),
                               self._original_badge, self._edited_label],
                              height=PANE_HEADER_HEIGHT,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER),
                       ft.Column([self._drop_hint, self._original],
                                 scroll=ft.ScrollMode.AUTO, expand=True)],
                      expand=True, spacing=4),
            ft.Column([ft.Row([ft.Text(texts.LBL_CONVERTED, size=12, weight=ft.FontWeight.W_600),
                               self._converted_badge,
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

        return ft.Column([file_bar, files_bar, ft.Divider(height=1), format_bar, filter_bar,
                          self._progress, panes, ft.Divider(height=1), status_bar],
                         expand=True, spacing=8)

    # ------------------------------------------------------------------ 操作

    async def open_startup_file(self, path: str) -> None:
        """起動引数で渡されたファイルを開く（``yaqpy --gui a.yaml``。U2）。"""
        await self._load(path)
        self._page.update()

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
        self._edited_label.visible = False      # 新しい文書は「追加編集」前の状態から始まる
        self._refresh_format_badges()
        self._refresh_multi_file_ui()

    def _refresh_format_badges(self) -> None:
        """見出しの横の形式名を、いまの選択（auto を解決した後）に合わせる。"""
        input_name, output_name = self._p.adopted_formats()
        for badge, text, name in ((self._original_badge, self._original_format, input_name),
                                  (self._converted_badge, self._converted_format, output_name)):
            text.value = name
            badge.visible = bool(name)

    async def _after_load(self) -> None:
        await self._run()
        await self._reload_candidates()

    # ------------------------------------------------------------------ 複数ファイル（U3）

    async def _on_add_file(self, e: ft.Event) -> None:
        """[＋ファイルを追加]：「開く」と「追加」を統一した唯一の入口（要望）。

        何も開いていなければ、選んだ最初の 1 件が最初の文書になる（今までの「開く」に相当）。
        すでに開いていれば、選んだものをすべて閉じずに増やす。拡張子では絞らない：開いたら
        内容で形式を判定する（yaqpy 独自の拡張）。
        """
        if self._uploader is not None:
            await self._add_uploaded_files()
            return
        files = await self._picker.pick_files(dialog_title=texts.BTN_ADD_FILE, allow_multiple=True)
        if not files:
            self._page.update()
            return
        start = 0
        if not self._state.documents:
            vm = await self._p.open_path(files[0].path)
            if vm.ok:
                self._show_loaded()
                self._original.value = vm.original_text
                self._file_label.value = f"{vm.name}  ({vm.byte_size:,} B)"
                self._file_label.tooltip = vm.path or ""
                self._after_open()
            else:
                self._show_error(vm.error.message, vm.error.hint)
            start = 1
        for picked in files[start:]:
            vm = await self._p.add_path(picked.path)
            if not vm.ok:
                self._show_error(vm.error.message, vm.error.hint)
        if self._state.document.is_loaded:
            self._sync_active_document_view()
            self._refresh_multi_file_ui()
            await self._run()
            await self._reload_candidates()
        self._page.update()                 # async ハンドラは終了時にも update する

    async def add_dropped_files(self) -> None:
        """Web 版：ブラウザにドロップされたファイルを開く（``yaqpy-drop.js`` が通知する。v0.7.0）。

        ドロップされた File は、JS が「ファイルを選んだこと」にして ``pick_files`` へ渡すので、
        [＋ファイルを追加] と同じ経路（サイズの事前確認・アップロード・上限）を通る。
        """
        if self._uploader is None:
            return
        await self._add_uploaded_files()

    async def _add_uploaded_files(self) -> None:
        """Web 版の [＋ファイルを追加]：ブラウザから送らせて開く（``_on_add_file`` と同じ規則）。"""
        assert self._uploader is not None

        def check_size(size: int) -> str:
            error = self._p.check_upload_size(size)
            return error.message if error else ""

        def on_start() -> None:
            self._progress.visible = True
            self._status_text.value = texts.MSG_UPLOADING
            self._page.update()

        items = await self._uploader.pick(check_size=check_size, on_start=on_start)
        self._progress.visible = False
        if not items:
            self._page.update()
            return
        errors: list[str] = []
        for item in items:
            if not item.ok:
                errors.append(item.error)
                continue
            assert item.data is not None
            if not self._state.documents:
                vm = await self._p.open_upload(item.name, item.data)
                if vm.ok:
                    self._show_loaded()
                    self._after_open()
            else:
                vm = await self._p.add_upload(item.name, item.data)
            if not vm.ok:
                errors.append(vm.error.message)
        if self._state.document.is_loaded:
            self._sync_active_document_view()
            self._refresh_multi_file_ui()
            await self._run()
            await self._reload_candidates()
        if errors:
            self._show_error(" / ".join(errors))     # 実行結果より後に出す（上書きされないように）
        elif not self._state.document.is_loaded:
            self._status_text.value = ""
        self._page.update()

    async def _on_select_document(self, index: int) -> None:
        self._p.select_document(index)
        self._sync_active_document_view()
        self._refresh_multi_file_ui()
        await self._run()
        await self._reload_candidates()
        self._page.update()

    async def _on_close_document_at(self, index: int) -> None:
        self._p.close_document_at(index)
        if self._state.document.is_loaded:
            self._sync_active_document_view()
            self._refresh_multi_file_ui()
            await self._run()
            await self._reload_candidates()
        else:
            self._reset_ui_to_unloaded()
        self._page.update()

    def _sync_active_document_view(self) -> None:
        """左ペイン・ファイル名の表示を、いま選ばれている文書に合わせる。"""
        doc = self._state.document
        self._show_loaded()
        self._original.value = doc.original_text
        self._file_label.value = f"{doc.name or texts.MSG_PASTED}  ({doc.byte_size:,} B)"
        self._file_label.tooltip = doc.path or ""
        self._edited_label.visible = doc.edited     # 文書ごとに「追加編集」の有無を覚えている
        self._refresh_format_badges()

    def _refresh_multi_file_ui(self) -> None:
        """ファイルの一覧（チップ）を、いまの状態に合わせて作り直す。

        1 件だけのときは v1 までと同じ見た目に戻す（チップの一覧は 2 件以上でだけ出す）。
        """
        documents = self._state.documents
        self._files_row.visible = len(documents) > 1
        chips: list[ft.Control] = []
        for i, doc in enumerate(documents):
            chips.append(ft.Chip(
                label=doc.name or texts.MSG_PASTED,
                selected=(i == self._state.active_index),
                delete_icon=ft.Icon(ft.Icons.CLOSE, size=14),
                on_click=self._chip_select_handler(i),
                on_delete=self._chip_close_handler(i),
            ))
        self._files_row.controls = chips

    def _chip_select_handler(self, index: int) -> Callable[[ft.Event[ft.Chip]], None]:
        def handler(e: ft.Event[ft.Chip]) -> None:
            self._page.run_task(self._on_select_document, index)
        return handler

    def _chip_close_handler(self, index: int) -> Callable[[ft.Event[ft.Chip]], None]:
        def handler(e: ft.Event[ft.Chip]) -> None:
            self._page.run_task(self._on_close_document_at, index)
        return handler

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
        """読込済み：案内を消し、左ペインを**追加編集できる**原文表示にする（要望）。

        開いたファイルそのもの（ディスク上）は書き換わらない：ここでの編集は
        ``DocumentState.original_text``（画面上の入力）だけを差し替える。
        """
        self._drop_hint.visible = False
        self._original.read_only = False
        self._original.min_lines = None
        self._original.hint_text = None
        self._original.on_change = self._on_edit_original

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

    def _on_edit_original(self, e: ft.Event[ft.TextField]) -> None:
        """読み込み後の追加編集：打ち終わって 500 ms 止まったら取り込み直す（要望）。"""
        self._edit_token += 1
        token = self._edit_token

        async def later() -> None:
            await asyncio.sleep(EDIT_DEBOUNCE_SECONDS)
            if token == self._edit_token:
                await self._apply_edit()

        self._page.run_task(later)

    async def _apply_edit(self) -> None:
        changed = self._p.edit_active_document(self._original.value or "")
        if not changed:
            return
        self._edited_label.visible = True
        doc = self._state.document
        self._file_label.value = f"{doc.name or texts.MSG_PASTED}  ({doc.byte_size:,} B)"
        self._refresh_format_badges()
        await self._run()
        await self._reload_candidates()
        self._page.update()

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
        """開いているものをすべて閉じる（一覧の 1 件だけを閉じるのは `_on_close_document_at`）。"""
        self._p.close_document()
        self._reset_ui_to_unloaded()

    def _reset_ui_to_unloaded(self) -> None:
        self._show_unloaded()
        self._converted.value = ""
        self._file_label.value = texts.MSG_NO_DOCUMENT
        self._file_label.tooltip = ""
        self._expr_field.value = "."
        self._expr_field.error = None
        self._expr_error.visible = False
        self._close_button.disabled = True
        self._run_button.disabled = True
        self._edited_label.visible = False
        self._truncated_note.visible = False
        self._save_button.disabled = True
        self._copy_button.disabled = True
        self._property_dd.options = []
        self._property_dd.value = None
        self._property_dd.disabled = True
        self._add_button.disabled = False
        self._candidate_note.visible = False
        self._status_icon.icon = ft.Icons.INFO_OUTLINE
        self._status_icon.color = None
        self._status_text.value = ""
        self._format_text.value = ""
        self._settings_link.visible = False
        self._refresh_format_badges()
        self._refresh_multi_file_ui()

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

    def _on_indent_minus(self, e: ft.Event[ft.IconButton]) -> None:
        self._set_indent(max(0, self._state.query.indent - 1))

    def _on_indent_plus(self, e: ft.Event[ft.IconButton]) -> None:
        self._set_indent(self._state.query.indent + 1)

    def _set_indent(self, value: int) -> None:
        """±ボタンからの変更。数字欄の表示も合わせて書き換える。"""
        self._state.query.indent = value
        self._indent_field.value = str(value)
        self._page.run_task(self._run)

    def _on_expression_change(self, e: ft.Event[ft.TextField]) -> None:
        """入力中は検証だけ（再実行はしない）。最後の打鍵から 300 ms 後に 1 回だけ走る。"""
        self._state.query.expression = e.control.value or ""
        self._add_button.disabled = not self._state.query.expression.strip()
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
        self._property_dd.disabled = vm.is_empty
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
        self._expr_field.value = self._p.apply_candidate(expression)
        self._add_button.disabled = False
        self._expr_field.error = None
        self._expr_error.visible = False
        self._page.run_task(self._run)

    def _on_add_pipe(self, e: ft.Event[ft.Button]) -> None:
        """式欄の末尾に `` | `` を足す。実行はしない（続きを書いてから実行する）。"""
        self._expr_field.value = self._p.append_pipe()
        self._expr_field.error = None            # 書きかけの式なので、検証の赤枠は出さない
        self._expr_error.visible = False
        self._page.update()

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

    # ------------------------------------------------------------------ AI への相談文（要望）

    async def _on_open_guide_prompt(self, e: ft.Event[ft.IconButton]) -> None:
        prompt = await self._p.guide_prompt()
        self._show_guide_prompt_dialog(prompt)
        self._page.update()

    def _show_guide_prompt_dialog(self, prompt: str) -> None:
        """CLI の --guide-prompt の内容を、編集してコピーできるダイアログで出す（要望）。

        MD Slide Studio の「AI プロンプト」画面を参考にした：全文を編集可能な 1 つの欄に入れ、
        末尾の「## 依頼」をユーザーが書き換えてからコピーする、という使い方を想定している。
        """
        field = ft.TextField(value=prompt, multiline=True, min_lines=16, max_lines=16,
                             text_style=MONO, expand=True)
        copy_button = ft.TextButton(content=texts.BTN_COPY_PROMPT)

        def close(_: ft.Event) -> None:
            self._page.pop_dialog()

        async def copy(_: ft.Event) -> None:
            if not await _set_clipboard(field.value or ""):
                self._page.show_dialog(ft.SnackBar(ft.Text(texts.MSG_COPY_FAILED)))
                self._page.update()
                return
            copy_button.content = texts.MSG_COPIED_SHORT
            self._page.update()
            await asyncio.sleep(COPY_FEEDBACK_SECONDS)
            copy_button.content = texts.BTN_COPY_PROMPT
            self._page.update()

        copy_button.on_click = copy

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(texts.DLG_GUIDE_PROMPT_TITLE),
            content=ft.Column([
                ft.Text(texts.DLG_GUIDE_PROMPT_HINT, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                field,
            ], width=640, height=460, spacing=8, tight=True),
            actions=[
                ft.TextButton(content=texts.BTN_CLOSE, on_click=close),
                copy_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)

    # ------------------------------------------------------------------ 保存（G3）

    async def _on_save(self, e: ft.Event[ft.Button]) -> None:
        if self._web:
            await self._download()
            self._page.update()
            return
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

    async def _download(self) -> None:
        """Web 版の保存：ブラウザのダウンロードで渡す（サーバーのディスクには書かない）。

        W0 の実測：``save_file`` は Web では ``src_bytes`` と ``file_name`` が必須で、戻り値は None。
        """
        vm = await self._p.prepare_download()
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        await self._picker.save_file(dialog_title=texts.BTN_DOWNLOAD, file_name=vm.file_name,
                                     src_bytes=vm.data)
        self._page.show_dialog(ft.SnackBar(ft.Text(texts.MSG_DOWNLOADED.format(name=vm.file_name))))

    async def _save_to(self, path: str, *, confirmed: bool) -> None:
        vm = await self._p.save(path, confirmed=confirmed)
        if vm.needs_overwrite_confirmation:
            self._ask_overwrite(path)
            return
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        message = (texts.MSG_SAVED_WITH_BACKUP.format(path=vm.path, backup=vm.backup_path)
                  if vm.backup_path else texts.MSG_SAVED.format(path=vm.path))
        self._page.show_dialog(ft.SnackBar(ft.Text(message)))

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
        copied = await _set_clipboard(run.full_text)   # 表示用ではなく全量をコピーする
        message = texts.MSG_COPIED if copied else texts.MSG_COPY_FAILED
        self._page.show_dialog(ft.SnackBar(ft.Text(message)))

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
        self._refresh_format_badges()
        if not vm.ok:
            self._converted.value = ""
            self._truncated_note.visible = False
            self._format_text.value = ""
            self._save_button.disabled = True
            self._copy_button.disabled = True
            self._show_error(vm.error.message, vm.error.hint)
            # 許可されていない演算子のときだけ、該当する設定への導線を出す
            # Web 版には許可の設定が無いので導線を出さない
            self._settings_link.visible = (vm.error.is_security and not self._web
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
