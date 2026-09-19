# yaqpy GUI 実装プラン — Phase G3（保存・設定・ドロップ・仕上げ）

| 項目 | 内容 |
|---|---|
| 文書 ID | 0919-06_31_yaqpy-gui-phaseG3 |
| 版 | 第1.0版 |
| 作成日 | 2026-09-19 |
| 親文書 | [`0919-02_31_design-yaqpy-gui.md`](./0919-02_31_design-yaqpy-gui.md)（GUI 設計書）の [6-4 保存機能](./0919-02_31_design-yaqpy-gui.md#6-4-保存機能) |
| 前フェーズ | [`0919-05_31_yaqpy-gui-phaseG2.md`](./0919-05_31_yaqpy-gui-phaseG2.md)（**完了していること**） |
| ブランチ | `feat/gui-g3-save` |
| 目的 | **結果をファイルに保存**できるようにし、設定・ドロップ・エラー導線・ドキュメントを仕上げて v1 にする |
| 完了条件 | GUI 設計書の受入基準 **A1〜A8 すべて** ＋ 手動テスト **M1〜M10** |
| 所要 | 1.5 日（タスク 8 件） |

---

## 0. このファイルの使い方

G1・G2 と同じです。加えて **T3-4（ドロップ）は G0 の実測メモの判定に従って分岐**します。着手前に `31_dev-yaqpy/docs/flet-1.0-api-notes.md` の「5. ファイルドロップの判定」を読んでください。

---

## 1. G3 が終わったときの状態

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 📄 [ファイルを開く]  sample.yaml (231 B)                     [✕ 閉じる]     │
│ 入力形式 [yaml ▼] 出力形式 [json ▼] インデント [2] [□ 整形]                 │
│ プロパティ [.server.port = 8080 ▼] [＋ 式に追加]                            │
│ 式 [.server.port                                      ] [▶ 実行][■ 中止]   │
├───────────────────────────────┬────────────────────────────────────────────┤
│ オリジナル                     │ 変換結果                  [📋] [💾 保存]   │  ← 新規
│ # サーバー設定                 │ 8080                                       │
├───────────────────────────────┴────────────────────────────────────────────┤
│ ✅ 1 document / 3.2 ms / 出力 5 bytes      yaml → json                      │
├────────────────────────────────────────────────────────────────────────────┤
│ [ 📄 メイン ]  [ ⚙ 設定 ]                                                   │  ← 新規
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. タスク一覧

| # | タスク | 推奨モデル | 主な成果物 |
|---|---|---|---|
| T3-1 | Presenter に保存を追加 ＋ テスト | **Sonnet 必須** | `gui/presenter.py`, `tests/unit/test_gui_presenter.py` |
| T3-2 | 保存・コピー UI ＋ 同一パス警告ダイアログ | **Sonnet 必須** | `gui/pages/main_page.py` |
| T3-3 | 設定ページとページ切り替え | Sonnet | `gui/pages/settings_page.py`, `gui/_run.py` |
| T3-4 | ファイルドロップ（G0 の判定で分岐） | **Sonnet 必須** | `gui/pages/main_page.py` ほか |
| T3-5 | セキュリティエラーから設定への導線 | Sonnet | `gui/pages/main_page.py` |
| T3-6 | 終了時のキャンセルとダークテーマ | **Haiku 4.5 可** | `gui/_run.py` |
| T3-7 | README / USAGE.ja.md / docs 反映 | **Haiku 4.5 可** | ドキュメント 3 点 |
| T3-8 | 受入 A1〜A8・手動 M1〜M10 の通し確認 | Sonnet | （確認のみ） |

---

## 3. 各タスクの詳細

### T3-1. Presenter に保存を追加

**設計上の不変条件（絶対に守ること）**

| # | 不変条件 | 実装での担保 |
|---|---|---|
| S1 | **保存するのは `full_text`**（`display_text` ではない） | `save()` は `RunViewModel.full_text` しか読まない。テスト T15 相当で検証 |
| S2 | **表示と保存がずれない** | 直前の実行結果が無ければ保存前に `run()` をやり直す |
| S3 | **開いている元ファイルを黙って壊さない** | 同一パスなら書かずに `needs_overwrite_confirmation=True` を返す |
| S4 | 途中で失敗しても保存先が壊れない | `LocalFileSystem.atomic_write()`（一時ファイル → `os.replace`）を使う。GUI 側で `open()` を書かない |

**変更 1**：`src/yaqpy/gui/presenter.py` に ViewModel を追加（`CandidatesViewModel` の後ろ）

```python
@dataclass(frozen=True, slots=True)
class SaveViewModel:
    path: str = ""
    byte_size: int = 0
    needs_overwrite_confirmation: bool = False   # 元ファイルと同じパスを指された
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.needs_overwrite_confirmation
```

**変更 2**：メソッドを 3 つ足す（`_collect_sync` の前）

```python
    # ------------------------------------------------------------------ 保存（G3）

    def default_save_name(self) -> str:
        """保存ダイアログの初期ファイル名。拡張子は FormatSpec から採る。"""
        run = self._last_run
        format_name = (run.output_format if run else "") or self.state.query.output_format
        if format_name in ("", "auto"):
            format_name = "yaml"
        spec = self._service.formats.get(format_name)
        extension = spec.extensions[0] if spec.extensions else f".{spec.name}"
        name = self.state.document.name
        stem = os.path.splitext(name)[0] if name else ""
        return f"{stem or 'output'}{extension}"

    async def save(self, path: str, *, confirmed: bool = False) -> SaveViewModel:
        """変換結果の**全量**を別名保存する。"""
        run = self._last_run
        if run is None:                       # 表示が古い／まだ実行していない
            run = await self.run()
            if not run.ok:
                return SaveViewModel(path=path, error=run.error)
        if not confirmed and self._is_source_path(path):
            return SaveViewModel(path=path, needs_overwrite_confirmation=True)
        text = run.full_text                  # ← display_text を使わないこと（S1）
        try:
            await asyncio.to_thread(self._fs.atomic_write, path, text)
        except Exception as e:                # noqa: BLE001 - 画面を落とさない
            return SaveViewModel(path=path, error=to_view_model(e))
        return SaveViewModel(path=path, byte_size=len(text.encode("utf-8")))

    def _is_source_path(self, path: str) -> bool:
        """保存先が、いま開いているファイルと同じか（大文字小文字・相対表記を吸収する）。"""
        source = self.state.document.path
        if not source:
            return False
        try:
            return (os.path.normcase(os.path.realpath(source))
                    == os.path.normcase(os.path.realpath(path)))
        except OSError:
            return source == path
```

**変更 3**：`src/yaqpy/gui/texts.py` に追加

```python
DLG_OVERWRITE_TITLE = "元のファイルを上書きしますか？"
DLG_OVERWRITE_BODY = (
    "保存先が、いま開いているファイルと同じです。\n"
    "上書きすると元の内容は戻せません。\n\n{path}"
)
DLG_OVERWRITE_OK = "上書きする"
DLG_OVERWRITE_CANCEL = "やめる"
MSG_COPIED = "変換結果をクリップボードにコピーしました"
```

**テスト追加**：`tests/unit/test_gui_presenter.py` の末尾

```python
class SaveTests(unittest.IsolatedAsyncioTestCase):
    async def _ready(self) -> MainPresenter:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        await p.run()
        return p

    async def test_saves_the_result(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/out.yaml")
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertEqual(p._fs.written["/w/out.yaml"], "8080\n")
        self.assertEqual(vm.byte_size, len("8080\n".encode()))

    async def test_saves_the_full_text_not_the_display_text(self) -> None:
        """リスク R8：表示を丸めても保存内容は全量であること。"""
        p = make_presenter()
        p.state.settings.max_display_lines = 3
        p.open_text("\n".join(f"- item{i}" for i in range(50)) + "\n", name="many.yaml")
        run = await p.run()
        self.assertEqual(run.display_text.count("\n"), 3)
        await p.save("/w/all.yaml")
        self.assertEqual(p._fs.written["/w/all.yaml"], run.full_text)
        self.assertEqual(p._fs.written["/w/all.yaml"].count("\n"), 50)

    async def test_refuses_to_overwrite_the_source_without_confirmation(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/sample.yaml")
        self.assertFalse(vm.ok)
        self.assertTrue(vm.needs_overwrite_confirmation)
        self.assertNotIn("/w/sample.yaml", p._fs.written)     # 書いていない

    async def test_overwrites_the_source_only_when_confirmed(self) -> None:
        p = await self._ready()
        vm = await p.save("/w/sample.yaml", confirmed=True)
        self.assertTrue(vm.ok)
        self.assertEqual(p._fs.written["/w/sample.yaml"], "8080\n")

    async def test_runs_again_when_there_is_no_fresh_result(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")        # run() していない
        vm = await p.save("/w/out.yaml")
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertIn("# サーバー設定", p._fs.written["/w/out.yaml"])

    async def test_save_failure_is_reported(self) -> None:
        p = await self._ready()

        def broken(path: str, text: str) -> None:
            raise PermissionError(13, "Permission denied")

        p._fs.atomic_write = broken             # type: ignore[method-assign]
        vm = await p.save("/w/out.yaml")
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "io")

    async def test_save_without_a_document(self) -> None:
        p = make_presenter()
        vm = await p.save("/w/out.yaml")
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "no_document")


class DefaultSaveNameTests(unittest.IsolatedAsyncioTestCase):
    async def test_follows_the_output_format(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "json"
        await p.run()
        self.assertEqual(p.default_save_name(), "sample.json")

    async def test_properties_extension(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "props"
        await p.run()
        self.assertEqual(p.default_save_name(), "sample.properties")

    async def test_pasted_text_gets_a_generic_name(self) -> None:
        p = make_presenter()
        p.open_text("a: 1\n")
        await p.run()
        self.assertEqual(p.default_save_name(), "output.yaml")
```

**検証**

```bash
uv run python -m unittest tests.unit.test_gui_presenter -v
```

**DoD**

- [ ] 追加 10 件を含め全件パス（`test_gui_presenter` 合計 38 件）
- [ ] `test_saves_the_full_text_not_the_display_text` がパス（**S1 の担保。ここが落ちたら先に進まない**）
- [ ] `test_refuses_to_overwrite_the_source_without_confirmation` がパス（**S3 の担保**）

**コミット**：`feat(gui): save the converted result to a new file`

---

### T3-2. 保存・コピー UI ＋ 同一パス警告ダイアログ

**変更 1**：`main_page.py` の `__init__` に部品を追加

```python
        self._save_button = ft.Button(content=texts.BTN_SAVE, icon=ft.Icons.SAVE,
                                      on_click=self._on_save, disabled=True)
        self._copy_button = ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip=texts.BTN_COPY,
                                          on_click=self._on_copy, disabled=True)
```

**変更 2**：`_build()` の右ペイン見出し行に足す

置換前：

```python
            ft.Column([ft.Row([ft.Text(texts.LBL_CONVERTED, size=12,
                                       weight=ft.FontWeight.W_600)]),
                       self._converted, self._truncated_note], expand=True, spacing=4),
```

置換後：

```python
            ft.Column([ft.Row([ft.Text(texts.LBL_CONVERTED, size=12,
                                       weight=ft.FontWeight.W_600),
                               ft.Container(expand=True),
                               self._copy_button, self._save_button]),
                       self._converted, self._truncated_note], expand=True, spacing=4),
```

**変更 3**：`_apply()` の成功時にボタンを有効化（`self._converted.value = vm.display_text` の直後）

```python
        self._save_button.disabled = False
        self._copy_button.disabled = False
```

`_apply()` の失敗側（`if not vm.ok:` の中）と `_on_close()` では無効化する：

```python
        self._save_button.disabled = True
        self._copy_button.disabled = True
```

**変更 4**：ハンドラを足す

```python
    # ------------------------------------------------------------------ 保存（G3）

    async def _on_save(self, e: ft.Event[ft.Button]) -> None:
        format_name = self._state.query.output_format
        if format_name in ("", "auto"):
            run = self._p.last_run
            format_name = run.output_format if run else "yaml"
        path = await self._picker.save_file(
            dialog_title=texts.BTN_SAVE,
            file_name=self._p.default_save_name(),
            allowed_extensions=[extension_for(format_name)],
        )
        if not path:
            return
        await self._save_to(path, confirmed=False)

    async def _save_to(self, path: str, *, confirmed: bool) -> None:
        vm = await self._p.save(path, confirmed=confirmed)
        if vm.needs_overwrite_confirmation:
            self._ask_overwrite(path)
            return
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._page.show_dialog(
            ft.SnackBar(ft.Text(texts.MSG_SAVED.format(path=vm.path))))

    def _ask_overwrite(self, path: str) -> None:
        """元ファイルと同じパスを指されたときだけ出す。既定は「やめる」。"""

        def close(_: ft.Event) -> None:
            self._page.pop_dialog()

        async def proceed(_: ft.Event) -> None:
            self._page.pop_dialog()
            await self._save_to(path, confirmed=True)

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
```

**変更 5**：import に追加

```python
from yaqpy.gui._di import extension_for, input_format_choices, output_format_choices
```

> ⚠ **ダイアログとスナックバーの出し方は G0 メモを確認**してください。ここでは `page.show_dialog(...)` / `page.pop_dialog()` を前提にしています（Flet 1.0 の移行ガイドと SnackBar のドキュメントで確認した形）。`ft.Clipboard()` はサービスなので、`page.services` への登録が要るかどうかもメモで確認してください（要る場合は `_run.py` で `clipboard = ft.Clipboard(); page.services.append(clipboard)` として使い回す）。

**検証（手動）**

- `.server.port` を出した状態で `[💾 保存]` → 既定名が `sample.yaml`（出力 json なら `sample.json`）
- 保存すると SnackBar が出て、ファイルの中身が右ペインと一致する（**受入 A6**）
- **元ファイルと同じ名前で保存しようとすると警告ダイアログが出る**。「やめる」を押すと元ファイルは無傷
- 表示上限を 10 行に下げて大きい出力を保存 → **保存ファイルは全量**

**DoD**

- [ ] 受入 **A6** が満たされる
- [ ] 上書き警告の既定が「やめる」側（`autofocus` がキャンセル）
- [ ] フルテストがパス

**コミット**：`feat(gui): add save and copy actions with an overwrite guard`

---

### T3-3. 設定ページとページ切り替え

**作成**：`src/yaqpy/gui/pages/settings_page.py`

```python
"""設定画面。値は GuiState.settings に即時反映し、必要なら再実行を依頼する。"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui.state import GuiState

NOTE = ft.TextStyle(size=12)


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
        self._timeout = ft.TextField(label=texts.SET_TIMEOUT, width=180,
                                     value=str(int(s.timeout_seconds)),
                                     input_filter=ft.NumbersOnlyInputFilter(),
                                     on_change=self._on_timeout)
        self._max_input = ft.TextField(label=texts.SET_MAX_INPUT, width=180,
                                       value=str(s.max_input_mib),
                                       input_filter=ft.NumbersOnlyInputFilter(),
                                       on_change=self._on_max_input)
        self._max_lines = ft.TextField(label=texts.SET_MAX_LINES, width=180,
                                       value=str(s.max_display_lines),
                                       input_filter=ft.NumbersOnlyInputFilter(),
                                       on_change=self._on_max_lines)
        self._dark = ft.Switch(label=texts.SET_DARK, value=s.dark_theme,
                               on_change=self._on_dark)

        self._root = ft.Column([
            ft.Text(texts.SET_TITLE, size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text(texts.SET_SECURITY, weight=ft.FontWeight.W_600),
            ft.Text(texts.SET_SECURITY_NOTE, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            self._allow_env,
            self._allow_file,
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
        target = self._allow_env if capability == "env" else self._allow_file
        target.focus()

    # ------------------------------------------------------------------ handlers

    def _on_allow_env(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.allow_env = bool(e.control.value)
        self._on_changed()

    def _on_allow_file(self, e: ft.Event[ft.Switch]) -> None:
        self._state.settings.allow_file = bool(e.control.value)
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
```

**変更**：`src/yaqpy/gui/texts.py` に追加

```python
SET_TITLE = "設定"
SET_SECURITY = "セキュリティ"
SET_SECURITY_NOTE = "既定はすべて不許可です。必要なときだけ許可してください"
SET_ALLOW_ENV = "env / strenv 演算子を許可（環境変数を読めるようになります）"
SET_ALLOW_FILE = "load / loadstr 演算子を許可（他のファイルを読めるようになります）"
SET_SYSTEM_NOTE = "※ system 演算子は GUI では提供しません"
SET_RUN = "実行"
SET_TIMEOUT = "タイムアウト（秒）"
SET_MAX_INPUT = "最大入力（MiB）"
SET_MAX_LINES = "表示行数の上限"
SET_VIEW = "表示"
SET_DARK = "ダークテーマ"
NAV_MAIN = "📄 メイン"
NAV_SETTINGS = "⚙ 設定"
```

**変更**：`src/yaqpy/gui/_run.py` にページ切り替えを入れる

置換前：

```python
    main_page = MainPage(page=page, presenter=presenter, state=state, picker=picker)
    page.add(main_page.control)
```

置換後：

```python
    content = ft.Container(expand=True)

    def show(index: int) -> None:
        content.content = pages[index].control
        for i, button in enumerate(nav_buttons):
            button.style = ft.ButtonStyle(
                color=ft.Colors.PRIMARY if i == index else ft.Colors.ON_SURFACE_VARIANT)

    def go_to_settings(capability: str = "") -> None:
        show(1)
        if capability:
            settings_page.focus_capability(capability)
        page.update()

    main_page = MainPage(page=page, presenter=presenter, state=state, picker=picker,
                         on_open_settings=go_to_settings)
    settings_page = SettingsPage(page=page, state=state,
                                 on_changed=lambda: page.run_task(main_page.rerun))
    pages = [main_page, settings_page]

    nav_buttons = [
        ft.TextButton(content=texts.NAV_MAIN, on_click=lambda e: show(0)),
        ft.TextButton(content=texts.NAV_SETTINGS, on_click=lambda e: show(1)),
    ]
    nav_bar = ft.Container(
        content=ft.Row(nav_buttons, alignment=ft.MainAxisAlignment.START),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
    )

    show(0)
    page.add(content, nav_bar)
```

import も足す：

```python
from yaqpy.gui.pages.settings_page import SettingsPage
```

**変更**：`main_page.py` に、設定から呼ばれる再実行の入口を足す

```python
    def __init__(self, *, page: ft.Page, presenter: MainPresenter, state: GuiState,
                 picker: ft.FilePicker,
                 on_open_settings: Callable[[str], None] | None = None) -> None:
        ...
        self._on_open_settings = on_open_settings

    async def rerun(self) -> None:
        """設定が変わったときに外から呼ばれる。"""
        if self._state.document.is_loaded:
            await self._run()
```

（`from collections.abc import Callable` の import を足す。）

**検証（手動）**

- `[⚙ 設定]` で設定ページに移り、`[📄 メイン]` で戻れる
- 「env を許可」を ON にして `strenv(PATH)` を実行 → 通る。OFF に戻すと拒否される
- 表示行数の上限を 5 にすると、右ペインが 5 行に丸められる（保存は全量のまま）
- ダークテーマの切り替えで両ページの文字が読める（**手動 M7**）

**DoD**

- [ ] 設定の変更が**次の実行から効く**
- [ ] タイムアウトに 0 や空欄を入れても壊れない
- [ ] フルテストがパス

**コミット**：`feat(gui): add the settings page and page navigation`

---

### T3-4. ファイルドロップ（G0 の判定で分岐）

**まず `docs/flet-1.0-api-notes.md` の「5. ファイルドロップの判定」を読む。** 以下は判定ごとの実装です。

#### 段階 1：Flet 本体に機能があった場合

メモに記録したイベント名で受け、`intake` に流すだけです。

```python
    # main_page.py
    def _install_drop(self) -> None:
        """G0 メモに記録した本体機能でドロップを受ける。"""
        def on_drop(e) -> None:  # noqa: ANN001 - 実際の型は G0 メモ参照
            paths = _paths_from_drop_event(e)     # メモの取り出し方をここに実装する
            if not paths:
                return
            self._page.run_task(lambda: self._load(paths[0]))
        # 例: self._page.on_drop = on_drop  /  受け皿を ft.DropZone で包む
```

#### 段階 2：`flet-dropzone` を使う場合

```bash
uv add --optional gui-drop flet-dropzone
```

`pyproject.toml` に extra がもう 1 つ増えるので、README にも書きます。読み込みは**必ず任意**にします。

```python
    # main_page.py の先頭
    try:
        from flet_dropzone import Dropzone
        DROP_AVAILABLE = True
    except ImportError:                       # 拡張が無くても GUI は動く
        Dropzone = None                       # type: ignore[assignment]
        DROP_AVAILABLE = False
```

2 ペインを `Dropzone` で包み、`on_dropped` から `self._load(path)` を呼びます。

#### 段階 3：v1 では見送る場合

**ドロップ領域は作らず、代わりに「クリックで開く／貼り付け」を目立たせます。**

```python
    # __init__ に足す
        self._drop_hint = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.UPLOAD_FILE, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(texts.MSG_NO_DOCUMENT, size=13),
                ft.Text(texts.MSG_DROP_UNSUPPORTED, size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Button(content=texts.BTN_OPEN, icon=ft.Icons.FOLDER_OPEN,
                          on_click=self._on_open),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            alignment=ft.Alignment.CENTER, expand=True,
            on_click=self._on_open,
        )
```

左ペインは「未読込なら `self._drop_hint`、読込済なら `self._original`」を切り替えて表示します。

```python
# texts.py
MSG_DROP_UNSUPPORTED = "この環境ではファイルのドラッグ＆ドロップに対応していません"
```

**さらに、貼り付けからの取り込みを必ず入れる**（段階 1・2 でも入れる。ドロップが使えない環境の保険）：

```python
    def _enable_paste(self) -> None:
        """未読込のとき、左ペインを編集可にして貼り付けを受ける。"""
        self._original.read_only = False
        self._original.hint_text = texts.MSG_PASTE_HERE
        self._original.on_change = self._on_paste

    def _on_paste(self, e: ft.Event[ft.TextField]) -> None:
        text = e.control.value or ""
        if not text.strip():
            return
        self._p.open_text(text)
        self._original.read_only = True
        self._original.on_change = None
        self._close_button.disabled = False
        self._run_button.disabled = False
        self._file_label.value = texts.MSG_PASTED
        self._page.run_task(self._after_load)

    async def _after_load(self) -> None:
        await self._run()
        await self._reload_candidates()
```

```python
# texts.py
MSG_PASTE_HERE = "ここに YAML / JSON を貼り付けてください"
MSG_PASTED = "（貼り付けたテキスト）"
```

> `_load()` の末尾も `await self._after_load()` を使うように整理すると、経路が 1 本になります。

**DoD**

- [ ] 段階 1・2 の場合：**受入 A7**（ドロップで開ける）が満たされる
- [ ] 段階 3 の場合：画面に「対応していません」が明示され、クリック＋貼り付けで開ける
- [ ] どの段階でも、**貼り付けからの取り込みが動く**
- [ ] `test_gui_third_party_whitelist` がパス（`flet_dropzone` は許可リストに入っている）

**コミット**：`feat(gui): accept files by drop (or state the fallback clearly)`

---

### T3-5. セキュリティエラーから設定への導線

**目的**：`env(...)` を書いて拒否されたとき、ユーザーが「どこを触れば通るのか」で迷わないようにする。

**変更**：`main_page.py` の `_apply()` のエラー側を、エラー種別で出し分ける

置換前：

```python
        if not vm.ok:
            self._converted.value = ""
            self._show_error(vm.error.message, vm.error.hint)
            return
```

置換後：

```python
        if not vm.ok:
            self._converted.value = ""
            self._save_button.disabled = True
            self._copy_button.disabled = True
            self._show_error(vm.error.message, vm.error.hint)
            self._settings_link.visible = (vm.error.is_security
                                           and self._on_open_settings is not None)
            if self._settings_link.visible:
                self._pending_capability = vm.error.capability
            return
```

`__init__` に：

```python
        self._pending_capability = ""
        self._settings_link = ft.TextButton(content="設定を開く", icon=ft.Icons.SETTINGS,
                                            visible=False, on_click=self._on_open_settings_click)
```

`_build()` の `status_bar` に `self._settings_link` を足し、ハンドラを書く：

```python
    def _on_open_settings_click(self, e: ft.Event[ft.TextButton]) -> None:
        if self._on_open_settings is not None:
            self._on_open_settings(self._pending_capability)
```

成功時（`_apply()` の成功パス）と `_on_close()` で `self._settings_link.visible = False` に戻す。

**検証（手動）**

- 式に `strenv(PATH)` を入れて実行 → 「この式は 環境変数（env / strenv）を使いますが、許可されていません」＋`[設定を開く]`
- ボタンを押すと設定ページに移り、env のスイッチにフォーカスが当たる
- スイッチを ON にすると自動で再実行され、値が出る

**DoD**

- [ ] 上記の一連が動く
- [ ] セキュリティ以外のエラーでは `[設定を開く]` が出ない

**コミット**：`feat(gui): link security errors to the matching setting`

---

### T3-6. 終了時のキャンセルとダークテーマの初期化

**変更**：`src/yaqpy/gui/_run.py` の `_main` の末尾に足す

```python
    def on_close(e: ft.Event) -> None:
        presenter.cancel()                    # 走っている評価を協調的に止める（リスク R9）

    try:
        page.on_close = on_close
    except Exception:                         # noqa: BLE001 - 属性が無い版でも起動は続ける
        pass

    page.theme_mode = ft.ThemeMode.DARK if state.settings.dark_theme else ft.ThemeMode.LIGHT
```

> `page.on_close` の有無は G0 メモの「Page のメソッド／属性」で確認できます。無ければこのブロックは省いて構いません（`asyncio.to_thread` のスレッドは最終的に終了します）。

**DoD**

- [ ] 重い評価の最中にウィンドウを閉じても、プロセスが残らない（タスクマネージャで確認）
- [ ] フルテストがパス

**コミット**：`feat(gui): cancel running work when the window closes`

---

### T3-7. ドキュメント

**変更 1**：`31_dev-yaqpy/README.md`

「使い方」節の後ろに GUI の節を足す。

````markdown
## GUI（デスクトップアプリ）

```bash
uv sync --extra gui       # GUI を使うときだけ flet が入ります
uv run yaqpy-gui          # 専用コマンド
uv run yaqpy --gui        # CLI のフラグでも起動できます
```

- ファイルを開く（またはドロップ／貼り付け）と、左に**原文そのまま**、右に**変換結果**が出ます
- プロパティのプルダウンから選ぶか、式を直接書いて絞り込めます
- 結果は**別名で保存**できます（開いたファイルは上書きしません）
- 既定は安全側：`env` / `load` 演算子は不許可、タイムアウト 10 秒。設定画面で変えられます

> **依存ゼロについて**：`yaqpy` 本体（ライブラリと CLI）の実行時依存は 0 個のままです。
> `flet` は `[gui]` extra に切り出してあり、テストでも「gui 以外は標準ライブラリのみ」を機械的に検査しています。
> `yaqpy --gui` は flet が無い環境では導入方法を案内して終了するだけで、通常の CLI には影響しません。
````

「リポジトリ構成」の `src/yaqpy/` ツリーに 1 行足す：

```text
├── gui/                            … Flet の GUI（任意依存。presenter は Flet 非依存）
```

**変更 2**：`31_dev-yaqpy/USAGE.ja.md` に「GUI の使い方」節を足す。CLI との対応表を入れる。

| GUI の操作 | 相当する CLI |
|---|---|
| アプリを起動する | `yaqpy --gui`（または `yaqpy-gui`）。※式・ファイルとは併用不可 |
| ファイルを開く | `yaqpy '.' file.yaml` |
| 式に `.server.port` を入れて実行 | `yaqpy '.server.port' file.yaml` |
| 出力形式を json にする | `yaqpy -o json '.' file.yaml` |
| インデントを 4 にする | `yaqpy -I 4 '.' file.yaml` |
| 整形（-P）を ON | `yaqpy -P '.' file.yaml` |
| 結果を別名保存 | `yaqpy '.' file.yaml > out.yaml` |
| 設定で env を許可 | （CLI は既定で許可。GUI は既定で不許可） |

> **注意**：CLI のフラグ名（`-I` など）は `uv run yaqpy --help` で実際の綴りを確認してから書くこと。

**変更 3**：`31_dev-yaqpy/docs/` に、GUI 設計書と 4 つのフェーズプランの写しを置く（基本設計書と同じ運用）。

```bash
cp ../21_docs/0919-02_31_design-yaqpy-gui.md docs/
cp ../21_docs/0919-0[3-6]_31_yaqpy-gui-phase*.md docs/
```

**DoD**

- [ ] README の GUI 節どおりに操作して実際に起動できる
- [ ] CLI 対応表のコマンドが実際に動く（1 つずつ実行して確認）
- [ ] 依存ゼロの説明が誤解を生まない書き方になっている（リスク R6）

**コミット**：`docs(gui): document the desktop app`

---

### T3-8. 受入・手動テストの通し確認

**受入基準（GUI 設計書 2-3）**

| # | シナリオ | 期待 | 結果 |
|---|---|---|---|
| A1 | `examples/sample.yaml` をダイアログで開く | 左に原文、右に YAML、状態バーに件数と時間 | |
| A2 | 出力形式を `json` に変える | 右だけ JSON に変わる | |
| A3 | プルダウンから `.server.port` を選ぶ | 式欄が変わり、右が `8080` | |
| A4 | 式欄に `.items[] \| select(.price > 500)` | 右に `book` の項目 | |
| A5 | 式欄に `.server.(` | 赤枠＋位置つきエラー、実行されない | |
| A6 | `[保存]` で `out.json` を指定 | 右ペインと同内容のファイル。元ファイルは無変化 | |
| A7 | ファイルをドロップ | A1 と同じ（不可環境では代替導線が明示） | |
| A8 | 壊れた YAML を開く | 左に原文、右にエラー（行・列）、落ちない | |

**手動テスト（GUI 設計書 9-3）**

| # | 操作 | 期待 | 結果 |
|---|---|---|---|
| M1 | ダイアログで開く | A1 と同じ | |
| M2 | ドロップで開く | A7 と同じ | |
| M3 | 大きい JSON（数十 MiB）を開いて実行 | UI が固まらず、進捗バーが動き、`[中止]` が効く | |
| M4 | 実行中にウィンドウをリサイズ | 描画が破綻しない | |
| M5 | 長い式を打って 3 文字消して Enter | 検証が追従し、最後の式で 1 回だけ実行 | |
| M6 | 保存で既存ファイルを選ぶ | OS の上書き確認が出る。元ファイルは無傷 | |
| M7 | ダークテーマに切り替え | 両ページで文字が読める | |
| M8 | flet 未導入で `yaqpy-gui` と `yaqpy --gui` | どちらも導入案内＋終了コード 1 | |
| M9 | flet 導入済みで `yaqpy --gui` | `yaqpy-gui` と同じウィンドウが開く | |
| M10 | `yaqpy --gui '.a'` | `cannot be combined` で終了コード 1（GUI は開かない） | |

**M3 用の大きいファイルの作り方**

```bash
uv run python -c "import json,pathlib; pathlib.Path('examples/big.json').write_text(json.dumps([{'i':i,'name':f'item{i}','tags':['a','b','c']} for i in range(200000)]))"
```

（確認が済んだら `examples/big.json` は消すこと。`.gitignore` に入れてもよい。）

**M8 の確認方法**（flet を消さずに試す）

```bash
uv run python -c "
import io, sys
from unittest import mock
from yaqpy.gui import app
err = io.StringIO()
with mock.patch.object(app, 'flet_available', return_value=False):
    print('exit code:', app.main_entry(stderr=err))
print(err.getvalue())
"
```

**M8〜M10 を実機で確かめるコマンド**（`yaqpy --gui`）

```bash
# M8: flet を入れていない環境（extra なしの uv sync 直後）
uv run yaqpy --gui ; echo "exit=$?"          # 導入案内が出て exit=1

# M9: flet を入れた環境
uv run --extra gui yaqpy --gui               # yaqpy-gui と同じウィンドウが開く

# M10: 併用は拒否される（GUI は開かない）
uv run yaqpy --gui '.a' ; echo "exit=$?"     # "cannot be combined ..." が出て exit=1
```

**DoD**

- [ ] A1〜A8 がすべて期待どおり（A7 は G0 の判定に沿った期待）
- [ ] M1〜M10 がすべて期待どおり
- [ ] フルテストがパス
- [ ] `uv run ruff check src tests` に致命的な指摘がない
- [ ] `uv build` が通る

**コミット**：`test(gui): verify all acceptance criteria for v1`

---

## 4. Phase G3（＝GUI v1）の完了条件

| # | 条件 | 確認方法 |
|---|---|---|
| D1 | 受入 A1〜A8 がすべて通る | T3-8 |
| D2 | 手動 M1〜M10 がすべて通る | T3-8 |
| D3 | 自動テストが全件パス | フルテスト |
| D4 | **保存内容が表示の丸めに影響されない** | `test_saves_the_full_text_not_the_display_text` |
| D5 | **元ファイルを黙って上書きしない** | `test_refuses_to_overwrite_the_source_without_confirmation` ＋ 手動 |
| D6 | 本体の実行時依存ゼロが保たれている | `tests.unit.test_architecture` ＋ `pyproject.toml` |
| D7 | README / USAGE に GUI が書かれている | 目視 |

追加されたテスト件数の目安：`test_gui_presenter` +10 = **+10 件**（G0 からの累計 **+107 件**。内訳は G1 が +69、G2 が +28、G3 が +10）。

**マージ**

```bash
cd 31_dev-yaqpy
git checkout main            # 既定ブランチ名は git branch で確認すること
git merge --no-ff feat/gui-g3-save
```

---

## 5. v1 のあとに残した宿題

GUI 設計書 [12 章](./0919-02_31_design-yaqpy-gui.md#12-未決事項) の未決事項のうち、v1 で**やらないと決めた**もの。

| # | 宿題 | 再検討のきっかけ |
|---|---|---|
| Q2 | 複数ファイル（`eval-all`） | 「2 つの設定を比べたい」という要望が出たら |
| Q3 | 元ファイルの上書き（`-i` 相当） | 要望が出たら。**バックアップの自動作成とセット**で設計する |
| Q4 | 行番号・シンタックスハイライト | 大きいファイルを読む用途が増えたら |
| Q5 | 設定の永続化（`ft.SharedPreferences`） | 起動のたびに設定し直す不満が出たら |
| Q6 | 単体 exe 配布（`flet build`） | 非開発者に配る必要が出たら |
| Q7 | yapilet の Flet 1.0 追随 | 本件とは別タスク |
| R4 | デコード中のキャンセル | 巨大ファイルで中止できない苦情が出たら。**コア改修（デコーダに `budget.tick()`）が必要** |

---

## 6. つまずいたときの対処

| 症状 | 対処 |
|---|---|
| 保存したファイルが右ペインより短い | **`display_text` を保存している**。`save()` が `run.full_text` を読んでいるか確認（不変条件 S1） |
| 元ファイルが上書きされた | `_is_source_path` が効いていない。`os.path.realpath` の比較を確認。**すぐに直す（最優先の不具合）** |
| `page.show_dialog` が無い | G0 メモの「Page のメソッド」を見て正しい名前に直す（`page.open` 系の可能性） |
| SnackBar が出ない | ダイアログと同じ経路で出す仕様。`page.show_dialog(ft.SnackBar(...))` が正しいか G0 メモで確認 |
| 設定を変えても結果が変わらない | `build_options()` は実行のたびに呼ばれるので、`SettingsPage` が `state.settings` を書き換えているか確認 |
| `ft.Clipboard()` でコピーできない | サービス登録が要る版かもしれない。`_run.py` で `page.services.append(ft.Clipboard())` を試す |
| 大きいファイルで `[中止]` が効かない | デコード中は効かない仕様（リスク R4）。状態バーに「間もなく停止します」を出す |
| `uv build` が失敗する | `src/yaqpy/gui/` に `__init__.py` があるか、`pages/__init__.py` があるか確認 |

---

## 7. 推奨モデルのまとめ

| タスク | Haiku 4.5 | Sonnet 5 / 4.6 | 理由 |
|---|---|---|---|
| T3-1 | 不可 | **必須** | 保存の不変条件（S1〜S4）を壊さない判断が要る |
| T3-2 | 不可 | **必須** | ダイアログの非同期フローと確認の既定値 |
| T3-3 | やや厳しい | **推奨** | 部品は定型だが、`_run.py` への差し込みで配線ミスが起きやすい |
| T3-4 | 不可 | **必須** | G0 の判定に応じた分岐と、代替導線の設計 |
| T3-5 | やや厳しい | **推奨** | 既存メソッドへの差し込み |
| T3-6, T3-7 | **可** | 可 | 定型。ただし T3-7 は CLI 対応表のコマンドを**実際に動かして**確認させること |
| T3-8 | 可 | 推奨 | チェックリストの消化。**判定は人が見ることを勧める** |

---

## 8. 4 フェーズ全体のまとめ

| Phase | 成果物 | 受入 | 所要 | 主なリスク |
|---|---|---|---|---|
| [G0](./0919-03_31_yaqpy-gui-phaseG0.md) | `docs/flet-1.0-api-notes.md`、gui extra | （検証のみ） | 0.5 日 | ドロップの可否が読めない |
| [G1](./0919-04_31_yaqpy-gui-phaseG1.md) | 改修 A〜D、gui 10 ファイル、2 ペイン、**`yaqpy --gui`** | A1・A2・A8 | 1.5 日 | Flet 1.0 の API 差異 |
| [G2](./0919-05_31_yaqpy-gui-phaseG2.md) | `paths.py`、プロパティ UI、デバウンス | A3・A4・A5 | 1.5 日 | 候補が実行できない式になる |
| [G3](./0919-06_31_yaqpy-gui-phaseG3.md) | 保存・設定・ドロップ・ドキュメント | A6・A7 ＋ 全件 | 1.5 日 | 保存内容の欠損、元ファイル破壊 |

**合計 5.0 日・タスク 35 件・追加テスト約 107 件。**

---

**前**：[Phase G2（フィルタ）](./0919-05_31_yaqpy-gui-phaseG2.md) ／ **設計書**：[GUI 設計書](./0919-02_31_design-yaqpy-gui.md)
