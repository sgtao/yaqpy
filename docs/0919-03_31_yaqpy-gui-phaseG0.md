# yaqpy GUI 実装プラン — Phase G0（事前検証・PoC）

| 項目 | 内容 |
|---|---|
| 文書 ID | 0919-03_31_yaqpy-gui-phaseG0 |
| 版 | 第1.0版 |
| 作成日 | 2026-09-19 |
| 親文書 | [`0919-02_31_design-yaqpy-gui.md`](./0919-02_31_design-yaqpy-gui.md)（以下「GUI 設計書」）の [8 章 Phase G0](./0919-02_31_design-yaqpy-gui.md#8-段階計画phase-g0g3) |
| 作業リポジトリ | `31_dev-yaqpy/`（**ここが git リポジトリのルート**。親フォルダは git 管理外） |
| ブランチ | `feat/gui-g0-poc` |
| 目的 | **本実装を始める前に、前提が本当に成り立つかを実機で確かめる**。ここで得た事実を G1〜G3 が参照する |
| 所要 | 0.5 日（タスク 8 件） |
| 推奨モデル | **Sonnet 5 / Sonnet 4.6**（外部調査と判断を含むため）。Haiku 4.5 は T0-1・T0-8 のみ可 |

---

## 0. このファイルの使い方

1. このファイルを Claude Code に渡し、**タスク T0-1 から順に**実行させる。
2. 各タスクは「目的 → 実行する内容 → 検証 → DoD（完了の定義）」の 4 点セット。**DoD を満たすまで次へ進まない**。
3. 1 タスク = 1 コミット。コミットメッセージの雛形は各タスクに書いてある。
4. **G0 の最大の成果物は動くコードではなく `docs/flet-1.0-api-notes.md`（実測メモ）** です。G1〜G3 のコード骨格はこのメモで答え合わせします。

> **重要**：GUI 設計書のコード例は、公開ドキュメントから確認できた範囲の Flet 1.0 API で書いてあります。**実機で違っていたらメモの方が正**です。G1 以降は必ずメモを優先してください。

---

## 1. Phase G0 のゴール

| # | 確かめること | なぜ必要か | 結果の使い道 |
|---|---|---|---|
| V1 | Flet 1.0 が uv の extra として入り、ウィンドウが開く | すべての前提 | G1 以降 |
| V2 | `ft.run` / `page.window` / `page.services` / `ft.DropdownOption` などの**実際のシグネチャ** | 設計書のコード例が正しいか | G1〜G3 のコード骨格 |
| V3 | `FilePicker` の `pick_files()` / `save_file()` が await で結果を返すか | G-FR-01・G-FR-09 | G1-T12・G3-T2 |
| V4 | `Dropdown` の `on_select` と `on_text_change` の発火タイミング | G-FR-07 の絞り込み UI | G2-T3 |
| V5 | **同期ハンドラで重い処理を書くと UI が固まるか**（`asyncio.to_thread` で解消するか） | G-NFR-01 の設計根拠 | G1-T9 |
| V6 | **OS からのファイルドロップが可能か**（本体機能 or `flet-dropzone` or 不可） | G-FR-02 の分岐 | G3-T4 |
| V7 | `ft.SnackBar` / `ft.AlertDialog` の出し方 | 保存完了通知・上書き警告 | G3-T2 |

---

## 2. タスク一覧

| # | タスク | 推奨モデル | 触るもの | 所要 |
|---|---|---|---|---|
| T0-1 | ブランチ作成と flet の導入 | Haiku 4.5 可 | `pyproject.toml`, `uv.lock` | 10 分 |
| T0-2 | 空ウィンドウの起動確認 | Sonnet | `_poc/p1_window.py` | 15 分 |
| T0-3 | API 実測プローブ（V2・V6 の一次調査） | Sonnet | `_poc/p2_api_probe.py` | 30 分 |
| T0-4 | FilePicker の素振り（V3） | Sonnet | `_poc/p3_filepicker.py` | 30 分 |
| T0-5 | Dropdown のイベント検証（V4） | Sonnet | `_poc/p4_dropdown.py` | 20 分 |
| T0-6 | UI 固まり検証（V5） | Sonnet | `_poc/p5_blocking.py` | 30 分 |
| T0-7 | ファイルドロップの PoC（V6 の本番判定） | Sonnet | `_poc/p6_drop.py` | 45 分 |
| T0-8 | 実測メモの作成と分岐の確定 | Haiku 4.5 可 | `docs/flet-1.0-api-notes.md` | 30 分 |

---

## 3. 各タスクの詳細

### T0-1. ブランチ作成と flet の導入

**目的**：`yaqpy[gui]` の extra を作り、Flet 1.0 を開発環境に入れる。

**実行**

```bash
cd 31_dev-yaqpy
git checkout -b feat/gui-g0-poc
```

`pyproject.toml` に PoC 用の作業ディレクトリを無視する設定を足す（`.gitignore` に追記）：

```gitignore
# PoC（Phase G0 限り。G1 開始時に削除する）
_poc/
```

extra を追加する：

```bash
uv add --optional gui "flet>=1.0,<2"
uv sync --extra gui
```

> `uv add --optional gui` は `[project.optional-dependencies] gui = [...]` に書き込みます。**手で `pyproject.toml` を編集せず、必ずこのコマンドを使う**こと（`uv.lock` が同時に更新されるため）。

**検証**

```bash
uv run --extra gui python -c "import flet; print(flet.__version__)"
```

**DoD**

- [ ] `pyproject.toml` に `[project.optional-dependencies]` の `gui` が入っている
- [ ] `dependencies = []`（本体の依存ゼロ）が**変わっていない**
- [ ] 上記コマンドが `1.x.x` を表示する
- [ ] `uv run python -m unittest discover -s tests/unit -t .` が**全件パスのまま**（extra を足しただけで既存が壊れていないこと）

**コミット**：`chore(gui): add flet as an optional 'gui' extra`

---

### T0-2. 空ウィンドウの起動確認

**目的**：`ft.run()` でウィンドウが開くこと、`page.window` 系の属性名を確かめる。

**作成**：`31_dev-yaqpy/_poc/p1_window.py`

```python
"""PoC 1: 空ウィンドウが開くか。page.window の属性名を確かめる。"""

from __future__ import annotations

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "yaqpy GUI PoC"

    log: list[str] = []

    # ウィンドウサイズの指定方法を 2 通り試し、通った方を記録する
    try:
        page.window.width = 1100
        page.window.height = 760
        log.append("OK: page.window.width / page.window.height")
    except Exception as e:  # noqa: BLE001 - PoC なので握りつぶして記録する
        log.append(f"NG: page.window.* -> {type(e).__name__}: {e}")

    log.append(f"flet version: {ft.__version__}")

    page.add(
        ft.SafeArea(
            content=ft.Column([ft.Text(line, selectable=True) for line in log]),
        )
    )


if __name__ == "__main__":
    ft.run(main)
```

**検証**

```bash
uv run --extra gui python _poc/p1_window.py
```

**DoD**

- [ ] デスクトップウィンドウが開く
- [ ] 画面に表示された `OK:` / `NG:` の行を**そのまま控える**（T0-8 でメモに転記する）
- [ ] `ft.__version__` の実値を控える

**コミット**：不要（`_poc/` は `.gitignore` 済み）。控えた内容は T0-8 でコミットする。

---

### T0-3. API 実測プローブ

**目的**：GUI 設計書が前提にしている API 名が**実物に存在するか**を機械的に確かめる。ドロップ関連の有無もここで一次調査する。

**作成**：`31_dev-yaqpy/_poc/p2_api_probe.py`

```python
"""PoC 2: Flet 1.0 の API 実測プローブ。標準出力の結果をメモに転記する。"""

from __future__ import annotations

import flet as ft

EXPECTED_TOP_LEVEL = [
    "run", "Page", "Button", "IconButton", "TextField", "Dropdown", "DropdownOption",
    "FilePicker", "SnackBar", "AlertDialog", "ProgressBar", "SafeArea", "Column", "Row",
    "Container", "Divider", "Text", "Icon", "Switch", "Checkbox", "Clipboard",
    "Colors", "Icons", "TextStyle", "SharedPreferences",
]


def probe() -> None:
    print(f"# flet version: {ft.__version__}")

    print("\n## トップレベル API の有無")
    for name in EXPECTED_TOP_LEVEL:
        print(f"{name:20} {'OK' if hasattr(ft, name) else 'MISSING'}")

    print("\n## Page のメソッド／属性（関心のあるものだけ）")
    keys = [k for k in dir(ft.Page) if not k.startswith("_")]
    for kw in ("dialog", "window", "run_", "service", "overlay", "clipboard", "drop", "resize",
               "close", "theme"):
        hits = sorted(k for k in keys if kw in k.lower())
        print(f"{kw:10} -> {hits}")

    print("\n## ドロップ関連の候補（V6 の一次調査）")
    print("flet top-level :", sorted(k for k in dir(ft) if "drop" in k.lower()))
    print("Page           :", sorted(k for k in keys if "drop" in k.lower()))

    print("\n## Dropdown のイベント引数")
    print(sorted(k for k in dir(ft.Dropdown) if k.startswith("on_")))

    print("\n## FilePicker のメソッド")
    print(sorted(k for k in dir(ft.FilePicker) if not k.startswith("_")))

    print("\n## TextField の属性（複数行・読み取り専用まわり）")
    tf = [k for k in dir(ft.TextField) if not k.startswith("_")]
    for kw in ("multiline", "read_only", "min_lines", "max_lines", "text_style", "expand",
               "border", "value", "on_change", "on_submit", "error"):
        print(f"{kw:12} {'OK' if kw in tf else 'MISSING'}")


if __name__ == "__main__":
    probe()
```

**検証**

```bash
uv run --extra gui python _poc/p2_api_probe.py > _poc/probe.txt
cat _poc/probe.txt
```

**DoD**

- [ ] `MISSING` になった名前を**すべて列挙できる**（T0-8 でメモに「設計書の修正が必要な箇所」として書く）
- [ ] 「ドロップ関連の候補」の出力を控える。**`DropZone` / `on_drop` 相当が存在すれば V6 は「本体機能あり」で確定**
- [ ] `ft.Dropdown` の `on_*` 一覧に `on_select` と `on_text_change` があるか確認

> **判断基準**：`ft.DropdownOption` が MISSING なら旧 `ft.dropdown.Option` 形式の可能性がある。その場合は `dir(ft.dropdown)` も調べてメモに残すこと。

---

### T0-4. FilePicker の素振り

**目的**：ファイルを開くダイアログと保存ダイアログが、**await で結果を返す**ことを確かめる（V3）。

**作成**：`31_dev-yaqpy/_poc/p3_filepicker.py`

```python
"""PoC 3: FilePicker（サービス）の pick_files / save_file を await で使う。"""

from __future__ import annotations

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "PoC: FilePicker"

    picker = ft.FilePicker()
    page.services.append(picker)          # 1.0 では overlay ではなく services

    out = ft.Text("", selectable=True)

    async def on_open(e: ft.Event[ft.Button]) -> None:
        files = await picker.pick_files(
            dialog_title="YAML/JSON を選んでください",
            allow_multiple=False,
            allowed_extensions=["yaml", "yml", "json", "toon", "properties"],
        )
        if not files:
            out.value = "（キャンセルされました）"
            return
        f = files[0]
        out.value = f"name={f.name}\npath={f.path}\nsize={f.size}\ntype={type(f).__name__}"

    async def on_save(e: ft.Event[ft.Button]) -> None:
        path = await picker.save_file(
            dialog_title="保存先を選んでください",
            file_name="output.json",
            allowed_extensions=["json"],
        )
        out.value = f"save_file -> {path!r} (type={type(path).__name__})"

    page.add(
        ft.SafeArea(
            content=ft.Column([
                ft.Row([
                    ft.Button(content="ファイルを開く", icon=ft.Icons.FOLDER_OPEN, on_click=on_open),
                    ft.Button(content="名前を付けて保存", icon=ft.Icons.SAVE, on_click=on_save),
                ]),
                out,
            ])
        )
    )


if __name__ == "__main__":
    ft.run(main)
```

**検証**

```bash
uv run --extra gui python _poc/p3_filepicker.py
```

**DoD**

- [ ] 「ファイルを開く」でダイアログが出て、選んだファイルの `name` / `path` / `size` が画面に出る
- [ ] キャンセル時に空リスト（または falsy）が返ることを確認
- [ ] 「名前を付けて保存」で保存先パスが**文字列で**返ることを確認（`None` はキャンセル）
- [ ] `allowed_extensions` が効いているか（拡張子で絞られるか）を目視で確認

> エラーになったら**引数名を削って**最小形（`await picker.pick_files()`）から試し、通った形をメモに残すこと。

---

### T0-5. Dropdown のイベント検証

**目的**：G-FR-07 の「プルダウン＋絞り込み」を成立させるため、どのイベントがいつ発火するかを確かめる（V4）。

**作成**：`31_dev-yaqpy/_poc/p4_dropdown.py`

```python
"""PoC 4: Dropdown の on_select / on_text_change の発火タイミング。"""

from __future__ import annotations

import flet as ft

CANDIDATES = [".server", ".server.port", ".server.hosts[]", ".items[]", ".items[].name",
              ".items[].price", ".backup.schedule"]


def main(page: ft.Page) -> None:
    page.title = "PoC: Dropdown"
    log = ft.Column([], scroll=ft.ScrollMode.AUTO, height=300)

    def add(line: str) -> None:
        log.controls.append(ft.Text(line, size=12, selectable=True))

    def on_select(e: ft.Event[ft.Dropdown]) -> None:
        add(f"on_select      value={e.control.value!r}")

    def on_text_change(e: ft.Event[ft.Dropdown]) -> None:
        add(f"on_text_change value={e.control.value!r}")
        # 入力した文字で候補を絞れるか（部分一致）を試す
        q = (e.control.value or "").lower()
        dd.options = [ft.DropdownOption(key=c, text=c) for c in CANDIDATES if q in c.lower()]

    dd = ft.Dropdown(
        label="プロパティ",
        editable=True,
        width=420,
        options=[ft.DropdownOption(key=c, text=c) for c in CANDIDATES],
        on_select=on_select,
        on_text_change=on_text_change,
    )

    page.add(ft.SafeArea(content=ft.Column([dd, ft.Divider(), log])))


if __name__ == "__main__":
    ft.run(main)
```

**検証**

```bash
uv run --extra gui python _poc/p4_dropdown.py
```

**DoD**

- [ ] 一覧から選んだとき **`on_select` だけ**が出る（`on_text_change` も出るなら、その事実をメモする）
- [ ] 文字を打ったとき `on_text_change` が出て、**候補が絞り込まれる**
- [ ] `editable=True` が受け付けられる（エラーにならない）
- [ ] `ft.DropdownOption(key=..., text=...)` が受け付けられる

> 絞り込みが動かない場合、G2-T3 は「別の `TextField` で絞り込み、`Dropdown.options` を差し替える」方式に切り替えます。**どちらになったかをメモに明記**してください。

---

### T0-6. UI 固まり検証

**目的**：GUI 設計書 5-7 の根拠（「Flet 1.0 の同期ハンドラはイベントループを塞ぐ」）を**自分の目で**確かめる（V5）。ここが崩れると G1 の設計が変わります。

**作成**：`31_dev-yaqpy/_poc/p5_blocking.py`

```python
"""PoC 5: 重い同期処理を (A) そのまま書いた場合と (B) to_thread に逃がした場合の比較。"""

from __future__ import annotations

import asyncio
import time

import flet as ft


def heavy() -> int:
    """CPU を 3 秒ほど使う（yaqpy の評価の代役）。"""
    total = 0
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        total += 1
    return total


def main(page: ft.Page) -> None:
    page.title = "PoC: blocking"
    bar = ft.ProgressBar(width=400, visible=False)
    status = ft.Text("")

    def on_sync(e: ft.Event[ft.Button]) -> None:
        bar.visible = True
        status.value = "同期で実行中…（バーは出るか？）"
        n = heavy()
        bar.visible = False
        status.value = f"同期 完了 {n}"

    async def on_async(e: ft.Event[ft.Button]) -> None:
        bar.visible = True
        status.value = "to_thread で実行中…"
        page.update()                      # 1.0 は自動更新だが、ハンドラ途中の反映は明示が要る場合がある
        n = await asyncio.to_thread(heavy)
        bar.visible = False
        status.value = f"async 完了 {n}"

    page.add(ft.SafeArea(content=ft.Column([
        ft.Row([
            ft.Button(content="A: 同期で重い処理", on_click=on_sync),
            ft.Button(content="B: to_thread で重い処理", on_click=on_async),
        ]),
        bar,
        status,
        ft.Text("実行中にこのウィンドウをドラッグ・リサイズしてみること", size=12),
    ])))


if __name__ == "__main__":
    ft.run(main)
```

**検証**

```bash
uv run --extra gui python _poc/p5_blocking.py
```

**DoD**

- [ ] **A**：進捗バーが出ない／ウィンドウが動かせない（＝設計書どおり塞ぐ）ことを確認
- [ ] **B**：進捗バーが動き、実行中もウィンドウを動かせることを確認
- [ ] B で `page.update()` が必要だったか不要だったかをメモする（G1-T12 の書き方が変わる）

> **もし A でも固まらなかった場合**：`asyncio.to_thread` は不要になりますが、**それでも B の形を採用**します（将来の Flet 更新で挙動が戻る可能性があり、害もないため）。その事実はメモに残してください。

---

### T0-7. ファイルドロップの PoC（最重要）

**目的**：G-FR-02 の実現可否を確定させる（V6）。GUI 設計書 [6-1-2](./0919-02_31_design-yaqpy-gui.md#6-1-2-ドロップの実現方針重要要-poc) の分岐を決めます。

**手順は 3 段階。上から順に試し、通った時点で止める。**

#### 段階 1：Flet 本体に機能があるか

T0-3 の「ドロップ関連の候補」の出力を見る。`DropZone`・`on_drop`・`on_files_dropped` のような名前があれば、それを使う最小コードを `_poc/p6_drop.py` に書いて確かめる。

```python
"""PoC 6-a: 本体のドロップ機能を使う（T0-3 で名前が見つかった場合のみ）。"""

from __future__ import annotations

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "PoC: drop (built-in)"
    out = ft.Text("ここにファイルをドロップしてください", selectable=True)

    # ↓ T0-3 で見つかった実際の名前に置き換える
    def on_drop(e) -> None:  # noqa: ANN001 - 型が未知なので PoC では緩くする
        out.value = f"event={type(e).__name__}\nattrs={[a for a in dir(e) if not a.startswith('_')]}"

    # 例: page.on_drop = on_drop  /  ft.DropZone(content=..., on_drop=on_drop)
    page.add(ft.SafeArea(content=ft.Container(content=out, width=600, height=300,
                                              bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)))


if __name__ == "__main__":
    ft.run(main)
```

#### 段階 2：`flet-dropzone` が動くか

```bash
uv add --optional gui-drop flet-dropzone
uv sync --extra gui --extra gui-drop
uv run --extra gui --extra gui-drop python -c "import flet_dropzone; print(flet_dropzone.__file__)"
```

```python
"""PoC 6-b: flet-dropzone を使う。"""

from __future__ import annotations

import flet as ft
from flet_dropzone import Dropzone


def main(page: ft.Page) -> None:
    page.title = "PoC: drop (flet-dropzone)"
    out = ft.Text("ここにファイルをドロップしてください", selectable=True)

    def on_dropped(e) -> None:  # noqa: ANN001
        out.value = f"dropped: {e}"

    page.add(ft.SafeArea(content=Dropzone(
        content=ft.Container(content=out, width=600, height=300,
                             bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST),
        on_dropped=on_dropped,
    )))


if __name__ == "__main__":
    ft.run(main)
```

> `flet-dropzone` は**プラットフォームごとのビルドが必要**と書かれています。`uv sync` が通っても実行時に落ちることがあります。**15 分試して動かなければ段階 3 に進んでください**（時間をかけすぎない）。失敗した場合は `uv remove --optional gui-drop flet-dropzone` で元に戻すこと。

#### 段階 3：v1 は見送り

段階 1・2 がどちらも駄目なら、**v1 ではドロップを実装しない**と決めます。G3-T4 は「ドロップ非対応の明示と代替導線（クリックで開く／貼り付け）」に置き換わります。

**DoD**

- [ ] 段階 1 / 2 / 3 のどれになったかが**一文で言える**
- [ ] 段階 1・2 で成功した場合、**受け取ったイベントからファイルパスを取り出す方法**をメモに書いた（G3-T4 がそのまま使える粒度で）
- [ ] 段階 2 を試して失敗した場合、`pyproject.toml` と `uv.lock` が**元に戻っている**

---

### T0-8. 実測メモの作成と分岐の確定

**目的**：G1〜G3 が参照する唯一の「実測された事実」を残す。

**作成**：`31_dev-yaqpy/docs/flet-1.0-api-notes.md`

以下のテンプレートを埋める。**推測を書かない。試していない項目は「未確認」と書く。**

```markdown
# Flet 1.0 API 実測メモ（Phase G0）

| 項目 | 内容 |
|---|---|
| 測定日 | 2026-09-19 |
| flet version | （T0-1 / T0-2 の実値） |
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13 |
| 出典 | 本リポジトリ `_poc/` で実際に動かした結果（公開ドキュメントの記述ではない） |

## 1. 確定した API

| 用途 | 実際に動いた書き方 | 備考 |
|---|---|---|
| 起動 | `ft.run(main)` | |
| ウィンドウサイズ | `page.window.width = 1100` / `NG だった場合は代替` | |
| 自動更新 | ハンドラ終了後に自動／`page.update()` が必要だった場面 | T0-6 の結果 |
| ボタン | `ft.Button(content="…", icon=ft.Icons.…, on_click=…)` | |
| プルダウン | `ft.Dropdown(options=[ft.DropdownOption(key=…, text=…)], on_select=…, on_text_change=…, editable=True)` | T0-5 |
| ファイル選択 | `picker = ft.FilePicker()` → `page.services.append(picker)` → `files = await picker.pick_files(...)` | 戻り値の型と属性名を書く |
| 保存ダイアログ | `path = await picker.save_file(...)` → `str \| None` | |
| 通知 | `page.show_dialog(ft.SnackBar(ft.Text("…")))` | |
| ダイアログ | `page.show_dialog(dlg)` / `page.pop_dialog()` | |
| クリップボード | `await ft.Clipboard().set(text)` | |
| 複数行テキスト | `ft.TextField(multiline=True, read_only=True, min_lines=…, max_lines=…, text_style=ft.TextStyle(font_family="Consolas"))` | |
| イベント型 | `ft.Event[ft.Button]` など | |

## 2. 設計書と違っていた点（G1 以降はこちらが正）

| GUI 設計書の記述 | 実際 | 影響するタスク |
|---|---|---|
| （例）`Dropdown.on_change` で絞り込む | `on_text_change` が正しい | G2-T3 |
| | | |

## 3. MISSING だった API

（T0-3 の出力から転記）

## 4. ブロッキング挙動（T0-6）

- 同期ハンドラで 3 秒の CPU 処理 → UI は（固まった／固まらなかった）
- `await asyncio.to_thread(...)` → UI は（応答した／しなかった）
- ハンドラ途中の `page.update()` は（必要だった／不要だった）
- **結論**：G1-T9 の Presenter は `asyncio.to_thread` 方式を（採用する／見直す）

## 5. ファイルドロップの判定（T0-7）★ G3-T4 の分岐

- 判定：**（段階1: 本体機能あり ／ 段階2: flet-dropzone で可能 ／ 段階3: v1 は見送り）**
- 根拠：
- 採用する場合の実装メモ（イベント名・パスの取り出し方）：
- 見送る場合の代替導線：ダイアログ（`FilePicker`）＋ 貼り付け

## 6. 未確認のまま残した項目

-
```

**検証**

```bash
cd 31_dev-yaqpy
git add docs/flet-1.0-api-notes.md pyproject.toml uv.lock .gitignore
git status   # _poc/ が追跡されていないことを確認
```

**DoD**

- [ ] メモの「5. ファイルドロップの判定」が**段階 1 / 2 / 3 のいずれかで確定**している
- [ ] 「2. 設計書と違っていた点」が空欄でない（違いが無ければ「差分なし」と明記）
- [ ] `_poc/` が git の追跡対象に入っていない
- [ ] 既存テストが全件パス：`uv run python -m unittest discover -s tests/unit -t .`

**コミット**：`docs(gui): record measured Flet 1.0 API notes from PoC`

---

## 4. Phase G0 の完了条件

次の 5 つがすべて満たされたら G1 に進みます。

| # | 条件 | 確認方法 |
|---|---|---|
| D1 | `uv sync --extra gui` で Flet 1.0 が入り、ウィンドウが開く | T0-2 |
| D2 | `docs/flet-1.0-api-notes.md` が存在し、推測でなく実測で埋まっている | 目視 |
| D3 | **ドロップの可否が段階 1/2/3 で確定している** | メモ 5 節 |
| D4 | 本体の依存ゼロ（`dependencies = []`）が維持されている | `pyproject.toml` |
| D5 | 既存テストが全件パス | `uv run python -m unittest discover -s tests/unit -t .` |

---

## 5. G1 への引き継ぎ

| 引き継ぐもの | G1 での使われ方 |
|---|---|
| `docs/flet-1.0-api-notes.md` | G1-T12（メイン画面）のコードを書く前に必ず読む。設計書のコード例と食い違ったらメモが正 |
| `pyproject.toml` の `gui` extra | G1-T1 では**スクリプト行だけ**を足す（extra は G0 で済んでいる） |
| ドロップ判定 | G3-T4 の実装方針。G1・G2 では一切使わない |
| ブロッキング挙動の結論 | G1-T9 の Presenter を `asyncio.to_thread` で書く根拠 |

**G1 開始時の後片付け**

```bash
cd 31_dev-yaqpy
rm -rf _poc
# .gitignore から「_poc/」の 2 行を削除する
git checkout -b feat/gui-g1-skeleton
```

---

## 6. つまずいたときの対処

| 症状 | 対処 |
|---|---|
| `uv sync --extra gui` が失敗する | Python 3.13 であることを確認（`uv run python -V`）。Flet はビルド済み wheel が要るので、環境によっては `uv cache clean` が要る |
| ウィンドウが開かず即終了する | `ft.run(main)` が `if __name__ == "__main__":` の中にあるか確認。VS Code のターミナルではなく素の PowerShell で試す |
| `AttributeError: module 'flet' has no attribute 'X'` | T0-3 のプローブに `X` を足して有無を確認し、**メモの「3. MISSING だった API」に記録**してから代替を探す |
| ドロップ検証に 1 時間以上かかっている | **段階 3（v1 見送り）で確定させて先へ進む**。G0 はここで止まってよい場所ではない |
| `flet-dropzone` を入れたら `uv sync` が壊れた | `uv remove --optional gui-drop flet-dropzone` → `uv sync --extra gui` で復旧 |

---

## 7. 推奨モデルについて

| タスク | Haiku 4.5 | Sonnet 5 / 4.6 | 理由 |
|---|---|---|---|
| T0-1, T0-8 | **可** | 可 | コマンド実行とテンプレート埋め。判断が少ない |
| T0-2〜T0-6 | 非推奨 | **推奨** | 出力を読んで「何が違うか」を判断する必要がある |
| T0-7 | 非推奨 | **推奨** | 3 段階の打ち切り判断（時間をかけすぎない判断）が要る |

> T0-7 は「うまくいかないときに諦める判断」が品質を決めます。ここだけは自動実行せず、**人が結果を見て判定**することを勧めます。

---

**次**：[Phase G1（骨格）](./0919-04_31_yaqpy-gui-phaseG1.md)
