# yaqpy GUI 実装プラン — Phase G2（フィルタ：フリー入力＋プロパティ選択）

| 項目 | 内容 |
|---|---|
| 文書 ID | 0919-05_31_yaqpy-gui-phaseG2 |
| 版 | 第1.0版 |
| 作成日 | 2026-09-19 |
| 親文書 | [`0919-02_31_design-yaqpy-gui.md`](./0919-02_31_design-yaqpy-gui.md)（GUI 設計書）の [6-3 フィルタ機能](./0919-02_31_design-yaqpy-gui.md#6-3-フィルタ機能) |
| 前フェーズ | [`0919-04_31_yaqpy-gui-phaseG1.md`](./0919-04_31_yaqpy-gui-phaseG1.md)（**完了していること**） |
| ブランチ | `feat/gui-g2-filter` |
| 目的 | **プロパティをプルダウンから選べる**ようにし、式入力の検証を実用的にする |
| 完了条件 | GUI 設計書の受入基準 **A3・A4・A5** が通る |
| 所要 | 1.5 日（タスク 5 件） |

---

## 0. このファイルの使い方

G1 と同じです（T2-1 から順に、1 タスク 1 コミット、DoD を満たすまで次へ進まない）。

**このフェーズの掲載値は実測済みです。** `paths.py` のアルゴリズムは `examples/sample.yaml` に対して実際に動かし、出力を確認したうえでテストの期待値に採用しています。**期待値が合わない場合はアルゴリズムの実装ミス**を疑ってください（G1 の丸めテストとは事情が違います）。

---

## 1. G2 が終わったときの状態

```text
├──────────────────────────────────────────────────────────────────────┤
│ プロパティ [.server.port  = 8080   ▼] [＋ 式に追加]                   │  ← 新規
│ 式 [.server.port                                  ] [▶ 実行][■ 中止] │
│    ↑ 300 ms 止まると検証が走り、エラー位置に ^ が出る                  │  ← 改良
├──────────────────────────────────────────────────────────────────────┤
```

- プルダウンは `editable=True`。**文字を打つと候補が絞り込まれる**（`on_text_change`）。
- 候補を選ぶ（`on_select`）と式欄が**置き換わり**、すぐ再実行される。
- `[＋ 式に追加]` は現在の式に ` | <選択したパス>` を**連結**する。

---

## 2. 設計の確認（G2 で守ること）

| 決めごと | 内容 | 根拠 |
|---|---|---|
| **真実は式欄ひとつ** | プルダウンは式欄へ書き込むだけ。式欄からプルダウンへは同期しない | 設計書 [6-3-1](./0919-02_31_design-yaqpy-gui.md#6-3-1-2-系統の関係) |
| 候補は Python で作る | `paths` 演算子は現行 yaqpy に**未実装**（`path` / `del_paths` のみ）。評価器は通さない | 設計書 G3 |
| 候補の生成は 1 回だけ | ファイルを開いた直後。式を変えても作り直さない | 設計書 6-3-2 |
| 入力形式は再判定しない | `RunViewModel.input_format`（改修 C の戻り）をそのまま使う | 形式判定を二重に書かないため |
| キーの書き方 | `[A-Za-z_][A-Za-z0-9_-]*` に当てはまるキーだけ `.key`、それ以外は `.["key"]` | 下記 2-1 |

### 2-1. キーの書き方を決めた根拠（実機で確認済み）

| 式 | 結果 |
|---|---|
| `.["my key"]` | **動く**（空白を含むキー） |
| `."my key"` | **動かない**（`WrappedPathElement` の字句規則が空白を許さない） |
| `.["9num"]` / `.["1"]` | **動く**（数字始まり・整数キーにも使える） |
| `.["a\"b"]` | **動く**（`"` は `\"` で退避できる） |
| `.select` / `.not` / `.keys` / `.env` | **動く**（`.` の直後は演算子ではなくパスとして解釈される） |
| `.server.["port"]` / `.items[].["name"]` | **動く**（素の形と括弧形は混ぜられる） |

→ **括弧形はどんなキーでも安全**、素の形は見やすい。だから「安全に素の形で書けるときだけ素の形」にします。

---

## 3. タスク一覧

| # | タスク | 推奨モデル | 主な成果物 |
|---|---|---|---|
| T2-1 | `gui/paths.py` ＋ テスト | **Sonnet 必須** | 新規 2 ファイル |
| T2-2 | Presenter に候補まわりを追加 ＋ テスト | **Sonnet 必須** | `gui/presenter.py`, `tests/unit/test_gui_presenter.py` |
| T2-3 | メイン画面にプロパティ行を追加 | **Sonnet 必須** | `gui/pages/main_page.py` |
| T2-4 | 式検証を 300 ms デバウンスにする | Sonnet | `gui/pages/main_page.py` |
| T2-5 | 受入 A3・A4・A5 と手動 M5 の確認 | Sonnet | （確認のみ） |

---

## 4. 各タスクの詳細

### T2-1. `gui/paths.py` ＋ テスト

**作成**：`src/yaqpy/gui/paths.py`

```python
"""読み込んだ文書から、プルダウンに出すプロパティパスの候補を作る。

現行 yaqpy に ``paths`` 演算子が無い（``path`` と ``del_paths`` のみ）ため、
Node ツリーを Python 側で走査する。評価器は通さないので副作用はない。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from yaqpy.core.model.node import Kind, Node

MAP = "map"
SEQ = "seq"
SCALAR = "scalar"
ALIAS = "alias"

MERGE_KEY = "<<"
SAMPLE_MAX = 40

DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_ITEMS = 500

# 素のまま `.key` と書いて安全なキー（詳しくは Phase G2 プラン 2-1）
_BARE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")

_KIND_NAMES = {Kind.MAPPING: MAP, Kind.SEQUENCE: SEQ, Kind.ALIAS: ALIAS}


@dataclass(frozen=True, slots=True)
class PathCandidate:
    expression: str        # ".server.port" / ".items[]" / '.["my key"]'
    kind: str              # "map" | "seq" | "scalar" | "alias"
    sample: str = ""       # スカラーのときだけ、値の先頭
    depth: int = 1

    @property
    def label(self) -> str:
        """プルダウンに出す 1 行。"""
        if self.kind == SCALAR and self.sample:
            return f"{self.expression}  = {self.sample}"
        return f"{self.expression}  ({self.kind})"


def format_key(key: str) -> str:
    """マッピングのキー 1 つを、パス式の 1 区間に変換する。"""
    if _BARE_KEY.fullmatch(key):
        return f".{key}"
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'.["{escaped}"]'


def _kind_of(node: Node) -> str:
    return _KIND_NAMES.get(node.kind, SCALAR)


def _sample_of(node: Node) -> str:
    if node.kind is not Kind.SCALAR:
        return ""
    value = node.value.replace("\n", " ").strip()
    return value if len(value) <= SAMPLE_MAX else value[: SAMPLE_MAX - 1] + "…"


def collect_paths(documents: Sequence[Node], *, max_depth: int = DEFAULT_MAX_DEPTH,
                  max_items: int = DEFAULT_MAX_ITEMS) -> list[PathCandidate]:
    """文書を深さ優先で走査して、パス候補を文書の出現順に返す。

    - シーケンスは要素ごとに展開せず ``[]`` に畳み、構造は**先頭要素**を代表にする
    - エイリアス（``*name``）と マージキー（``<<``）は辿らない（無限ループ防止）
    - 同じ式は 1 回だけ
    """
    out: list[PathCandidate] = []
    seen: set[str] = set()

    def emit(expression: str, node: Node, depth: int) -> bool:
        """候補を 1 件足す。上限に達したら False を返して走査を止める。"""
        if expression in seen:
            return True
        if len(out) >= max_items:
            return False
        seen.add(expression)
        out.append(PathCandidate(expression, _kind_of(node), _sample_of(node), depth))
        return True

    def walk(node: Node, prefix: str, depth: int) -> None:
        if depth > max_depth or len(out) >= max_items:
            return
        if node.kind is Kind.MAPPING:
            for key, value in node.map_items():
                if key.value == MERGE_KEY:
                    continue
                expression = prefix + format_key(key.value)
                if not emit(expression, value, depth):
                    return
                if value.kind is not Kind.ALIAS:
                    walk(value, expression, depth + 1)
        elif node.kind is Kind.SEQUENCE:
            if not node.content:
                return
            expression = prefix + "[]"
            first = node.content[0]
            if not emit(expression, first, depth):
                return
            if first.kind is not Kind.ALIAS:
                walk(first, expression, depth + 1)

    for document in documents:
        walk(document, "", 1)
    return out
```

**作成**：`tests/unit/test_gui_paths.py`

> 期待値は `examples/sample.yaml` に対して実際に走らせて確認した値です。

```python
"""プロパティ候補の抽出テスト（GUI 設計書 6-3-2 / 9-2 の T1〜T4）。"""

from __future__ import annotations

import unittest

import yaqpy
from yaqpy.gui.paths import PathCandidate, collect_paths, format_key

SAMPLE = (
    "# サーバー設定\n"
    "server:\n"
    "  port: 8080 # 開発用\n"
    "  hosts: [a, b]\n"
    "  tls: &tls\n"
    "    enabled: true\n"
    "    cert: /etc/cert.pem\n"
    "backup:\n"
    "  <<: *tls\n"
    '  schedule: "0 3 * * *"\n'
    "items:\n"
    "  - name: pen\n"
    "    price: 120\n"
    "  - name: book\n"
    "    price: 980\n"
)

EXPECTED = [
    (".server", "map", "", 1),
    (".server.port", "scalar", "8080", 2),
    (".server.hosts", "seq", "", 2),
    (".server.hosts[]", "scalar", "a", 3),
    (".server.tls", "map", "", 2),
    (".server.tls.enabled", "scalar", "true", 3),
    (".server.tls.cert", "scalar", "/etc/cert.pem", 3),
    (".backup", "map", "", 1),
    (".backup.schedule", "scalar", "0 3 * * *", 2),
    (".items", "seq", "", 1),
    (".items[]", "map", "", 2),
    (".items[].name", "scalar", "pen", 3),
    (".items[].price", "scalar", "120", 3),
]


def paths(text: str, **kwargs) -> list[PathCandidate]:
    return collect_paths(yaqpy.load(text), **kwargs)


class CollectPathsTests(unittest.TestCase):
    def test_sample_document(self) -> None:
        got = [(c.expression, c.kind, c.sample, c.depth) for c in paths(SAMPLE)]
        self.assertEqual(got, EXPECTED)

    def test_every_candidate_is_a_valid_expression(self) -> None:
        """作った候補がそのまま実行できること（プルダウンの価値そのもの）。"""
        for candidate in paths(SAMPLE):
            with self.subTest(expression=candidate.expression):
                yaqpy.evaluate(candidate.expression, SAMPLE)

    def test_merge_key_is_skipped(self) -> None:
        expressions = [c.expression for c in paths(SAMPLE)]
        self.assertNotIn('.["<<"]', expressions)
        self.assertNotIn(".backup.<<", expressions)

    def test_alias_is_not_traversed(self) -> None:
        got = [c.expression for c in paths("x: &a\n  p: 1\ny: *a\n")]
        self.assertEqual(got, [".x", ".x.p", ".y"])   # .y.p は作らない

    def test_alias_candidate_kind(self) -> None:
        by_expr = {c.expression: c for c in paths("x: &a\n  p: 1\ny: *a\n")}
        self.assertEqual(by_expr[".y"].kind, "alias")

    def test_sequence_is_collapsed(self) -> None:
        expressions = [c.expression for c in paths(SAMPLE)]
        self.assertIn(".items[].name", expressions)
        self.assertNotIn(".items[0].name", expressions)
        self.assertEqual(expressions.count(".items[].name"), 1)

    def test_empty_sequence(self) -> None:
        self.assertEqual([c.expression for c in paths("a: []\n")], [".a"])

    def test_empty_document(self) -> None:
        self.assertEqual(paths(""), [])

    def test_scalar_document(self) -> None:
        self.assertEqual(paths("just a string\n"), [])

    def test_multiple_documents_are_merged(self) -> None:
        self.assertEqual([c.expression for c in paths("a: 1\n---\nb: 2\n")], [".a", ".b"])

    def test_max_depth(self) -> None:
        deep = "".join(f"{'  ' * i}k{i}:\n" for i in range(10)) + "  " * 10 + "leaf: 1\n"
        self.assertEqual([c.expression for c in paths(deep, max_depth=3)],
                         [".k0", ".k0.k1", ".k0.k1.k2"])

    def test_max_items(self) -> None:
        got = paths(SAMPLE, max_items=3)
        self.assertEqual([c.expression for c in got],
                         [".server", ".server.port", ".server.hosts"])

    def test_sample_is_truncated(self) -> None:
        long_value = "x" * 100
        candidate = paths(f"a: {long_value}\n")[0]
        self.assertEqual(len(candidate.sample), 40)
        self.assertTrue(candidate.sample.endswith("…"))

    def test_label(self) -> None:
        by_expr = {c.expression: c for c in paths(SAMPLE)}
        self.assertEqual(by_expr[".server.port"].label, ".server.port  = 8080")
        self.assertEqual(by_expr[".items"].label, ".items  (seq)")


class FormatKeyTests(unittest.TestCase):
    def test_bare_keys(self) -> None:
        self.assertEqual(format_key("server"), ".server")
        self.assertEqual(format_key("with-dash"), ".with-dash")
        self.assertEqual(format_key("_private"), "._private")
        self.assertEqual(format_key("select"), ".select")   # 演算子名でも素のままで通る

    def test_quoted_keys(self) -> None:
        self.assertEqual(format_key("my key"), '.["my key"]')
        self.assertEqual(format_key("9num"), '.["9num"]')
        self.assertEqual(format_key("a.b"), '.["a.b"]')
        self.assertEqual(format_key(""), '.[""]')

    def test_quotes_are_escaped(self) -> None:
        self.assertEqual(format_key('a"b'), '.["a\\"b"]')
        self.assertEqual(format_key("a\\b"), '.["a\\\\b"]')

    def test_quoted_keys_actually_work(self) -> None:
        document = 'my key: 1\n9num: 2\n'
        self.assertEqual(yaqpy.evaluate(format_key("my key"), document), "1\n")
        self.assertEqual(yaqpy.evaluate(format_key("9num"), document), "2\n")


if __name__ == "__main__":
    unittest.main()
```

**検証**

```bash
uv run python -m unittest tests.unit.test_gui_paths -v
```

**DoD**

- [ ] 18 件パス
- [ ] `test_every_candidate_is_a_valid_expression` がパス（**候補が実行できることが本質**。ここが落ちたら `format_key` を疑う）
- [ ] `test_gui_logic_stays_flet_free` がパス（`paths.py` は `GUI_FLET_FREE_MODULES` に入っている）

**コミット**：`feat(gui): derive property path candidates from the document tree`

---

### T2-2. Presenter に候補まわりを追加

**変更 1**：`src/yaqpy/gui/presenter.py` の import に追加

```python
from yaqpy.gui.paths import DEFAULT_MAX_DEPTH, DEFAULT_MAX_ITEMS, PathCandidate, collect_paths
```

**変更 2**：ViewModel を 1 つ追加（`RunViewModel` の後ろに置く）

```python
@dataclass(frozen=True, slots=True)
class CandidatesViewModel:
    candidates: tuple[PathCandidate, ...] = ()
    truncated: bool = False          # 上限に達して打ち切った
    note: str = ""                   # 候補を作れなかった理由（画面に出す）

    @property
    def is_empty(self) -> bool:
        return not self.candidates
```

**変更 3**：`__init__` にフィールドを 1 つ足す

```python
        self._budget: StepBudget | None = None
        self._last_run: RunViewModel | None = None
        self._candidates: list[PathCandidate] = []          # 追加
```

**変更 4**：`_accept` と `close_document` で候補を捨てる

```python
    def close_document(self) -> None:
        self.state.document = DocumentState()
        self.state.query.expression = "."
        self._last_run = None
        self._candidates = []                                # 追加

    def _accept(self, item: intake.IntakeItem) -> OpenViewModel:
        self.state.document = DocumentState(path=item.path, name=item.name,
                                            original_text=item.text, byte_size=item.byte_size)
        self.state.query.expression = "."
        self._last_run = None
        self._candidates = []                                # 追加
        return OpenViewModel(name=item.name, path=item.path, original_text=item.text,
                             byte_size=item.byte_size)
```

**変更 5**：メソッドを 4 つ足す（`cancel()` の後ろ）

```python
    # ------------------------------------------------------------------ 候補（G2）

    async def build_candidates(self) -> CandidatesViewModel:
        """いま開いている文書からパス候補を作る。open → run の後に 1 回だけ呼ぶ。

        入力形式は直前の実行結果（EvaluateResult.input_format）から採る。
        こうすると拡張子からの判定ロジックを GUI 側に複製しなくて済む。
        """
        self._candidates = []
        run = self._last_run
        if run is None or not self.state.document.is_loaded:
            return CandidatesViewModel(note=texts.MSG_NO_CANDIDATES)
        try:
            found = await asyncio.to_thread(self._collect_sync, run.input_format,
                                            self.state.document.original_text)
        except Exception:                        # noqa: BLE001 - 候補が無くても本体は使える
            return CandidatesViewModel(note=texts.MSG_NO_CANDIDATES)
        self._candidates = found
        return CandidatesViewModel(candidates=tuple(found),
                                   truncated=len(found) >= DEFAULT_MAX_ITEMS)

    def filter_candidates(self, query: str = "", *, limit: int = 200) -> list[PathCandidate]:
        """絞り込みボックスの文字で候補を部分一致フィルタする（大文字小文字は無視）。"""
        text = query.strip().lower()
        items = self._candidates
        if text:
            items = [c for c in items if text in c.expression.lower()]
        return items[:limit]

    def apply_candidate(self, expression: str, *, append: bool = False) -> str:
        """候補を式欄へ反映する。append=True ならパイプで連結する。"""
        current = self.state.query.expression.strip()
        if append and current and current != ".":
            merged = f"{current} | {expression}"
        else:
            merged = expression
        self.state.query.expression = merged
        return merged

    def _collect_sync(self, input_format: str, text: str) -> list[PathCandidate]:
        """別スレッドで動く。デコードだけして評価器は通さない。"""
        options = build_options(self.state)
        decoder = self._service.formats.decoder_for(input_format, options)
        documents = list(decoder.decode_documents(text))
        return collect_paths(documents, max_depth=DEFAULT_MAX_DEPTH,
                             max_items=DEFAULT_MAX_ITEMS)
```

**変更 6**：`src/yaqpy/gui/texts.py` に文言を追加

```python
MSG_NO_CANDIDATES = "この文書からはプロパティ候補を作れませんでした"
MSG_TOO_MANY_CANDIDATES = "候補が多いため、絞り込んでください"
```

**テスト追加**：`tests/unit/test_gui_presenter.py` の末尾（`if __name__` の前）

```python
class CandidateTests(unittest.IsolatedAsyncioTestCase):
    async def _ready(self) -> MainPresenter:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        await p.run()
        return p

    async def test_candidates_are_built_after_a_run(self) -> None:
        p = await self._ready()
        vm = await p.build_candidates()
        expressions = [c.expression for c in vm.candidates]
        self.assertIn(".server.port", expressions)
        self.assertIn(".items[].name", expressions)
        self.assertFalse(vm.truncated)

    async def test_candidates_need_a_successful_run(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        await p.run()                                # 失敗する
        vm = await p.build_candidates()
        self.assertTrue(vm.is_empty)
        self.assertTrue(vm.note)

    async def test_candidates_follow_the_detected_format(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        await p.run()
        vm = await p.build_candidates()
        self.assertEqual([c.expression for c in vm.candidates], [".a"])

    async def test_filter_is_case_insensitive(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        self.assertEqual([c.expression for c in p.filter_candidates("PORT")], [".server.port"])
        self.assertTrue(p.filter_candidates(""))     # 空なら全件

    async def test_filter_limit(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        self.assertEqual(len(p.filter_candidates("", limit=2)), 2)

    async def test_apply_replaces_the_expression(self) -> None:
        p = await self._ready()
        self.assertEqual(p.apply_candidate(".server.port"), ".server.port")
        self.assertEqual(p.state.query.expression, ".server.port")

    async def test_apply_append_joins_with_a_pipe(self) -> None:
        p = await self._ready()
        p.apply_candidate(".items[]")
        self.assertEqual(p.apply_candidate(".name", append=True), ".items[] | .name")

    async def test_append_on_the_identity_expression_replaces(self) -> None:
        p = await self._ready()                     # 開いた直後の式は "."
        self.assertEqual(p.apply_candidate(".server", append=True), ".server")

    async def test_applied_candidate_runs(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.apply_candidate(".items[] | select(.price > 500)")
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertIn("book", vm.full_text)

    async def test_candidates_are_cleared_when_the_document_closes(self) -> None:
        p = await self._ready()
        await p.build_candidates()
        p.close_document()
        self.assertEqual(p.filter_candidates(), [])
```

**検証**

```bash
uv run python -m unittest tests.unit.test_gui_presenter -v
```

**DoD**

- [ ] 追加 10 件を含め、`test_gui_presenter` が全件パス（合計 28 件）
- [ ] `test_candidates_need_a_successful_run` がパス（**壊れた文書でもフリー入力は使えるまま**、という設計の担保）

**コミット**：`feat(gui): expose path candidates from the presenter`

---

### T2-3. メイン画面にプロパティ行を追加

> ⚠ **G0 メモの「Dropdown のイベント」の節を先に読むこと。** `on_text_change` で絞り込めなかった場合の代替は本タスクの末尾に書いてあります。

**変更 1**：`src/yaqpy/gui/pages/main_page.py` の import に追加

```python
from yaqpy.gui.paths import PathCandidate
```

**変更 2**：`__init__` の「式バー」の前に、プロパティ行の部品を足す

```python
        # --- プロパティ行（G2）---
        self._property_dd = ft.Dropdown(
            label=texts.LBL_PROPERTY,
            editable=True,
            expand=True,
            options=[],
            on_select=self._on_property_select,
            on_text_change=self._on_property_filter,
            disabled=True,
        )
        self._add_button = ft.Button(content=texts.BTN_ADD_TO_EXPR, icon=ft.Icons.ADD,
                                     on_click=self._on_add_to_expression, disabled=True)
        self._candidate_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)
        self._selected_candidate = ""
```

**変更 3**：`_build()` の `expr_bar` を、プロパティ行を含む形に差し替える

置換前：

```python
        expr_bar = ft.Column([
            ft.Row([self._expr_field, self._run_button, self._cancel_button], spacing=8),
            self._expr_error,
        ], spacing=2)
```

置換後：

```python
        filter_bar = ft.Column([
            ft.Row([self._property_dd, self._add_button], spacing=8),
            self._candidate_note,
            ft.Row([self._expr_field, self._run_button, self._cancel_button], spacing=8),
            self._expr_error,
        ], spacing=2)
```

そして `_build()` の戻り値のリストで `expr_bar` を `filter_bar` に置き換える。

**変更 4**：`_load()` の末尾で候補を作る

置換前：

```python
        self._expr_error.visible = False
        await self._run()
```

置換後：

```python
        self._expr_error.visible = False
        await self._run()
        await self._reload_candidates()
```

**変更 5**：`_on_close` で候補を空にする（`self._status_text.value = ""` の前に足す）

```python
        self._property_dd.options = []
        self._property_dd.value = None
        self._property_dd.disabled = True
        self._add_button.disabled = True
        self._candidate_note.visible = False
        self._selected_candidate = ""
```

**変更 6**：ハンドラを 4 つ足す（`_on_expression_change` の後ろ）

```python
    # ------------------------------------------------------------------ プロパティ候補（G2）

    async def _reload_candidates(self) -> None:
        vm = await self._p.build_candidates()
        self._set_candidates(self._p.filter_candidates())
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

    def _on_property_filter(self, e: ft.Event[ft.Dropdown]) -> None:
        """編集可能モードで文字を打ったとき（＝絞り込み）。"""
        self._set_candidates(self._p.filter_candidates(e.control.value or ""))

    def _on_property_select(self, e: ft.Event[ft.Dropdown]) -> None:
        expression = e.control.value or ""
        if not expression:
            return
        self._selected_candidate = expression
        self._expr_field.value = self._p.apply_candidate(expression)
        self._expr_field.error_text = None
        self._expr_error.visible = False
        self._page.run_task(self._run)

    def _on_add_to_expression(self, e: ft.Event[ft.Button]) -> None:
        expression = self._selected_candidate or (self._property_dd.value or "")
        if not expression:
            return
        self._expr_field.value = self._p.apply_candidate(expression, append=True)
        self._expr_field.error_text = None
        self._expr_error.visible = False
        self._page.run_task(self._run)
```

**代替案（`on_text_change` で絞り込めなかった場合）**

`editable=True` の Dropdown が期待どおり動かないときは、**絞り込み専用の TextField を隣に置く**形に変えます。

```python
        self._property_filter = ft.TextField(label="絞り込み", width=220,
                                             prefix_icon=ft.Icons.SEARCH,
                                             on_change=self._on_property_filter)
        self._property_dd = ft.Dropdown(label=texts.LBL_PROPERTY, expand=True, options=[],
                                        on_select=self._on_property_select, disabled=True)
        # filter_bar の 1 行目: ft.Row([self._property_dd, self._property_filter, self._add_button])
```

`_on_property_filter` の中身は同じ（`e.control.value` を `filter_candidates` に渡す）です。**どちらを採ったかを G0 メモの「2. 設計書と違っていた点」に追記してください。**

**検証（手動）**

```bash
uv run --extra gui yaqpy-gui
```

- `examples/sample.yaml` を開く → プルダウンに 13 件の候補（`.server` 〜 `.items[].price`）が出る
- プルダウンに `port` と打つ → `.server.port` だけに絞られる
- `.server.port` を選ぶ → 式欄が `.server.port` になり、右ペインが `8080` になる（**受入 A3**）
- `.items[]` を選んでから `.name` を選び直さずに `[＋ 式に追加]` → `.items[] | .items[]` のような二重にならないこと（選択中の候補が使われる）

**DoD**

- [ ] 受入 **A3** が満たされる
- [ ] 壊れた YAML を開いたとき、プルダウンが無効になり注記が出て、**式欄は使えるまま**
- [ ] フルテストがパス

**コミット**：`feat(gui): add the property dropdown with incremental filtering`

---

### T2-4. 式検証を 300 ms デバウンスにする

**目的**：1 文字打つたびに構文解析が走らないようにし、入力中の赤表示のちらつきを抑える。

**変更 1**：`main_page.py` の import に `asyncio` を追加。

**変更 2**：`__init__` にトークンを 1 つ足す

```python
        self._validate_token = 0
```

**変更 3**：`_on_expression_change` を置き換える

置換前（G1 で書いたもの全体）：

```python
    def _on_expression_change(self, e: ft.Event[ft.TextField]) -> None:
        """入力中は検証だけ（再実行はしない）。G2 で 300 ms のデバウンスを入れる。"""
        expression = e.control.value or ""
        self._state.query.expression = expression
        result = self._p.validate(expression)
        ...
```

置換後：

```python
    def _on_expression_change(self, e: ft.Event[ft.TextField]) -> None:
        """入力中は検証だけ（再実行はしない）。最後の打鍵から 300 ms 後に 1 回だけ走る。"""
        self._state.query.expression = e.control.value or ""
        self._validate_token += 1
        token = self._validate_token

        async def later() -> None:
            await asyncio.sleep(0.3)
            if token != self._validate_token:
                return                       # もっと新しい入力が来たので捨てる
            self._apply_validation(self._p.validate(self._state.query.expression))
            self._page.update()

        self._page.run_task(later)

    def _apply_validation(self, result) -> None:  # noqa: ANN001 - ValidationViewModel
        expression = self._state.query.expression
        if result.valid:
            self._expr_field.error_text = None
            self._expr_error.visible = False
            return
        self._expr_field.error_text = result.message
        caret = caret_line(result.position)
        self._expr_error.value = (f"{result.message}\n{expression}\n{caret}" if caret
                                  else result.message)
        self._expr_error.visible = True
```

> `page.run_task` は**呼び出したコルーチンではなく関数**を渡します（Flet 1.0 の移行ガイド）。ここでは引数なしのローカル関数 `later` を渡すのでその条件を満たします。返り値は使いません（トークンで新旧を判定しているので `Task.cancel()` は不要）。

**変更 4**：`_on_run` の先頭で、実行前に必ず最新の検証を通す

```python
    async def _on_run(self, e: ft.Event) -> None:
        self._validate_token += 1            # 走りかけのデバウンスを無効化
        self._apply_validation(self._p.validate(self._state.query.expression))
        await self._run()
```

（`Presenter.run()` 自身も検証してから評価するので、二重の安全網になります。）

**検証（手動・M5）**

- 式欄に `.items[] | select(.price > 500)` をゆっくり打つ → 途中の不完全な式で赤くならず、**打ち終わって 0.3 秒後に判定が出る**
- 末尾 3 文字を消して Enter → 最後の式で **1 回だけ**実行される
- `.server.(` と打つ → 赤枠＋`^` が出て、Enter しても実行されない（**受入 A5**）

**DoD**

- [ ] 受入 **A5** が満たされる
- [ ] 手動テスト **M5** が満たされる
- [ ] 長い式を高速に打っても CPU が跳ねない

**コミット**：`feat(gui): debounce expression validation`

---

### T2-5. 受入確認

**受入 A3・A4・A5 を通しで確認する。**

| # | 操作 | 期待 |
|---|---|---|
| A3 | `sample.yaml` を開き、プルダウンから `.server.port` を選ぶ | 式欄が `.server.port`、右ペインが `8080` |
| A4 | 式欄に `.items[] \| select(.price > 500)` を入れて Enter | 右ペインに `name: book` / `price: 980` |
| A5 | 式欄に `.server.(` を入れる | 赤枠＋位置つきエラー。Enter しても実行されない |

**回帰確認**（G1 の受入が壊れていないこと）

| # | 操作 | 期待 |
|---|---|---|
| A1 | `sample.yaml` を開く | 左に原文、右に YAML、状態バーに件数と時間 |
| A2 | 出力形式を `json` に | 右だけ JSON |
| A8 | 壊れた YAML を開く | 右にエラー、落ちない、プルダウンは無効＋注記 |

**DoD**

- [ ] 上記 6 件すべて期待どおり
- [ ] フルテストがパス
- [ ] `uv run ruff check src/yaqpy/gui` に致命的な指摘がない

**コミット**：`test(gui): verify acceptance A3-A5 for phase G2`

---

## 5. Phase G2 の完了条件

| # | 条件 | 確認方法 |
|---|---|---|
| D1 | 受入 A3・A4・A5 が通る | 手動（T2-5） |
| D2 | 受入 A1・A2・A8 が壊れていない | 手動（T2-5） |
| D3 | 生成した候補が**すべてそのまま実行できる** | `test_every_candidate_is_a_valid_expression` |
| D4 | 壊れた文書でもフリー入力は使える | `test_candidates_need_a_successful_run` ＋ 手動 |
| D5 | 自動テストが全件パス | フルテスト |

追加されたテスト件数の目安：`test_gui_paths` +18、`test_gui_presenter` +10 = **+28 件**（G1 からの累計 +97 件。G1 の +69 と G2 の +28）。

---

## 6. G3 への引き継ぎ

| 引き継ぐもの | G3 での使われ方 |
|---|---|
| `MainPresenter.last_run` | `save()` が `full_text` を取り出す元 |
| `RunViewModel.full_text` | 保存する内容そのもの（`display_text` を保存しないこと） |
| `MainPage` の右ペイン見出し行 | ここに `[📋]` と `[💾 保存]` を足す |
| `GuiState.settings` | 設定画面がこれを直接書き換える |
| G0 メモのドロップ判定 | `G3-T4` の実装方針 |

```bash
git checkout -b feat/gui-g3-save
```

---

## 7. つまずいたときの対処

| 症状 | 対処 |
|---|---|
| `test_sample_document` の期待値と 1 件ずれる | `emit` の呼び出し位置（値ノードを渡しているか）と、シーケンスで先頭要素を代表にしているかを確認 |
| `.items[0].name` のような候補が出る | シーケンスを畳んでいない。`walk` の SEQUENCE 分岐が `node.content[0]` だけを見ているか確認 |
| 候補が無限に増える／再帰エラー | エイリアス（`Kind.ALIAS`）で降りるのを止めていない |
| `.["<<"]` が候補に出る | `MERGE_KEY` のスキップが入っていない |
| プルダウンに打った文字で絞り込めない | T2-3 の「代替案」に切り替える。G0 メモに記録する |
| 候補を選んでも式欄が変わらない | `on_change` ではなく **`on_select`** に繋いでいるか確認（Flet 1.0 の変更点） |
| デバウンスが効かず打鍵ごとに走る | `self._validate_token` をインクリメントしてから**ローカル変数に退避**しているか確認 |

---

## 8. 推奨モデルのまとめ

| タスク | Haiku 4.5 | Sonnet 5 / 4.6 | 理由 |
|---|---|---|---|
| T2-1 | 不可 | **必須** | 木の走査・打ち切り・キーの書き分けという設計判断が詰まっている |
| T2-2 | 不可 | **必須** | 既存クラスへの差し込みで、状態の無効化漏れが起きやすい |
| T2-3, T2-4 | 不可 | **必須** | Flet の実 API との擦り合わせと、代替案への切り替え判断 |
| T2-5 | 可 | 推奨 | 手順どおりの確認 |

> G2 に Haiku 向きのタスクはありません。**このフェーズは Sonnet で通してください。**

---

**前**：[Phase G1（骨格）](./0919-04_31_yaqpy-gui-phaseG1.md) ／ **次**：[Phase G3（保存・仕上げ）](./0919-06_31_yaqpy-gui-phaseG3.md)
