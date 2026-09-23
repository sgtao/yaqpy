# Flet 1.0 API 実測メモ（Phase G0）

| 項目 | 内容 |
|---|---|
| 測定日 | 2026-09-19 |
| flet version | `flet 1.0.0`（`ft.__version__` の実値）。デスクトップ実行には `flet-desktop 1.0.0` も必要で、`ft.run` 初回に自動で導入された（→ 2 章 h） |
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.12（uv 0.11.17） |
| 出典 | 本リポジトリ `_poc/` で実際に動かした結果（公開ドキュメントの記述ではない） |
| 測定方法 | デスクトップ版（`ft.run(main)`）を実際に起動し、ファイルダイアログ等の OS 画面は**入力を自動送信して**操作した。画面は窓キャプチャ（`PrintWindow`）で目視確認し、イベントは PoC 内のログファイルに記録した。人手による確認ではない |

> **G1 以降の読み方**：GUI 設計書のコード例と食い違ったらこのメモが正。特に **2 章（設計書との差分）** と **4 章（`page.update()` の規則）** は G1-T12 のコードに直結する。

## 0. 要点

| # | 結論 |
|---|---|
| 1 | 設計書が使っている Flet 1.0 の型名・メソッド名は**すべて実在**した（`MISSING` なし）。旧 API（`ElevatedButton`・`page.open`・`page.set_clipboard` 等）が廃止済みであることも確認できた |
| 2 | **`Dropdown` に `on_change` は無い**（渡すと `TypeError`）。一覧から選ぶと **`on_text_change` が先、`on_select` が後**に発火する |
| 3 | プルダウンの絞り込みは `options` を差し替える方式だと**キーボードフォーカスが外れる**。**`enable_filter=True`** を使う |
| 4 | 同期ハンドラは実行中の UI 更新を止める。`async def` ＋ `asyncio.to_thread` で解消する。ただし**途中で `page.update()` を呼んだら、最後にも呼ぶ**こと |
| 5 | **OS ファイルドロップは v1 では見送り（段階 3）**。`flet-dropzone` は Flet 標準クライアントに含まれず `Unknown control` になる |

## 1. 確定した API

| 用途 | 実際に動いた書き方 | 備考 |
|---|---|---|
| 起動 | `ft.run(main)` | `main` は同期・`async def` のどちらも可。`view=ft.AppView.WEB_BROWSER, port=…` も指定可（引数として存在。動作は未確認） |
| ウィンドウサイズ | `page.window.width = 1100` / `page.window.height = 760` | 実際の窓の外寸も 1100×760 になった |
| 自動更新 | 4 章を参照 | 規則あり。**要注意** |
| ボタン | `ft.Button(content="…", icon=ft.Icons.FOLDER_OPEN, on_click=…)` | `ft.Button(text=…)` は `TypeError`。`ft.ElevatedButton` は存在しない |
| プルダウン | `ft.Dropdown(options=[ft.DropdownOption(key=…, text=…)], on_select=…, on_text_change=…, editable=True, enable_filter=True)` | 発火順は 2 章 b。`on_*` は `on_animation_end / on_blur / on_focus / on_select / on_size_change / on_text_change` のみ |
| ファイル選択 | `picker = ft.FilePicker()` → `page.services.append(picker)` → `files = await picker.pick_files(...)` | 戻り値は `list[FilePickerFile]`。属性は `name` / `path` / `size`（`sample.yaml` で `size=233` を確認）。**キャンセルは `[]`**。`services` に登録せず `ft.FilePicker()` をその場で作って `await` しても動いた |
| ファイル選択の引数 | `dialog_title` / `allowed_extensions=["yaml", …]` / `allow_multiple` / `initial_directory` / `file_type` / `with_data` | `dialog_title` は OS ダイアログのタイトルになり、`allowed_extensions` は「Files (*.yaml,*.yml,…)」の絞り込みとして効いた |
| 保存ダイアログ | `path = await picker.save_file(dialog_title=…, file_name="output.json", allowed_extensions=["json"])` → `str \| None` | 選択で**フルパスの `str`**、キャンセルは **`None`**。**デスクトップではこの呼び出しだけではファイルは作られない**（書き込みは呼び出し側）。`file_name` は入力欄に初期表示された |
| 保存時の上書き | OS が「名前を付けて保存の確認」を出す | 既存ファイルを指定すると OS 標準の確認が出た。アプリ側で二重に聞かない、という設計書の方針は妥当 |
| フォルダ選択 | `await picker.get_directory_path(...)` | メソッドの存在のみ確認。動作は未確認 |
| 通知 | `page.show_dialog(ft.SnackBar(ft.Text("…"), duration=6000))` | 画面下部に表示された |
| ダイアログ | `page.show_dialog(ft.AlertDialog(modal=True, title=…, content=…, actions=[…]))` / `page.pop_dialog()` | 表示を確認。`pop_dialog()` は閉じた `AlertDialog` を返す |
| クリップボード | `await ft.Clipboard().set(text)` / `await ft.Clipboard().get()` | `page.services` に登録しなくても動いた。OS のクリップボードが実際に書き換わった |
| 複数行テキスト | `ft.TextField(multiline=True, read_only=True, min_lines=3, max_lines=6, text_style=ft.TextStyle(font_family="Consolas"))` | Consolas の等幅で複数行表示された |
| イベント型 | `ft.Event[ft.Button]` / `ft.Event[ft.Dropdown]` | ハンドラの型注釈として使える |
| 非同期タスク | `page.run_task(coroutine_function)` | 心拍タスクの起動に使えた |
| 永続化 | `sp = ft.SharedPreferences()` → `page.services.append(sp)` → `await sp.set(k, v)` / `await sp.get(k)` / `await sp.remove(k)` | `set` → `get` で値が戻ることを確認。`remove` は例外なく呼べた（G3 の設定保存で使える） |
| 入力フィルタ | `ft.NumbersOnlyInputFilter` | クラスの存在のみ確認（インデント欄用） |

## 2. 設計書と違っていた点（G1 以降はこちらが正）

| GUI 設計書の記述 | 実際 | 影響するタスク |
|---|---|---|
| a. 5-3・7-2：「1.0 で `on_change` は編集可能モードの文字入力時に発火。選択は `on_select`」 | **`Dropdown` に `on_change` という引数・属性が存在しない**（`ft.Dropdown(on_change=…)` は `TypeError: unexpected keyword argument`）。文字入力は `on_text_change` | G1-T12、G2-T3 |
| b. フェーズプラン想定：「一覧から選んだとき `on_select` だけが出る」 | **一覧から選ぶと `on_text_change` が先、`on_select` が後**に発火する（`on_text_change` は `value=None`、選んだ文字列は `e.data` と `e.control.text`）。両方にハンドラを付けると選択で 2 回動く | G1-T12、G2-T3 |
| c. 6-3-2：「絞り込みは `on_text_change` で `options` を差し替える」 | ① 入力途中の文字列は **`e.data`（`e.control.text`）**。`e.control.value` は古い値か `None` で使えない。② `on_text_change` 内で **`dd.options` を差し替えると、キーボードフォーカスが外れて 2 文字目以降が入力できない**（実機で再現：`ite` と打って `i` しか入らず、再クリックが必要）。③ **`enable_filter=True` なら全打鍵が入力され、部分一致で絞り込まれる**（`items` → `.items[]` / `.items[].name` / `.items[].price`）。**採用は `enable_filter=True`** | G2-T3 |
| d. 5-7・7-2：「同期ハンドラは UI が固まる」 | 正確には **Python 側のイベントループが塞がり、実行中の UI 更新が届かない**（心拍が 3.01 秒停止、バーもステータスも出ない）。Flutter の窓自体は描画に応答した。結論（`asyncio.to_thread` に逃がす）は設計書どおりで変更なし | G1-T9 |
| e. （記述なし） | **途中で `page.update()` を呼ぶと、ハンドラ終了時の最終状態が自動反映されない**（4 章）。中間表示が要る `async def` ハンドラは**前後で `page.update()`** | G1-T12、G3-T2 |
| f. 6-1-2：ドロップの機能検出は `import flet_dropzone` の成否 | `flet-dropzone` は **import に成功しても描画できない**（`Unknown control: flet_dropzone`）。import の成否は機能検出にならない。v1 は見送りのため G3-T4 では「ドロップ非対応の明示」になり、検出コードは不要 | G3-T4 |
| g. 6-4：保存（`save_file` を呼ぶ記述） | `save_file` は**パスを返すだけ**でファイルを作らない。書き込み（`atomic_write`）は呼び出し側が行う。設計書の書き方（`atomic_write` を呼ぶ）と矛盾はないが、手順として明記が要る | G3-T2 |
| h. 4-1：`gui = ["flet>=1.0,<2"]` | `flet` 単体には**デスクトップクライアントが含まれない**。`ft.run` 初回に `flet-desktop` を自動で導入し、クライアント本体を `~/.flet/client/` へ展開する（「Preparing Flet v1.0.0 for the first use」と表示。**初回にネットワークが要るかどうかは未検証**）。再現性のため extra を **`flet[desktop]>=1.0,<2`** にするかは G1-T1 で判断（→ 6 章） | G1-T1 |
| i. （G2 で確認）フェーズプラン G2-T3：「`editable=True` の Dropdown で、`on_text_change` から `options` を差し替えて絞り込む」 | **`enable_filter=True` を採用**（代替案の別 `TextField` は不要）。`options` は候補の全件を一度だけ入れて触らない。実機で `port` と打つと全打鍵が入り、`.server.port  = 8080` だけに絞られた。候補の選択は `on_select` で、`e.control.value` には表示文字列ではなく **`DropdownOption.key`**（式）が入る。`key` と `text` を別にしても動く。絞り込みは **表示文字列（`text`）に効く**（`key` に無い値 `pen` が、`text` の `.items[].name  = pen` に一致した。G3 で確認） | G2-T3 |
| j. （G3 で確認）フェーズプラン G3-T6：「`page.on_close` で走っている評価をキャンセルする」 | **`page.on_close` は窓を閉じた直後には発火しない**（セッションが期限切れになったときの通知）。窓の終了は **`page.window.on_event` の `WindowEventType.CLOSE`**（`prevent_close=True` のとき）で受ける。さらに、**Windows の Flet 1.0.0 では、`FilePicker` でファイルを選んだあとに窓を閉じると、窓は消えるのに `flet.exe` と Python が終了せず残る**（`FilePicker` だけの最小アプリでも再現。選ばずにキャンセルした場合・貼り付けのみ・何も操作しない場合は 1 秒で終了）。`window.destroy()` だけでは直らず、`os._exit` だけでは `flet.exe` が孤児で残る。**CLOSE イベントで `taskkill /F /T /PID <自分>` して子のクライアントごと落とす**と、1 秒以内に両方終了した | G3-T6 |
| 差分なし | `ft.Button(content=…)`、`page.services` への `FilePicker`、`await pick_files()`・`save_file()`、`page.show_dialog` / `pop_dialog`、`page.on_resize`、`Tab.label`、`ft.Icons.*`、`ft.Clipboard`、`ft.TextField(read_only, multiline, text_style)`、`ft.SharedPreferences` | — |

## 3. MISSING だった API

`p2_api_probe.py` の対象 25 名（`run` `Page` `Button` `IconButton` `TextField` `Dropdown` `DropdownOption` `FilePicker` `SnackBar` `AlertDialog` `ProgressBar` `SafeArea` `Column` `Row` `Container` `Divider` `Text` `Icon` `Switch` `Checkbox` `Clipboard` `Colors` `Icons` `TextStyle` `SharedPreferences`）は**すべて `OK`。`MISSING` は 0 件**。`TextField` の属性 11 個（`multiline` `read_only` `min_lines` `max_lines` `text_style` `expand` `border` `value` `on_change` `on_submit` `error`）もすべて存在した。`ft.DropdownOption` は存在したので、旧 `ft.dropdown.Option` 形式の調査は不要。

設計書が「廃止」とした旧 API が**本当に無い**ことも確認した。

| 旧 API | 実測 |
|---|---|
| `ft.ElevatedButton` | 存在しない |
| `ft.Button(text=…)` | `TypeError`（`content=` が正） |
| `page.open` / `page.close` | 存在しない（`show_dialog` / `pop_dialog` が正） |
| `page.set_clipboard` | 存在しない（`ft.Clipboard` が正） |
| `page.on_resized` | 存在しない（`page.on_resize` が正） |
| `ft.Tab(text=…)` | 存在しない（`label=` が正） |
| `ft.Dropdown(on_change=…)` | `TypeError`（2 章 a） |

> プローブの「ドロップ関連の候補」は `Dropdown` 系 6 件が**部分一致で誤ヒット**しただけで、ドロップ機能ではない（5 章）。

## 4. ブロッキング挙動（T0-6）

3 秒の CPU 処理（`heavy()`）を 4 通りで比較した。「心拍」はイベントループ上で 50 ms ごとに時刻を記録する計測タスクで、塞がれると間隔が伸びる。

| 案 | ハンドラの書き方 | 心拍の停止 | 実行中の画面 | 終了後の画面 |
|---|---|---|---|---|
| A | 同期ハンドラで直接 `heavy()` | **3.01 秒停止** | バー・ステータスとも**出ない** | 完了表示が出る |
| B | `async def` ＋ 途中で `page.update()` ＋ `await asyncio.to_thread(heavy)`（終了後の `update` なし） | 最大 0.10 秒 | バー・ステータスが**出る** | **完了表示が出ず、バーが回り続ける**（8 秒後も未反映） |
| C | `async def` ＋ `await asyncio.to_thread(heavy)`（`update` なし） | 最大 0.10 秒 | **何も出ない**（3 秒後に一括反映） | 完了表示が出る |
| D | `async def` ＋ **前後で `page.update()`** ＋ `await asyncio.to_thread(heavy)` | 最大 0.10 秒 | バー・ステータスが**出る** | **完了表示が出る** |

- 同期ハンドラで 3 秒の CPU 処理 → **UI 更新が止まった**（Python 側のループが塞がれた。ハンドラは `MainThread` で実行されていた）。Flutter の窓自体は描画に応答した（窓キャプチャが 114 ms で返った）。実行中に窓をドラッグして動くかの目視は未確認。
- `await asyncio.to_thread(...)` → **ループは応答した**（心拍の最大間隔 0.10 秒）。
- **ハンドラ途中の `page.update()` は「実行中の表示を出したいなら必要」**。ただし**一度でも `page.update()` を呼ぶと、ハンドラ終了時の自動反映が効かなくなる**（B と D の差）。ルールは次のとおり：
  - 中間表示が不要 → `page.update()` を一切書かない（C。終了時に一括反映される）
  - 中間表示が必要 → **開始側と終了側の両方**で `page.update()`（D）
- **結論**：G1-T9 の Presenter は `asyncio.to_thread` 方式を**採用する**。G1-T12 のハンドラは「開始で `update`、`await`、終了で `update`」の D の形で書く。

## 5. ファイルドロップの判定（T0-7）★ G3-T4 の分岐

- 判定：**段階 3: v1 は見送り**
- 根拠：
  - **段階 1（本体機能）**：なし。`dir(ft)` の `drop` を含む名前は `Dropdown` 系のみ。`flet` パッケージ内で `Drag` 系を含むのは `drag_target.py` / `draggable.py`（**アプリ内ドラッグ専用**）だけで、`Page` に `on_drop` 相当もない。
  - **段階 2（`flet-dropzone`）**：`flet-dropzone 0.4.0`（`flet>=0.80` 要求）は `uv run --with flet-dropzone` で導入でき、`from flet_dropzone import Dropzone` も通った。しかし**実機で `Unknown control: flet_dropzone`（赤い帯）が出て描画されない**。原因は、`uv run` / pip で配布される Flet 標準クライアント（`flet-desktop-full-1.0.0`）に、`desktop_drop` を含む Flutter プラグインが組み込まれていないこと（クライアントのプラグイン DLL 一覧に該当なし）。Flutter 拡張を使うには **`flet build` で独自クライアントをビルド**する必要があり（Flutter SDK が必要）、`pip install yaqpy[gui]` で配る構成と合わない。
  - `pyproject.toml` と `uv.lock` は、試験に `uv run --with` を使ったため**変更していない**。
- 採用する場合の実装メモ：（該当なし）参考として、`flet-dropzone` の API は `Dropzone(content=…, on_dropped=…)`、イベントの `e.files`（`DropzoneFile` のリスト、`.path` あり）、`await dz.read_bytes(file)`。実機で描画できていないため、**このイベント経由でパスが取れるかは未確認**。
- 見送る場合の代替導線：**ダイアログ（`FilePicker`）＋ 貼り付け**。G3-T4 は「ドロップ非対応の明示と代替導線」に置き換える。
- 再検討の条件：`flet build` による独自クライアント配布を採用するとき、または Flet 本体に OS ファイルドロップが取り込まれたとき。

## 6. 未確認のまま残した項目

- プルダウンの絞り込み（`enable_filter=True`）の**大文字小文字の扱い**、日本語入力（IME）中の `on_text_change` の発火
- `save_file(src_bytes=…)` の挙動（Web・モバイル向けの引数と思われる）
- Web ブラウザ表示（`ft.AppView.WEB_BROWSER`）での各挙動（本 PoC はデスクトップのみで実施）
- `pick_files(with_data=True)` と巨大ファイルの扱い、`get_directory_path()` の動作
- 実行中に**窓をドラッグ・リサイズして固まらないか**の人手による目視（窓キャプチャの応答のみ確認）
- macOS / Linux での挙動（Windows のみで実施）
- ウィンドウを閉じたときの `page.on_close` の発火と `to_thread` の残留（設計書 R9）
- **macOS / Linux で、`FilePicker` のあとに窓を閉じたときの終了**（上の j は Windows のみで確認。現状 Windows 以外は `page.on_close` のみで、CLOSE イベントでの終了処理は入れていない）
- `ft.Switch` に `focus()` が無い、`ft.ButtonStyle` が色を受け取れない（G3 で確認。代替は実装済み）
- `ft.run` 初回の導入（`flet-desktop` の pip 導入とクライアントの展開）に**ネットワークが要るか・所要時間**、**オフライン環境での失敗の仕方**
- `flet build` による独自クライアントで `flet-dropzone` が動くか
- `yaqpy[gui]` の extra を **`flet[desktop]>=1.0,<2` にするか**の判断（`flet` 単体だと初回実行時に自動導入されるが、クリーン環境・オフライン環境での再現性が下がる。G1-T1 で決める）
- Web ブラウザ表示の各挙動 → **7 章（W0）で確認した**

## 7. Web 表示（Phase W0、v0.6.0）

| 項目 | 内容 |
|---|---|
| 測定日 | 2026-09-23 |
| 版 | `flet 1.0.0`、`flet-web 1.0.0`（`uv add --optional web "flet[web]>=1.0,<2"` で導入。`fastapi 0.141.1`・`uvicorn 0.53.0` が付いてくる） |
| 測定方法 | リポジトリ外の最小アプリ 2 本（`ft.run(..., view=WEB_BROWSER)` 版と、`flet.fastapi.app` ＋ `uvicorn` を自分で組む版）を起動し、Claude Code デスクトップアプリの**組み込みブラウザ**で操作した。イベントはアプリ内のログファイルに記録。ファイル選択は、組み込みブラウザが OS のダイアログを出さないため、**ページ内の `<input type=file>` の `click` を JS で差し替え、`DataTransfer` で作った `File` を選ばせた**（ブラウザ → サーバーの受け渡しは本物の経路） |

### 7-1. 結論

| # | 確認項目（計画書 5-5 W0） | 結果 |
|---|---|---|
| 0 | **待ち受けアドレス** | `ft.run(main, host=None, view=WEB_BROWSER)` は **`0.0.0.0` と `::`（全インターフェース）で待ち受けた**（`Get-NetTCPConnection` で確認）。uvicorn の `Config(host=None)` がそのまま渡るため。**yaqpy は `127.0.0.1` を必ず明示する** |
| 1 | ファイル選択 | `pick_files()` の `path` は **常に `None`**（`FilePickerFile.path` の docstring どおり）。中身の受け取り方は 2 通り（7-2）。**yaqpy はアップロード経路（B）を採る** |
| 2 | 保存 | `save_file(file_name=…, src_bytes=…)` で**ブラウザのダウンロード**になった。中身はバイト単位で一致（UTF-8 の日本語を含む 12 バイト）。戻り値は `None`。`src_bytes`・`file_name` が無いと Web では `ValueError`（ソースで確認） |
| 3 | クリップボード | 組み込みブラウザでは `ft.Clipboard().set()` が **`PlatformException(copy_fail, Clipboard.setData failed.)`** で失敗した。`navigator.permissions.query({name: "clipboard-write"})` が `denied`（`isSecureContext` は true、`document.hasFocus()` も true）で、**このブラウザの権限の方針**による。一般のブラウザでは未確認。**コピーは失敗しうる前提で、例外を受けて案内を出す**。なお、実装後の yaqpy（同じ組み込みブラウザ）では、ボタンのクリックからのコピーが**成功した**（OS のクリップボードに書き込まれた）。成否は環境（ブラウザの権限・操作の直後かどうか）で変わる |
| 4 | `SharedPreferences` | Web でも `set` / `get` が動いた。保存先は**ブラウザ側**で、同じブラウザの 2 つ目のタブでは前の値が読めた（タブ間で共有される） |
| 5 | デスクトップ専用 API | `page.web` は `True`、`page.platform` は `WINDOWS`（ブラウザの OS）。`page.window.width`・`prevent_close`・`on_event` への代入は**例外にならない**（効果もない）。終了ボタン・窓のイベントは Web では出さない／登録しない |
| 6 | 同時利用の分離 | 2 つのタブはそれぞれ**別の `Page`（別セッション）**で `main` が呼ばれ、入力が混ざらなかった。**同じタブの再読み込みは同じセッションに戻る**（前の状態が残る）。モジュールの大域変数はプロセスで共有されるので、アプリ側の大域変数（`texts.select_language` など）は分離されない |

### 7-2. ファイルの受け渡し：2 つの経路

| 経路 | 書き方 | 結果 |
|---|---|---|
| A. `with_data=True` | `files = await picker.pick_files(allow_multiple=True, with_data=True)` → `f.bytes` | 動く（2 件同時・10 MiB も可）。ただし中身は **WebSocket の 1 通**で送られ、**20 MiB では接続が切れた**（uvicorn の `ws_max_size` 既定 16 MiB）。切れたセッションは以後 `pick_files` が「invoke method listener」待ちのタイムアウトになり、**再読み込みまで使えない**。**サイズを確かめる前に全量が送られる**ので、上限で断れない |
| B. アップロード | `pick_files()`（中身なし）で `name`・`size` を得る → 上限を超えるものは**送らずに断る** → `page.get_upload_url(保存名, 秒)` → `picker.upload([FilePickerUploadFile(upload_url=…, id=…, name=…)])` → `on_upload` の `progress == 1.0` を待ってサーバー側のファイルを読む | 動く。HTTP の PUT なので WebSocket の上限に当たらない。サーバー側の `max_upload_size` を超えると `on_upload` に **413 のエラー**が来る |

経路 B の注意（すべて実測・ソースで確認）

- **`ft.run` からは使えない**：`ft.run(upload_dir=…)` は内部の `flet_web.fastapi.app` に `upload_endpoint_path` と `secret_key` を渡さないため、`page.get_upload_url` が `upload_path should be specified to enable uploads` になる。**`flet.fastapi.app(main, upload_dir=…, upload_endpoint_path="upload", max_upload_size=…, secret_key=…)` を自分で組み、uvicorn で起動する**
- `upload_endpoint_path` は**先頭の `/` を付けない**（`"upload"`）。ルートが `f"/{upload_endpoint_path}"` で組まれるため、`"/upload"` だと `//upload` になり **405** が返った
- **複数ファイルは `id` の大きい順に**アップロードする。クライアント（Dart の `FilePicker.uploadFiles`）はアップロードが済んだファイルを選択一覧から `_files.remove(file)` で**取り除く**ため、`id`（＝一覧の添字）が前詰めにずれ、小さい順だと 2 件目以降が見つからない（`File '…' (id: 2) not found`。イベントも来ない）。`name` も渡すと、`id` で見つからないときに名前で探す
- サーバー側の上限（413）で断られても、**上限までの途中のファイルがディスクに残る**（1 MiB 上限で 1,048,576 バイトが残った）。**エラーのときも自分で消す**
- アップロード URL は署名つき（`secret_key`）で有効期限がある。ファイル名はセッションごとの一意な名前にする（元のファイル名はパスに使わない）

### 7-3. そのほか

- `flet-web` が無いと、`ft.run(view=WEB_BROWSER)` は実行時に pip で `flet-web` を入れようとする（`ensure_flet_web_package_installed`）。yaqpy は extra（`[web]`）で入れる
- Web クライアント一式（`canvaskit` など、約 73 MB）は `flet_web/web/` に同梱されている。`no_cdn=True` で CDN を使わない（外部へ取りに行かない）。**ただし `no_cdn=True` では日本語の文字が「□」になった**（実装後の実機確認。英数字は表示される。`FLET_WEB_NO_CDN=false` で CDN を使うと正しく表示された）。Flutter の Web は OS のフォントを使えず、同梱の資産に日本語のフォントが無いため。**yaqpy の既定は CDN を使う**（Flet の既定と同じ）。オフライン向けに `--no-cdn`（`--lang en` を勧める）
- `view=WEB_BROWSER` は起動時に**既定のブラウザを開く**（`webbrowser`）。`FLET_FORCE_WEB_SERVER=1` なら開かない。自分で uvicorn を組む場合はどちらも関係しない
- Linux で `DISPLAY` が無い（ヘッドレス）と、Flet は `ft.run` を強制的に Web サーバーにする（`is_linux_server()`）

### 7-4. 未確認のまま残した項目

- 一般のブラウザ（Chrome・Edge・Firefox）での実機操作。特に**クリップボード**（`localhost` は安全なコンテキストなので許可される見込みだが未確認）と、**OS のファイル選択ダイアログ**からの選択
- `http://` で他の端末から開いたとき（安全なコンテキストでない）のクリップボード
- 長時間放置したセッションの破棄（`page.on_close` の発火までの時間）
