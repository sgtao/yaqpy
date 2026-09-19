# yaqpy GUI 実装プラン — Phase G1（骨格：開く → 表示 → 変換）

| 項目 | 内容 |
|---|---|
| 文書 ID | 0919-04_31_yaqpy-gui-phaseG1 |
| 版 | 第1.0版 |
| 作成日 | 2026-09-19 |
| 親文書 | [`0919-02_31_design-yaqpy-gui.md`](./0919-02_31_design-yaqpy-gui.md)（GUI 設計書） |
| 前フェーズ | [`0919-03_31_yaqpy-gui-phaseG0.md`](./0919-03_31_yaqpy-gui-phaseG0.md)（**完了していること**） |
| 作業リポジトリ | `31_dev-yaqpy/` |
| ブランチ | `feat/gui-g1-skeleton` |
| 目的 | **ファイルを開くと、左に原文・右に変換結果が出る**ところまで作り、`uv run yaqpy-gui` / `uv run yaqpy --gui` で起動できるようにする |
| 完了条件 | GUI 設計書の受入基準 **A1・A2・A8** が通る ＋ 両方の起動コマンドが動く |
| 所要 | 1.5 日（タスク 14 件） |

---

## 0. このファイルの使い方

1. **必ず先に `31_dev-yaqpy/docs/flet-1.0-api-notes.md`（G0 の実測メモ）を読む。** このファイルのコードと食い違ったら**メモが正**。
2. タスク T1-1 から順に実行する。各タスクは「目的 → 変更内容 → 検証 → DoD」。
3. 1 タスク = 1 コミット。
4. 掲載しているコードは**そのまま貼って動くことを狙った完成形**です。写経して構いませんが、import 漏れ・型注釈は `ruff` と目視で確認してください。
5. **既存ファイルの変更は Edit ツール（文字列の置換）で行い、改行コードを変えないこと。** このリポジトリは **LF**（`git ls-files --eol` が `i/lf w/lf`、`core.autocrlf=false`）です。Windows 上で Python の `Path.read_text()` → `write_text()` で書き換えると **CRLF に化けて全行が差分になります**（実際に起きました）。スクリプトで書き換える必要があるときは `Path.read_bytes()` / `write_bytes()` か `open(..., newline="\n")` を使い、**各タスクの後に `git diff --stat` で差分が数行〜数十行であることを確認**してください。

**共通の検証コマンド**（以後「フルテスト」と呼ぶ）

```bash
uv run python -m unittest discover -s tests/unit -t . && uv run python -m unittest tests.acceptance.test_cli
```

---

## 1. G1 が終わったときの状態

```text
┌──────────────────────────────────────────────────────────────────────┐
│ 📄 [ファイルを開く]  examples/sample.yaml  (231 B)      [✕ 閉じる]    │
├──────────────────────────────────────────────────────────────────────┤
│ 入力形式 [auto ▼]  出力形式 [json ▼]  インデント [2]  [□ 整形]        │
├──────────────────────────────────────────────────────────────────────┤
│ 式 [.server.port                                  ] [▶ 実行][■ 中止] │
├───────────────────────────────┬──────────────────────────────────────┤
│ オリジナル（読み取り専用）     │ 変換結果                             │
│ # サーバー設定                 │ 8080                                 │
│ server:                       │                                      │
│   port: 8080 # 開発用          │                                      │
├───────────────────────────────┴──────────────────────────────────────┤
│ ✅ 1 document / 3.2 ms                                yaml → json    │
└──────────────────────────────────────────────────────────────────────┘
```

**まだ無いもの**：プロパティのプルダウン（G2）、保存・設定画面・ドロップ（G3）。

**起動コマンド**（どちらも同じ画面が開く）

```bash
uv sync --extra gui          # GUI を使うときだけ flet が入る
uv run yaqpy-gui             # 専用コマンド（T1-1・T1-12）
uv run yaqpy --gui           # CLI のフラグ（T1-14）
```

> flet を入れていない環境で `uv run yaqpy --gui` を実行すると、導入方法を案内して終了コード 1 で終わります。

---

## 2. タスク一覧

| # | タスク | 推奨モデル | 主な成果物 |
|---|---|---|---|
| T1-1 | 後片付けとブランチ作成、`yaqpy-gui` スクリプト追加 | **Haiku 4.5 可** | `pyproject.toml` |
| T1-2 | 改修 B：`YqService` にバジェットを通す | **Haiku 4.5 可** | `app/service.py` |
| T1-3 | 改修 C：`EvaluateResult` に解決済み形式を持たせる | **Haiku 4.5 可** | `app/dto.py`, `app/service.py` |
| T1-4 | 改修 B・C のテスト | Sonnet | `tests/unit/test_api.py` |
| T1-5 | 改修 D：アーキテクチャ検査の作り替え | Sonnet | `tests/unit/test_architecture.py` |
| T1-6 | `gui/__init__.py` と `gui/texts.py` | **Haiku 4.5 可** | 新規 2 ファイル |
| T1-7 | `gui/state.py` ＋ テスト | Sonnet | 新規 2 ファイル |
| T1-8 | `gui/errors_ja.py` ＋ テスト | Sonnet | 新規 2 ファイル |
| T1-9 | `gui/intake.py` ＋ テスト | Sonnet | 新規 2 ファイル |
| T1-10 | `gui/presenter.py` ＋ テスト（**山場**） | **Sonnet 必須** | 新規 2 ファイル |
| T1-11 | `gui/_di.py` | **Haiku 4.5 可** | 新規 1 ファイル |
| T1-12 | `gui/app.py` / `gui/_run.py` ＋ 起動ガードのテスト | Sonnet | 新規 3 ファイル |
| T1-13 | `gui/pages/main_page.py`（2 ペイン） | **Sonnet 必須** | 新規 2 ファイル |
| T1-14 | `yaqpy --gui`（CLI からの起動）＋ 依存方向の例外 ＋ テスト | **Haiku 4.5 可**（Edit ツール使用が条件） | `cli/parser.py`, `cli/main.py`, `test_architecture.py`, 新規テスト 1 ＋ acceptance |

---

## 3. 各タスクの詳細

### T1-1. 後片付けとブランチ作成、スクリプト追加

```bash
cd 31_dev-yaqpy
rm -rf _poc
git checkout -b feat/gui-g1-skeleton
```

`.gitignore` から G0 で足した 2 行（`# PoC（Phase G0 限り…）` と `_poc/`）を削除する。

`pyproject.toml` の `[project.scripts]` に 1 行足す（**extra は G0 で追加済みなので触らない**）：

```toml
[project.scripts]
yaqpy = "yaqpy.cli.main:main"
yaqpy-gui = "yaqpy.gui.app:main_entry"
```

**DoD**

- [ ] `_poc/` が消えている
- [ ] `dependencies = []` が変わっていない
- [ ] `[project.optional-dependencies] gui` が残っている
- [ ] フルテストがパス

**コミット**：`build(gui): register the yaqpy-gui console script`

---

### T1-2. 改修 B：`YqService` にバジェットを通す

**目的**：GUI が評価を中止できるようにする（G-NFR-02）。`StepBudget.cancel()` は実装済みなので、**外から渡す経路だけ**を作る。

**変更 1**：`src/yaqpy/app/service.py` の `make_env`

置換前：

```python
    def make_env(self, options: Options) -> EvalEnv:
        environ = self.env.environ() if options.security.allow_env else {}
        snippet_decoder = YamlDecoder(options)
        return EvalEnv(
            operators=self.operators,
            security=options.security,
            environ=environ,
            limits=options.limits,
            budget=StepBudget(options.limits.max_steps, options.limits.timeout_seconds),
            options=options,
            formats=self.formats,
            yaml_snippet_decoder=snippet_decoder.decode_snippet,
        )
```

置換後：

```python
    def new_budget(self, options: Options) -> StepBudget:
        """Create a budget the caller can keep a reference to.

        The GUI needs this so that it can call ``budget.cancel()`` while an
        evaluation is running on a worker thread.
        """
        return StepBudget(options.limits.max_steps, options.limits.timeout_seconds)

    def make_env(self, options: Options, budget: StepBudget | None = None) -> EvalEnv:
        environ = self.env.environ() if options.security.allow_env else {}
        snippet_decoder = YamlDecoder(options)
        return EvalEnv(
            operators=self.operators,
            security=options.security,
            environ=environ,
            limits=options.limits,
            budget=budget or self.new_budget(options),
            options=options,
            formats=self.formats,
            yaml_snippet_decoder=snippet_decoder.decode_snippet,
        )
```

**変更 2**：`evaluate` のシグネチャ

置換前：

```python
    def evaluate(self, request: EvaluateRequest, sink: Any) -> EvaluateResult:
```

置換後：

```python
    def evaluate(self, request: EvaluateRequest, sink: Any, *,
                 budget: StepBudget | None = None) -> EvaluateResult:
```

**変更 3**：`evaluate` の中で env を作っている行

> ⚠ **落とし穴**：`env = self.make_env(options)` は**このファイルに 2 か所**あります（`evaluate` と `evaluate_nodes`）。直すのは `evaluate` の方だけです。次の 3 行をまとめて置換して取り違えを防いでください。

置換前：

```python
        env = self.make_env(options)
        nav = Navigator(env)
        document_count = 0
```

置換後：

```python
        env = self.make_env(options, budget)
        nav = Navigator(env)
        document_count = 0
```

**検証**

```bash
uv run python -m unittest tests.unit.test_api
grep -n "make_env" src/yaqpy/app/service.py   # 定義1 + evaluate1 + evaluate_nodes1 の 3 か所
```

**DoD**

- [ ] `evaluate_nodes` 側の `make_env(options)` は**変わっていない**
- [ ] フルテストがパス（既存の呼び出しはすべてキーワード省略で動く）

**コミット**：`feat(app): let callers supply a StepBudget so evaluation can be cancelled`

---

### T1-3. 改修 C：`EvaluateResult` に解決済み形式を持たせる

**目的**：GUI が「拡張子から何形式と判定されたか」を知る唯一の経路を作る（形式判定ロジックを GUI 側に複製しない）。

**変更 1**：`src/yaqpy/app/dto.py`

置換前：

```python
@dataclass(frozen=True, slots=True)
class EvaluateResult:
    output: str | None
    printed_anything: bool
    document_count: int
    warnings: tuple[str, ...]
    elapsed_seconds: float
```

置換後：

```python
@dataclass(frozen=True, slots=True)
class EvaluateResult:
    output: str | None
    printed_anything: bool
    document_count: int
    warnings: tuple[str, ...]
    elapsed_seconds: float
    input_format: str = ""      # actually used (after "auto" was resolved)
    output_format: str = ""     # actually used
```

**変更 2**：`src/yaqpy/app/service.py` の `evaluate` の戻り値

置換前：

```python
        return EvaluateResult(
            output=output,
            printed_anything=printer.printed_anything,
            document_count=document_count,
            warnings=(),
            elapsed_seconds=time.monotonic() - started,
        )
```

置換後：

```python
        return EvaluateResult(
            output=output,
            printed_anything=printer.printed_anything,
            document_count=document_count,
            warnings=(),
            elapsed_seconds=time.monotonic() - started,
            input_format=input_format,
            output_format=output_format,
        )
```

> `input_format` / `output_format` は同じメソッドの上の方で `self._resolve_formats(request)` から受け取っているローカル変数です。新しく作る必要はありません。

**DoD**

- [ ] フルテストがパス（既定値つき追加なので既存コードは無改修）

**コミット**：`feat(app): report the resolved input/output formats in EvaluateResult`

---

### T1-4. 改修 B・C のテスト

`src/yaqpy/tests/unit/test_api.py` ではなく **`tests/unit/test_api.py`** の末尾（`if __name__ == "__main__":` の直前）に次のクラスを足す。

```python
class ServiceBudgetTests(unittest.TestCase):
    """改修 B / C: 外から渡した StepBudget と、解決済み形式の報告。"""

    def _service(self) -> YqService:
        return YqService(InMemoryFileSystem(), StaticEnvironment())

    def _request(self, text: str = "a: 1\n", name: str = "<text>") -> EvaluateRequest:
        return EvaluateRequest(
            expression=".",
            inputs=(InputSource(name, text),),
            options=Options(input_format="auto", output_format="auto"),
            input_format="auto",
            output_format="auto",
        )

    def test_external_budget_can_cancel(self) -> None:
        service = self._service()
        options = Options()
        budget = service.new_budget(options)
        budget.cancel()                      # 走り出す前に中止しておく（決定的に再現できる）
        with self.assertRaises(EvaluationLimitError) as ctx:
            service.evaluate(self._request(), MemorySink(), budget=budget)
        self.assertEqual(ctx.exception.limit, "cancelled")

    def test_budget_is_optional(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(), MemorySink())
        self.assertEqual(result.output, "a: 1\n")

    def test_result_reports_resolved_formats(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(name="config.json", text='{"a":1}'),
                                  MemorySink())
        self.assertEqual(result.input_format, "json")
        self.assertEqual(result.output_format, "json")

    def test_auto_falls_back_to_yaml_for_unknown_extension(self) -> None:
        service = self._service()
        result = service.evaluate(self._request(name="config.conf"), MemorySink())
        self.assertEqual(result.input_format, "yaml")
```

**検証**

```bash
uv run python -m unittest tests.unit.test_api
```

**DoD**

- [ ] 4 件すべてパス
- [ ] `EvaluationLimitError` が `test_api.py` の import に入っている（既に入っている）

**コミット**：`test(app): cover external budgets and resolved-format reporting`

---

### T1-5. 改修 D：アーキテクチャ検査の作り替え

**目的**：`gui/` に `flet` が入っても検査が落ちないようにし、**代わりにもっと強い主張**を検査する。

**変更 1**：`tests/unit/test_architecture.py` の `FORBIDDEN` に `"yaqpy.gui"` を足す（現状 `core.*` と `formats` の行に無い）。

置換前：

```python
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "yaqpy.core.model": ("yaqpy.core.lang", "yaqpy.core.engine", "yaqpy.core.operators",
                        "yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.lang": ("yaqpy.core.engine", "yaqpy.core.operators", "yaqpy.formats", "yaqpy.app",
                       "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.engine": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.operators": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.formats": ("yaqpy.core.engine", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.app": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web", "yaqpy.api"),
    "yaqpy.api": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web"),
    "yaqpy.cli": ("yaqpy.gui", "yaqpy.web"),
}
```

置換後：

```python
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "yaqpy.core.model": ("yaqpy.core.lang", "yaqpy.core.engine", "yaqpy.core.operators",
                        "yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.core.lang": ("yaqpy.core.engine", "yaqpy.core.operators", "yaqpy.formats", "yaqpy.app",
                       "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.core.engine": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.core.operators": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.formats": ("yaqpy.core.engine", "yaqpy.app", "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.app": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web", "yaqpy.api"),
    "yaqpy.api": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web"),
    "yaqpy.cli": ("yaqpy.gui", "yaqpy.web"),
}

GUI_PREFIX = "yaqpy.gui"
# gui が使ってよい外部パッケージ（G0 でドロップ拡張を採用した場合のみ 2 つ目が有効になる）
GUI_ALLOWED_THIRD_PARTY = {"flet", "flet_dropzone"}
# View から切り離してテストするため、flet を import してはいけないモジュール
GUI_FLET_FREE_MODULES = {
    "yaqpy.gui.presenter",
    "yaqpy.gui.state",
    "yaqpy.gui.paths",
    "yaqpy.gui.intake",
    "yaqpy.gui.errors_ja",
    "yaqpy.gui.texts",
    "yaqpy.gui._di",
}
```

**変更 2**：`test_only_standard_library` を「`gui/` 以外は依存ゼロ」に変え、GUI 用の検査を 2 つ足す。

置換前：

```python
    def test_only_standard_library(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            for imported in imports_of(path):
                top = imported.split(".")[0]
                with self.subTest(file=path.name, imported=imported):
                    self.assertTrue(top == "yaqpy" or top in stdlib,
                                    f"{path.name} imports non-stdlib module {imported}")
```

置換後：

```python
    def test_only_standard_library(self) -> None:
        """gui/ 以外は実行時依存ゼロ（README の約束）。"""
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            if module_name(path).startswith(GUI_PREFIX):
                continue                      # gui は flet を使ってよい（下の 2 つで別途検査）
            for imported in imports_of(path):
                top = imported.split(".")[0]
                with self.subTest(file=path.name, imported=imported):
                    self.assertTrue(top == "yaqpy" or top in stdlib,
                                    f"{path.name} imports non-stdlib module {imported}")

    def test_gui_third_party_whitelist(self) -> None:
        """gui/ が使ってよい外部パッケージは flet 系だけ。"""
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            module = module_name(path)
            if not module.startswith(GUI_PREFIX):
                continue
            for imported in imports_of(path):
                top = imported.split(".")[0]
                with self.subTest(module=module, imported=imported):
                    self.assertTrue(
                        top == "yaqpy" or top in stdlib or top in GUI_ALLOWED_THIRD_PARTY,
                        f"{module} imports unexpected third-party module {imported}")

    def test_gui_logic_stays_flet_free(self) -> None:
        """Presenter 層は flet 抜きで単体テストできること（設計書 G-NFR-05）。"""
        for path in self.files:
            module = module_name(path)
            if module not in GUI_FLET_FREE_MODULES:
                continue
            for imported in imports_of(path):
                with self.subTest(module=module, imported=imported):
                    self.assertNotEqual(imported.split(".")[0], "flet",
                                        f"{module} must not import flet")
```

**検証**

```bash
uv run python -m unittest tests.unit.test_architecture
```

**DoD**

- [ ] この時点（`gui/` がまだ空）でも 5 件すべてパスする
- [ ] `test_gui_logic_stays_flet_free` は対象モジュールが未作成でも落ちない（ループが回らないだけ）

**コミット**：`test(arch): scope the zero-dependency rule to everything but gui/`

---

### T1-6. `gui/__init__.py` と `gui/texts.py`

**作成**：`src/yaqpy/gui/__init__.py`

```python
"""Desktop GUI (Flet). Optional: install with ``pip install "yaqpy[gui]"``."""

from __future__ import annotations

__all__ = ["main_entry"]


def main_entry() -> int:
    """Re-export so that ``python -m yaqpy.gui`` style use also works."""
    from yaqpy.gui.app import main_entry as _main_entry

    return _main_entry()
```

**作成**：`src/yaqpy/gui/texts.py`

```python
"""UI 文言（日本語）。将来の多言語化に備えてここに集める。"""

from __future__ import annotations

APP_TITLE = "yaqpy"

# ボタン・ラベル
BTN_OPEN = "ファイルを開く"
BTN_CLOSE = "閉じる"
BTN_RUN = "実行"
BTN_CANCEL = "中止"
BTN_SAVE = "保存"
BTN_COPY = "コピー"
BTN_ADD_TO_EXPR = "式に追加"
LBL_INPUT_FORMAT = "入力形式"
LBL_OUTPUT_FORMAT = "出力形式"
LBL_INDENT = "インデント"
LBL_PRETTY = "整形 (-P)"
LBL_EXPRESSION = "式"
LBL_PROPERTY = "プロパティ"
LBL_ORIGINAL = "オリジナル"
LBL_CONVERTED = "変換結果"

# プレースホルダ・案内
PH_EXPRESSION = "例: .items[] | select(.price > 500)"
MSG_NO_DOCUMENT = "ファイルを開くか、テキストを貼り付けてください"
MSG_RUNNING = "実行中…"
MSG_TRUNCATED = "（以下 {n} 行を表示していません。保存すれば全量が得られます）"
MSG_SAVED = "保存しました: {path}"

# エラー
ERR_BUSY = "実行中です。終わるまでお待ちください"
ERR_NO_DOCUMENT = "先にファイルを開いてください"
ERR_TOO_LARGE = "ファイルが大きすぎます（{size} / 上限 {limit}）"
ERR_NOT_A_FILE = "ファイルを指定してください（フォルダは開けません）"
ERR_NOT_UTF8 = "UTF-8 のテキストとして読めませんでした"
ERR_UNEXPECTED = "想定外のエラーが発生しました"

# エラーの対処ヒント
HINT_EXPRESSION = "式の書き方は USAGE.ja.md を参照してください"
HINT_INPUT_FORMAT = "入力形式の選択が違うかもしれません"
HINT_SECURITY = "設定画面で「{capability} を許可」を有効にすると実行できます"
HINT_TIMEOUT = "設定画面でタイムアウトを延ばせます"
HINT_CANCELLED = "中止しました"
HINT_REPORT = "再現手順を添えて不具合として報告してください"

INSTALL_HINT = (
    "GUI を使うには flet が必要です。次のどちらかで導入してください:\n"
    '  pip install "yaqpy[gui]"\n'
    "  uv sync --extra gui\n"
)
```

**DoD**：`uv run python -c "import yaqpy.gui.texts"` が通る。

**コミット**：`feat(gui): add the gui package skeleton and UI texts`

---

### T1-7. `gui/state.py` ＋ テスト

**作成**：`src/yaqpy/gui/state.py`

```python
"""GUI の状態と、そこから Options を組み立てる関数（Flet 非依存）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from yaqpy.options import JsonOptions, Limits, Options, SecurityPolicy, ToonOptions, YamlOptions

AUTO = "auto"


@dataclass(slots=True)
class DocumentState:
    """いま開いている文書。path が None なら貼り付け由来。"""

    path: str | None = None
    name: str = ""                # 形式の自動判定に使う表示名（ファイル名）
    original_text: str = ""
    byte_size: int = 0

    @property
    def is_loaded(self) -> bool:
        return bool(self.original_text)

    @property
    def source_name(self) -> str:
        """EvaluateRequest に渡す入力名。拡張子から形式が判定される。"""
        return self.path or self.name or "<text>"


@dataclass(slots=True)
class QueryState:
    """式と出力の設定。"""

    expression: str = "."
    input_format: str = AUTO
    output_format: str = AUTO
    indent: int = 2
    pretty_print: bool = False


@dataclass(slots=True)
class SettingsState:
    """設定画面の値。v1 では永続化しない（セッション内のみ）。"""

    allow_env: bool = False
    allow_file: bool = False
    timeout_seconds: float = 10.0
    max_input_mib: int = 50
    max_display_lines: int = 5000
    dark_theme: bool = False

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mib * 1024 * 1024


@dataclass(slots=True)
class GuiState:
    """画面をまたいで共有する唯一の状態。"""

    document: DocumentState = field(default_factory=DocumentState)
    query: QueryState = field(default_factory=QueryState)
    settings: SettingsState = field(default_factory=SettingsState)
    running: bool = False


def build_options(state: GuiState) -> Options:
    """GuiState から、その 1 回の評価に使う不変の Options を作る。

    Options は frozen なので使い回さず、実行のたびに作り直す。
    """
    q, s = state.query, state.settings
    indent = max(q.indent, 0)
    return Options(
        input_format=q.input_format or AUTO,
        output_format=q.output_format or AUTO,
        indent=indent,
        pretty_print=q.pretty_print,
        yaml=YamlOptions(indent=indent),
        json=JsonOptions(indent=indent),
        toon=ToonOptions(indent=indent if indent >= 1 else 2),
        security=SecurityPolicy(
            allow_env=s.allow_env,
            allow_file=s.allow_file,
            allow_system=False,      # GUI からは決して許可しない（設計書 10 章）
        ),
        limits=Limits(
            max_input_bytes=s.max_input_bytes,
            timeout_seconds=s.timeout_seconds,
        ),
    )


def truncate_for_display(text: str, max_lines: int) -> tuple[str, int]:
    """表示用に先頭 max_lines 行へ丸める。戻り値は (表示文字列, 省略した行数)。

    保存には**必ず元の text** を使うこと（設計書のリスク R8）。
    """
    if max_lines <= 0:
        return text, 0
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, 0
    return "".join(lines[:max_lines]), len(lines) - max_lines
```

**作成**：`tests/unit/test_gui_state.py`

```python
"""GuiState と Options 変換のテスト（GUI 設計書 5-4）。"""

from __future__ import annotations

import unittest

from yaqpy.gui.state import GuiState, build_options, truncate_for_display


class BuildOptionsTests(unittest.TestCase):
    def test_defaults_are_safe(self) -> None:
        options = build_options(GuiState())
        self.assertFalse(options.security.allow_env)
        self.assertFalse(options.security.allow_file)
        self.assertFalse(options.security.allow_system)
        self.assertEqual(options.limits.timeout_seconds, 10.0)
        self.assertEqual(options.input_format, "auto")

    def test_security_switches_are_applied(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        state.settings.allow_file = True
        options = build_options(state)
        self.assertTrue(options.security.allow_env)
        self.assertTrue(options.security.allow_file)

    def test_system_operator_is_never_allowed(self) -> None:
        state = GuiState()
        state.settings.allow_env = True
        self.assertFalse(build_options(state).security.allow_system)

    def test_indent_reaches_every_encoder(self) -> None:
        state = GuiState()
        state.query.indent = 4
        options = build_options(state)
        self.assertEqual(options.indent, 4)          # json が見る
        self.assertEqual(options.yaml.indent, 4)
        self.assertEqual(options.toon.indent, 4)

    def test_indent_zero_keeps_toon_valid(self) -> None:
        state = GuiState()
        state.query.indent = 0
        options = build_options(state)
        self.assertEqual(options.indent, 0)
        self.assertEqual(options.toon.indent, 2)     # toon は 1 未満を許さない

    def test_max_input_bytes(self) -> None:
        state = GuiState()
        state.settings.max_input_mib = 2
        self.assertEqual(build_options(state).limits.max_input_bytes, 2 * 1024 * 1024)


class TruncateTests(unittest.TestCase):
    def test_short_text_is_untouched(self) -> None:
        text = "a\nb\n"
        self.assertEqual(truncate_for_display(text, 10), (text, 0))

    def test_long_text_is_cut(self) -> None:
        text = "".join(f"line{i}\n" for i in range(100))
        shown, omitted = truncate_for_display(text, 10)
        self.assertEqual(omitted, 90)
        self.assertEqual(shown.count("\n"), 10)
        self.assertTrue(shown.startswith("line0\n"))

    def test_zero_means_no_limit(self) -> None:
        text = "a\nb\nc\n"
        self.assertEqual(truncate_for_display(text, 0), (text, 0))


if __name__ == "__main__":
    unittest.main()
```

**DoD**：`uv run python -m unittest tests.unit.test_gui_state` が 9 件パス。

**コミット**：`feat(gui): add GuiState and Options builder`

---

### T1-8. `gui/errors_ja.py` ＋ テスト

**作成**：`src/yaqpy/gui/errors_ja.py`

```python
"""yaqpy の例外を、画面に出せる日本語の ViewModel に畳む（Flet 非依存）。"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from yaqpy.errors import (
    EvaluationError,
    EvaluationLimitError,
    ExpressionSyntaxError,
    FormatError,
    SecurityError,
    UnknownFormatError,
    YamlSyntaxError,
    YqError,
)
from yaqpy.gui import texts

# capability 名 → 設定画面での呼び名
_CAPABILITY_JA = {"env": "環境変数（env / strenv）", "file": "ファイル読み込み（load / loadstr）"}


@dataclass(frozen=True, slots=True)
class ErrorViewModel:
    code: str
    message: str
    hint: str = ""
    position: int = -1        # ExpressionSyntaxError のときだけ 0 以上
    capability: str = ""      # SecurityError のときだけ "env" / "file"
    limit: str = ""           # EvaluationLimitError のときだけ
    detail: str = ""          # 想定外の例外のトレース

    @property
    def is_security(self) -> bool:
        return self.code == "security"


def caret_line(position: int) -> str:
    """式の何文字目かを指す下線。position が負なら空文字。"""
    return "" if position < 0 else " " * position + "^"


def to_view_model(exc: BaseException) -> ErrorViewModel:
    """例外 1 個を ErrorViewModel にする。判定は具体的なものから順に見る。"""
    if isinstance(exc, ExpressionSyntaxError):
        where = f"式の {exc.position + 1} 文字目でエラー" if exc.position >= 0 else "式のエラー"
        return ErrorViewModel("expression_syntax", f"{where}：{exc.message}",
                              hint=texts.HINT_EXPRESSION, position=exc.position)

    if isinstance(exc, YamlSyntaxError):
        where = f"{exc.line} 行 {exc.column} 列" if exc.line else "入力"
        return ErrorViewModel("yaml_syntax", f"YAML の {where} でエラー：{exc.message}",
                              hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, UnknownFormatError):
        return ErrorViewModel("unknown_format", exc.message, hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, SecurityError):
        name = _CAPABILITY_JA.get(exc.capability, exc.capability or "この機能")
        return ErrorViewModel("security", f"この式は {name} を使いますが、許可されていません",
                              hint=texts.HINT_SECURITY.format(capability=name),
                              capability=exc.capability)

    if isinstance(exc, EvaluationLimitError):
        if exc.limit == "cancelled":
            return ErrorViewModel("evaluation_limit", texts.HINT_CANCELLED, limit=exc.limit)
        if exc.limit == "timeout_seconds":
            return ErrorViewModel("evaluation_limit", "時間切れで中断しました",
                                  hint=texts.HINT_TIMEOUT, limit=exc.limit)
        return ErrorViewModel("evaluation_limit", f"上限に達しました：{exc.message}",
                              limit=exc.limit)

    if isinstance(exc, EvaluationError):
        suffix = f"（演算子 {exc.operator}）" if exc.operator else ""
        return ErrorViewModel("evaluation", f"評価エラー：{exc.message}{suffix}")

    if isinstance(exc, FormatError):
        return ErrorViewModel("format", f"読み書きに失敗しました：{exc.message}",
                              hint=texts.HINT_INPUT_FORMAT)

    if isinstance(exc, YqError):
        return ErrorViewModel(exc.code, exc.message)

    if isinstance(exc, OSError):
        return ErrorViewModel("io", f"ファイルを扱えませんでした：{exc.strerror or exc}")

    return ErrorViewModel("unexpected", texts.ERR_UNEXPECTED, hint=texts.HINT_REPORT,
                          detail="".join(traceback.format_exception(exc)).strip())
```

**作成**：`tests/unit/test_gui_errors_ja.py`

```python
"""例外 → 日本語 ViewModel の変換テスト（GUI 設計書 5-8）。"""

from __future__ import annotations

import unittest

from yaqpy.errors import (
    EvaluationError,
    EvaluationLimitError,
    ExpressionSyntaxError,
    FormatError,
    SecurityError,
    UnknownFormatError,
    YamlSyntaxError,
)
from yaqpy.gui.errors_ja import caret_line, to_view_model


class ErrorMappingTests(unittest.TestCase):
    def test_expression_syntax_keeps_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("閉じ括弧がありません", position=6))
        self.assertEqual(vm.code, "expression_syntax")
        self.assertIn("7 文字目", vm.message)
        self.assertEqual(vm.position, 6)

    def test_expression_syntax_without_position(self) -> None:
        vm = to_view_model(ExpressionSyntaxError("だめ"))
        self.assertIn("式のエラー", vm.message)
        self.assertEqual(vm.position, -1)

    def test_yaml_syntax_shows_line_and_column(self) -> None:
        vm = to_view_model(YamlSyntaxError("bad indent", line=12, column=3))
        self.assertEqual(vm.code, "yaml_syntax")
        self.assertIn("12 行 3 列", vm.message)

    def test_unknown_format(self) -> None:
        vm = to_view_model(UnknownFormatError("unknown format 'xml'", format="xml"))
        self.assertEqual(vm.code, "unknown_format")

    def test_security_points_at_the_setting(self) -> None:
        vm = to_view_model(SecurityError("env operations have been disabled", capability="env"))
        self.assertEqual(vm.code, "security")
        self.assertTrue(vm.is_security)
        self.assertEqual(vm.capability, "env")
        self.assertIn("環境変数", vm.message)

    def test_cancelled(self) -> None:
        vm = to_view_model(EvaluationLimitError("evaluation was cancelled", limit="cancelled"))
        self.assertEqual(vm.limit, "cancelled")
        self.assertIn("中止", vm.message)

    def test_timeout(self) -> None:
        vm = to_view_model(EvaluationLimitError("too slow", limit="timeout_seconds"))
        self.assertIn("時間切れ", vm.message)
        self.assertTrue(vm.hint)

    def test_evaluation_error_mentions_operator(self) -> None:
        vm = to_view_model(EvaluationError("cannot compare", operator="COMPARE"))
        self.assertIn("COMPARE", vm.message)

    def test_plain_format_error(self) -> None:
        vm = to_view_model(FormatError("broken"))
        self.assertEqual(vm.code, "format")

    def test_unexpected_exception_keeps_traceback(self) -> None:
        vm = to_view_model(ValueError("boom"))
        self.assertEqual(vm.code, "unexpected")
        self.assertIn("ValueError", vm.detail)

    def test_caret_line(self) -> None:
        self.assertEqual(caret_line(3), "   ^")
        self.assertEqual(caret_line(-1), "")


if __name__ == "__main__":
    unittest.main()
```

**DoD**：11 件パス。

**コミット**：`feat(gui): map yaqpy errors to Japanese view models`

---

### T1-9. `gui/intake.py` ＋ テスト

**作成**：`src/yaqpy/gui/intake.py`

```python
"""ファイルテキストの取り込み口（ダイアログ・ドロップ・貼り付けを 1 つにまとめる）。

読み込み自体は FileSystemPort を通す。サイズの事前確認だけは、
巨大ファイルを読んでしまわないために ``size_of`` コールバックを使う。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from yaqpy.app.ports import FileSystemPort
from yaqpy.gui import texts

DIALOG = "dialog"
DROP = "drop"
PASTE = "paste"


class IntakeError(Exception):
    """取り込めなかった理由（すでに日本語）。"""


@dataclass(frozen=True, slots=True)
class IntakeItem:
    name: str          # 形式の自動判定に使う表示名。貼り付けなら ""
    text: str
    origin: str
    byte_size: int
    path: str | None = None


def _human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MiB"
    if size >= 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size} B"


def from_path(fs: FileSystemPort, path: str, *, max_bytes: int,
              size_of: Callable[[str], int] | None = None,
              origin: str = DIALOG) -> IntakeItem:
    """ファイルを 1 つ取り込む。大きすぎる場合は読まずに失敗する。"""
    if not fs.exists_file(path):
        raise IntakeError(texts.ERR_NOT_A_FILE)
    probe = size_of or os.path.getsize
    try:
        size = probe(path)
    except OSError:
        size = 0                       # 測れないときは読んでから測る
    if size > max_bytes:
        raise IntakeError(texts.ERR_TOO_LARGE.format(size=_human(size), limit=_human(max_bytes)))
    try:
        text = fs.read_text(path)
    except UnicodeDecodeError as e:
        raise IntakeError(texts.ERR_NOT_UTF8) from e
    actual = len(text.encode("utf-8"))
    if actual > max_bytes:
        raise IntakeError(texts.ERR_TOO_LARGE.format(size=_human(actual),
                                                     limit=_human(max_bytes)))
    return IntakeItem(name=os.path.basename(path), text=text, origin=origin,
                      byte_size=actual, path=path)


def from_text(text: str, *, name: str = "", origin: str = PASTE) -> IntakeItem:
    """貼り付けられたテキストを取り込む。"""
    return IntakeItem(name=name, text=text, origin=origin,
                      byte_size=len(text.encode("utf-8")), path=None)
```

**作成**：`tests/unit/test_gui_intake.py`

```python
"""取り込み口のテスト（GUI 設計書 6-1-3）。"""

from __future__ import annotations

import unittest

from yaqpy.app.ports import InMemoryFileSystem
from yaqpy.gui.intake import IntakeError, from_path, from_text

SAMPLE = "server:\n  port: 8080\n"
MB = 1024 * 1024


def _fs() -> InMemoryFileSystem:
    return InMemoryFileSystem({"/w/sample.yaml": SAMPLE, "/w/big.json": "x" * 4096})


def _size_of(fs: InMemoryFileSystem):
    return lambda path: len(fs.files[path].encode("utf-8"))


class FromPathTests(unittest.TestCase):
    def test_reads_a_file(self) -> None:
        fs = _fs()
        item = from_path(fs, "/w/sample.yaml", max_bytes=50 * MB, size_of=_size_of(fs))
        self.assertEqual(item.text, SAMPLE)
        self.assertEqual(item.name, "sample.yaml")
        self.assertEqual(item.path, "/w/sample.yaml")
        self.assertEqual(item.byte_size, len(SAMPLE.encode()))
        self.assertEqual(item.origin, "dialog")

    def test_missing_file_is_rejected(self) -> None:
        fs = _fs()
        with self.assertRaises(IntakeError):
            from_path(fs, "/w/nope.yaml", max_bytes=50 * MB, size_of=_size_of(fs))

    def test_directory_is_rejected(self) -> None:
        fs = _fs()                       # InMemoryFileSystem は登録外を「ファイルでない」とみなす
        with self.assertRaises(IntakeError) as ctx:
            from_path(fs, "/w", max_bytes=50 * MB, size_of=_size_of(fs))
        self.assertIn("フォルダ", str(ctx.exception))

    def test_too_large_is_rejected_before_reading(self) -> None:
        fs = _fs()
        calls: list[str] = []
        original = fs.read_text

        def spy(path: str) -> str:
            calls.append(path)
            return original(path)

        fs.read_text = spy          # type: ignore[method-assign]
        with self.assertRaises(IntakeError) as ctx:
            from_path(fs, "/w/big.json", max_bytes=1024, size_of=_size_of(fs))
        self.assertIn("大きすぎます", str(ctx.exception))
        self.assertEqual(calls, [], "上限超過のファイルは読んではいけない")

    def test_size_probe_failure_falls_back_to_reading(self) -> None:
        fs = _fs()

        def broken(path: str) -> int:
            raise OSError("cannot stat")

        item = from_path(fs, "/w/sample.yaml", max_bytes=50 * MB, size_of=broken)
        self.assertEqual(item.text, SAMPLE)


class FromTextTests(unittest.TestCase):
    def test_paste(self) -> None:
        item = from_text(SAMPLE)
        self.assertEqual(item.origin, "paste")
        self.assertEqual(item.name, "")
        self.assertIsNone(item.path)
        self.assertEqual(item.byte_size, len(SAMPLE.encode()))


if __name__ == "__main__":
    unittest.main()
```

**DoD**：6 件パス。

**コミット**：`feat(gui): add the file intake layer`

---

### T1-10. `gui/presenter.py` ＋ テスト（山場）

**目的**：GUI の頭脳。**Flet を一切 import しない**。

**作成**：`src/yaqpy/gui/presenter.py`

```python
"""GUI の業務ロジック。Flet を import しないので単体テストできる。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass

from yaqpy.app.dto import EvalMode, EvaluateRequest, EvaluateResult, InputSource
from yaqpy.app.ports import FileSystemPort
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService
from yaqpy.core.engine.limits import StepBudget
from yaqpy.gui import intake, texts
from yaqpy.gui.errors_ja import ErrorViewModel, to_view_model
from yaqpy.gui.state import DocumentState, GuiState, build_options, truncate_for_display


@dataclass(frozen=True, slots=True)
class OpenViewModel:
    name: str = ""
    path: str | None = None
    original_text: str = ""
    byte_size: int = 0
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class ValidationViewModel:
    valid: bool = True
    message: str = ""
    position: int = -1


@dataclass(frozen=True, slots=True)
class RunViewModel:
    display_text: str = ""       # 画面に出す（丸めた）文字列
    full_text: str = ""          # 保存に使う全量。display_text と混同しないこと
    truncated_lines: int = 0
    input_format: str = ""
    output_format: str = ""
    document_count: int = 0
    elapsed_ms: float = 0.0
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class MainPresenter:
    """View（Flet）から呼ばれる唯一の窓口。"""

    def __init__(self, *, service: YqService, fs: FileSystemPort, state: GuiState,
                 size_of: Callable[[str], int] | None = None) -> None:
        self._service = service
        self._fs = fs
        self.state = state
        self._size_of = size_of or os.path.getsize
        self._budget: StepBudget | None = None
        self._last_run: RunViewModel | None = None

    # ------------------------------------------------------------------ 開く

    async def open_path(self, path: str) -> OpenViewModel:
        try:
            item = await asyncio.to_thread(
                intake.from_path, self._fs, path,
                max_bytes=self.state.settings.max_input_bytes,
                size_of=self._size_of,
                origin=intake.DIALOG,
            )
        except intake.IntakeError as e:
            return OpenViewModel(error=ErrorViewModel("intake", str(e)))
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return OpenViewModel(error=to_view_model(e))
        return self._accept(item)

    async def open_dropped(self, path: str) -> OpenViewModel:
        vm = await self.open_path(path)
        return vm

    def open_text(self, text: str, *, name: str = "") -> OpenViewModel:
        return self._accept(intake.from_text(text, name=name))

    def close_document(self) -> None:
        self.state.document = DocumentState()
        self.state.query.expression = "."
        self._last_run = None

    def _accept(self, item: intake.IntakeItem) -> OpenViewModel:
        self.state.document = DocumentState(path=item.path, name=item.name,
                                            original_text=item.text, byte_size=item.byte_size)
        self.state.query.expression = "."          # 新しい文書は恒等式から始める
        self._last_run = None
        return OpenViewModel(name=item.name, path=item.path, original_text=item.text,
                             byte_size=item.byte_size)

    # ------------------------------------------------------------------ 式の検証

    def validate(self, expression: str) -> ValidationViewModel:
        if not expression.strip():
            return ValidationViewModel()           # 空は「.」と同じ扱いで有効
        info = self._service.validate_expression(expression)
        if info.valid:
            return ValidationViewModel()
        vm = to_view_model_from_info(info)
        return ValidationViewModel(valid=False, message=vm.message, position=vm.position)

    # ------------------------------------------------------------------ 実行

    async def run(self) -> RunViewModel:
        if self.state.running:
            return RunViewModel(error=ErrorViewModel("busy", texts.ERR_BUSY))
        if not self.state.document.is_loaded:
            return RunViewModel(error=ErrorViewModel("no_document", texts.ERR_NO_DOCUMENT))

        validation = self.validate(self.state.query.expression)
        if not validation.valid:
            return RunViewModel(error=ErrorViewModel("expression_syntax", validation.message,
                                                     hint=texts.HINT_EXPRESSION,
                                                     position=validation.position))

        request = self._build_request()
        budget = self._service.new_budget(request.options)
        self._budget = budget
        self.state.running = True
        try:
            result = await asyncio.to_thread(self._evaluate_sync, request, budget)
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return RunViewModel(error=to_view_model(e))
        finally:
            self.state.running = False
            self._budget = None
        vm = self._success(result)
        self._last_run = vm
        return vm

    def cancel(self) -> None:
        budget = self._budget
        if budget is not None:
            budget.cancel()

    @property
    def last_run(self) -> RunViewModel | None:
        """最後に成功した実行結果（保存で使う。G3）。"""
        return self._last_run

    # ------------------------------------------------------------------ 内部

    def _evaluate_sync(self, request: EvaluateRequest, budget: StepBudget) -> EvaluateResult:
        """別スレッドで動く同期部分。ここだけが重い。"""
        return self._service.evaluate(request, MemorySink(), budget=budget)

    def _build_request(self) -> EvaluateRequest:
        d, q = self.state.document, self.state.query
        return EvaluateRequest(
            expression=q.expression or ".",
            inputs=(InputSource(d.source_name, d.original_text),),
            mode=EvalMode.STREAM,
            options=build_options(self.state),
            input_format=q.input_format,       # "auto" なら service が拡張子で判定する
            output_format=q.output_format,
        )

    def _success(self, result: EvaluateResult) -> RunViewModel:
        full = result.output or ""
        shown, omitted = truncate_for_display(full, self.state.settings.max_display_lines)
        return RunViewModel(
            display_text=shown,
            full_text=full,
            truncated_lines=omitted,
            input_format=result.input_format,
            output_format=result.output_format,
            document_count=result.document_count,
            elapsed_ms=result.elapsed_seconds * 1000.0,
        )


def to_view_model_from_info(info: object) -> ErrorViewModel:
    """ExpressionInfo（例外ではない）を ErrorViewModel に合わせる。"""
    message = getattr(info, "message", "")
    position = getattr(info, "position", -1)
    where = f"式の {position + 1} 文字目でエラー" if position >= 0 else "式のエラー"
    return ErrorViewModel("expression_syntax", f"{where}：{message}",
                          hint=texts.HINT_EXPRESSION, position=position)
```

**作成**：`tests/unit/test_gui_presenter.py`

```python
"""Presenter のテスト（GUI 設計書 9-2 の T5〜T10・T15）。"""

from __future__ import annotations

import json
import unittest

from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

SAMPLE = (
    "# サーバー設定\n"
    "server:\n"
    "  port: 8080 # 開発用\n"
    "  hosts: [a, b]\n"
    "items:\n"
    "  - name: pen\n"
    "    price: 120\n"
    "  - name: book\n"
    "    price: 980\n"
)
BROKEN = "a: [1\n"
FILES = {"/w/sample.yaml": SAMPLE, "/w/broken.yaml": BROKEN, "/w/data.json": '{"a": 1}'}


def make_presenter(environ: dict[str, str] | None = None) -> MainPresenter:
    fs = InMemoryFileSystem(dict(FILES))
    service = YqService(fs, StaticEnvironment(environ or {}))
    return MainPresenter(service=service, fs=fs, state=GuiState(),
                         size_of=lambda p: len(fs.files[p].encode("utf-8")))


class OpenTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_keeps_the_original_text(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/sample.yaml")
        self.assertTrue(vm.ok)
        self.assertEqual(vm.original_text, SAMPLE)
        self.assertEqual(p.state.document.name, "sample.yaml")
        self.assertEqual(p.state.query.expression, ".")

    async def test_open_missing_file_reports_an_error(self) -> None:
        p = make_presenter()
        vm = await p.open_path("/w/nope.yaml")
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "intake")

    async def test_close_clears_the_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.close_document()
        self.assertFalse(p.state.document.is_loaded)


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_returns_the_whole_document(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        vm = await p.run()
        self.assertTrue(vm.ok)
        self.assertEqual(vm.input_format, "yaml")
        self.assertEqual(vm.output_format, "yaml")
        self.assertEqual(vm.document_count, 1)
        self.assertIn("# サーバー設定", vm.full_text)     # コメントが保たれている

    async def test_property_filter(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.port"
        vm = await p.run()
        self.assertEqual(vm.full_text, "8080\n")

    async def test_json_output(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.output_format = "json"
        p.state.query.expression = ".server"
        vm = await p.run()
        self.assertEqual(vm.output_format, "json")
        self.assertEqual(json.loads(vm.full_text), {"port": 8080, "hosts": ["a", "b"]})

    async def test_json_input_is_detected_from_the_extension(self) -> None:
        p = make_presenter()
        await p.open_path("/w/data.json")
        vm = await p.run()
        self.assertEqual(vm.input_format, "json")

    async def test_select_expression(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".items[] | select(.price > 500)"
        vm = await p.run()
        self.assertIn("book", vm.full_text)
        self.assertNotIn("pen", vm.full_text)

    async def test_syntax_error_is_not_evaluated(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = ".server.("
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "expression_syntax")
        self.assertEqual(vm.full_text, "")

    async def test_broken_yaml_keeps_the_original(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.yaml")
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertIn(vm.error.code, {"yaml_syntax", "format"})
        self.assertEqual(p.state.document.original_text, BROKEN)   # 原文は残っている

    async def test_run_without_a_document(self) -> None:
        p = make_presenter()
        vm = await p.run()
        self.assertEqual(vm.error.code, "no_document")


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_env_is_denied_by_default(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.code, "security")
        self.assertEqual(vm.error.capability, "env")

    async def test_env_can_be_allowed_from_settings(self) -> None:
        p = make_presenter({"NAME": "x"})
        await p.open_path("/w/sample.yaml")
        p.state.settings.allow_env = True
        p.state.query.expression = "strenv(NAME)"
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertEqual(vm.full_text, "x\n")


class CancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_budget_becomes_an_error(self) -> None:
        p = make_presenter()
        await p.open_path("/w/sample.yaml")
        original = p._service.new_budget

        def pre_cancelled(options):          # noqa: ANN001, ANN202
            budget = original(options)
            budget.cancel()
            return budget

        p._service.new_budget = pre_cancelled          # type: ignore[method-assign]
        vm = await p.run()
        self.assertFalse(vm.ok)
        self.assertEqual(vm.error.limit, "cancelled")

    async def test_cancel_without_a_running_job_is_harmless(self) -> None:
        make_presenter().cancel()


class TruncationTests(unittest.IsolatedAsyncioTestCase):
    async def test_display_is_cut_but_full_text_is_not(self) -> None:
        p = make_presenter()
        p.state.settings.max_display_lines = 3
        p.open_text("\n".join(f"- item{i}" for i in range(50)) + "\n", name="many.yaml")
        vm = await p.run()
        self.assertTrue(vm.ok, msg=str(vm.error))
        self.assertEqual(vm.display_text.count("\n"), 3)
        self.assertEqual(vm.full_text.count("\n"), 50)
        self.assertEqual(vm.truncated_lines, 47)


class ValidateTests(unittest.TestCase):
    def test_empty_expression_is_valid(self) -> None:
        self.assertTrue(make_presenter().validate("").valid)

    def test_broken_expression_reports_a_position(self) -> None:
        vm = make_presenter().validate(".server.(")
        self.assertFalse(vm.valid)
        self.assertTrue(vm.message)


if __name__ == "__main__":
    unittest.main()
```

**検証**

```bash
uv run python -m unittest tests.unit.test_gui_presenter -v
```

**DoD**

- [ ] 18 件パス
- [ ] `test_gui_logic_stays_flet_free` がパス（`presenter.py` が flet を import していない）
- [ ] `TruncationTests` が通る（**リスク R8 の担保。ここが落ちたら先に進まない**）

> **失敗しやすい点**：`test_display_is_cut_but_full_text_is_not` の期待行数は、YAML エンコーダの出力に依存します。落ちたら実際の出力を `print(vm.full_text)` で確認し、**期待値の方を実測に合わせて**ください（丸め処理の検証が目的であり、エンコーダの出力仕様を固定する意図はありません）。

**コミット**：`feat(gui): add MainPresenter (open / validate / run / cancel)`

---

### T1-11. `gui/_di.py`

**作成**：`src/yaqpy/gui/_di.py`

```python
"""Composition Root。pages がアプリ層を直接 import しないための唯一の結節点。"""

from __future__ import annotations

from yaqpy.app.local import LocalEnvironment, LocalFileSystem
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import AUTO, GuiState

_service: YqService | None = None


def make_service() -> YqService:
    """YqService はステートレスなので 1 個を使い回す。"""
    global _service
    if _service is None:
        _service = YqService(LocalFileSystem(), LocalEnvironment())
    return _service


def make_presenter(state: GuiState) -> MainPresenter:
    return MainPresenter(service=make_service(), fs=LocalFileSystem(), state=state)


def input_format_choices() -> list[str]:
    """props は出力専用なのでここには出てこない。"""
    return [AUTO, *make_service().list_formats().input_formats]


def output_format_choices() -> list[str]:
    return [AUTO, *make_service().list_formats().output_formats]


def extension_for(format_name: str) -> str:
    """出力形式 → 既定の拡張子（GUI 側に対応表を持たない）。"""
    spec = make_service().formats.get(format_name)
    return spec.extensions[0].lstrip(".") if spec.extensions else format_name
```

**追加テスト**（`tests/unit/test_gui_state.py` の末尾に足してよい）

```python
class DiTests(unittest.TestCase):
    def test_format_choices(self) -> None:
        from yaqpy.gui._di import extension_for, input_format_choices, output_format_choices

        self.assertIn("yaml", input_format_choices())
        self.assertNotIn("props", input_format_choices())   # props は入力に使えない
        self.assertIn("props", output_format_choices())
        self.assertEqual(extension_for("json"), "json")
        self.assertEqual(extension_for("props"), "properties")
```

**DoD**：追加テストがパス。`_di.py` が flet を import していない。

**コミット**：`feat(gui): add the composition root`

---

### T1-12. `gui/app.py` / `gui/_run.py` ＋ 起動ガードのテスト

**作成**：`src/yaqpy/gui/app.py`

```python
"""``yaqpy-gui`` のエントリポイント。

**このモジュールは flet 未導入でも import できること。**
flet に触れるのは ``yaqpy.gui._run`` 側だけにして、導入案内を出せるようにする。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import TextIO

from yaqpy.gui import texts


def flet_available() -> bool:
    return importlib.util.find_spec("flet") is not None


def main_entry(*, stderr: TextIO | None = None) -> int:
    err = stderr or sys.stderr
    if not flet_available():
        err.write(texts.INSTALL_HINT)
        return 1
    from yaqpy.gui._run import run_app

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
```

**作成**：`src/yaqpy/gui/_run.py`

> ⚠ **G0 の実測メモを開いて、`ft.run` / `page.window` / `page.services` の書き方を確認してから写すこと。**

```python
"""flet を実際に起動する層。ここから先だけが flet に依存する。"""

from __future__ import annotations

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import make_presenter
from yaqpy.gui.pages.main_page import MainPage
from yaqpy.gui.state import GuiState


def _main(page: ft.Page) -> None:
    page.title = texts.APP_TITLE
    page.padding = 12
    try:
        page.window.width = 1180
        page.window.height = 820
        page.window.min_width = 820
        page.window.min_height = 560
    except Exception:                      # noqa: BLE001 - 属性名が違う環境でも起動は続ける
        pass

    state = GuiState()
    presenter = make_presenter(state)

    picker = ft.FilePicker()
    page.services.append(picker)           # Flet 1.0: overlay ではなく services

    main_page = MainPage(page=page, presenter=presenter, state=state, picker=picker)
    page.add(main_page.control)


def run_app() -> None:
    ft.run(_main)
```

**作成**：`tests/unit/test_gui_entry.py`

```python
"""起動ガードのテスト（手動テスト M8 の自動化）。"""

from __future__ import annotations

import io
import unittest
from unittest import mock

from yaqpy.gui import app


class EntryGuardTests(unittest.TestCase):
    def test_missing_flet_gives_an_install_hint(self) -> None:
        err = io.StringIO()
        with mock.patch.object(app, "flet_available", return_value=False):
            code = app.main_entry(stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("yaqpy[gui]", err.getvalue())
        self.assertIn("uv sync --extra gui", err.getvalue())

    def test_app_module_imports_without_flet(self) -> None:
        """app.py が import 時点で flet を要求しないこと。"""
        import ast
        import pathlib

        source = pathlib.Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports: list[str] = []
        for node in tree.body:               # 関数の中の import は対象外
            if isinstance(node, ast.Import):
                top_level_imports += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.append(node.module)
        self.assertNotIn("flet", [m.split(".")[0] for m in top_level_imports])


if __name__ == "__main__":
    unittest.main()
```

**DoD**

- [ ] 2 件パス
- [ ] `uv run --extra gui yaqpy-gui` でウィンドウが開く（T1-13 の後）

**コミット**：`feat(gui): add the entry point with a flet-missing guard`

---

### T1-13. `gui/pages/main_page.py`（2 ペイン）

> ⚠ **ここも G0 のメモを見ながら書くこと。** yapilet は `ft.Column` を継承していますが、**本実装は継承せず合成**（`.control` プロパティで Flet のツリーを返す）にします。Flet 1.0 のコントロール継承の仕様に賭けないためです。

**作成**：`src/yaqpy/gui/pages/__init__.py`

```python
"""Flet の画面。ここだけが flet に依存する。"""
```

**作成**：`src/yaqpy/gui/pages/main_page.py`

```python
"""メイン画面：左に原文、右に変換結果。"""

from __future__ import annotations

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import input_format_choices, output_format_choices
from yaqpy.gui.errors_ja import caret_line
from yaqpy.gui.presenter import MainPresenter, RunViewModel
from yaqpy.gui.state import GuiState

MONO = ft.TextStyle(font_family="Consolas", size=12)


def _options(names: list[str]) -> list[ft.DropdownOption]:
    return [ft.DropdownOption(key=n, text=n) for n in names]


class MainPage:
    def __init__(self, *, page: ft.Page, presenter: MainPresenter, state: GuiState,
                 picker: ft.FilePicker) -> None:
        self._page = page
        self._p = presenter
        self._state = state
        self._picker = picker

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

        # --- 式バー ---
        self._expr_field = ft.TextField(label=texts.LBL_EXPRESSION, value=state.query.expression,
                                        hint_text=texts.PH_EXPRESSION, expand=True,
                                        text_style=MONO,
                                        on_change=self._on_expression_change,
                                        on_submit=self._on_run)
        self._expr_error = ft.Text("", color=ft.Colors.ERROR, size=12, selectable=True,
                                   visible=False)
        self._run_button = ft.Button(content=texts.BTN_RUN, icon=ft.Icons.PLAY_ARROW,
                                     on_click=self._on_run, disabled=True)
        self._cancel_button = ft.Button(content=texts.BTN_CANCEL, icon=ft.Icons.STOP,
                                        on_click=self._on_cancel, disabled=True)
        self._progress = ft.ProgressBar(visible=False)

        # --- 2 ペイン ---
        self._original = ft.TextField(multiline=True, read_only=True, expand=True,
                                      min_lines=20, max_lines=1000, text_style=MONO,
                                      border=ft.InputBorder.OUTLINE)
        self._converted = ft.TextField(multiline=True, read_only=True, expand=True,
                                       min_lines=20, max_lines=1000, text_style=MONO,
                                       border=ft.InputBorder.OUTLINE)
        self._truncated_note = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT,
                                       visible=False)

        # --- 状態バー ---
        self._status_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=16)
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

        expr_bar = ft.Column([
            ft.Row([self._expr_field, self._run_button, self._cancel_button], spacing=8),
            self._expr_error,
        ], spacing=2)

        panes = ft.Row([
            ft.Column([ft.Text(texts.LBL_ORIGINAL, size=12, weight=ft.FontWeight.W_600),
                       self._original], expand=True, spacing=4),
            ft.Column([ft.Row([ft.Text(texts.LBL_CONVERTED, size=12,
                                       weight=ft.FontWeight.W_600)]),
                       self._converted, self._truncated_note], expand=True, spacing=4),
        ], expand=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

        status_bar = ft.Row([self._status_icon, self._status_text,
                             ft.Container(expand=True), self._format_text], spacing=8)

        return ft.Column([file_bar, ft.Divider(height=1), format_bar, expr_bar,
                          self._progress, panes, ft.Divider(height=1), status_bar],
                         expand=True, spacing=8)

    # ------------------------------------------------------------------ 操作

    async def _on_open(self, e: ft.Event[ft.Button]) -> None:
        files = await self._picker.pick_files(
            dialog_title=texts.BTN_OPEN,
            allow_multiple=False,
            allowed_extensions=["yaml", "yml", "json", "toon", "properties"],
        )
        if not files:
            return
        await self._load(files[0].path)

    async def _load(self, path: str) -> None:
        vm = await self._p.open_path(path)
        if not vm.ok:
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._original.value = vm.original_text
        self._file_label.value = f"{vm.name}  ({vm.byte_size:,} B)"
        self._expr_field.value = self._state.query.expression
        self._close_button.disabled = False
        self._run_button.disabled = False
        self._expr_error.visible = False
        await self._run()

    def _on_close(self, e: ft.Event[ft.Button]) -> None:
        self._p.close_document()
        self._original.value = ""
        self._converted.value = ""
        self._file_label.value = texts.MSG_NO_DOCUMENT
        self._expr_field.value = "."
        self._close_button.disabled = True
        self._run_button.disabled = True
        self._truncated_note.visible = False
        self._status_text.value = ""
        self._format_text.value = ""

    def _on_input_format(self, e: ft.Event[ft.Dropdown]) -> None:
        self._state.query.input_format = e.control.value or "auto"
        self._page.run_task(self._run)

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
        """入力中は検証だけ（再実行はしない）。G2 で 300 ms のデバウンスを入れる。"""
        expression = e.control.value or ""
        self._state.query.expression = expression
        result = self._p.validate(expression)
        if result.valid:
            self._expr_field.error_text = None
            self._expr_error.visible = False
        else:
            self._expr_field.error_text = result.message
            caret = caret_line(result.position)
            self._expr_error.value = f"{result.message}\n{expression}\n{caret}" if caret \
                else result.message
            self._expr_error.visible = True

    async def _on_run(self, e: ft.Event) -> None:
        await self._run()

    def _on_cancel(self, e: ft.Event[ft.Button]) -> None:
        self._p.cancel()

    # ------------------------------------------------------------------ 実行

    async def _run(self) -> None:
        if not self._state.document.is_loaded:
            return
        self._set_running(True)
        self._page.update()                 # G0 メモで「不要」と判明したらこの行は消してよい
        vm = await self._p.run()
        self._set_running(False)
        self._apply(vm)

    def _set_running(self, running: bool) -> None:
        self._progress.visible = running
        self._run_button.disabled = running
        self._cancel_button.disabled = not running
        if running:
            self._status_icon.name = ft.Icons.HOURGLASS_TOP
            self._status_text.value = texts.MSG_RUNNING
            self._status_text.color = ft.Colors.ON_SURFACE

    def _apply(self, vm: RunViewModel) -> None:
        if not vm.ok:
            self._converted.value = ""
            self._show_error(vm.error.message, vm.error.hint)
            return
        self._converted.value = vm.display_text
        self._truncated_note.visible = vm.truncated_lines > 0
        self._truncated_note.value = texts.MSG_TRUNCATED.format(n=f"{vm.truncated_lines:,}")
        self._input_dd.value = vm.input_format
        self._output_dd.value = vm.output_format
        self._format_text.value = f"{vm.input_format} → {vm.output_format}"
        self._status_icon.name = ft.Icons.CHECK_CIRCLE_OUTLINE
        self._status_icon.color = ft.Colors.GREEN
        self._status_text.color = ft.Colors.ON_SURFACE
        self._status_text.value = (f"{vm.document_count} document / {vm.elapsed_ms:.1f} ms / "
                                   f"出力 {len(vm.full_text.encode('utf-8')):,} bytes")

    def _show_error(self, message: str, hint: str = "") -> None:
        self._status_icon.name = ft.Icons.ERROR_OUTLINE
        self._status_icon.color = ft.Colors.ERROR
        self._status_text.color = ft.Colors.ERROR
        self._status_text.value = f"{message}（{hint}）" if hint else message
```

**検証（手動）**

```bash
uv run --extra gui yaqpy-gui
```

- `examples/sample.yaml` を開く → 左に原文（コメント込み）、右に YAML
- 出力形式を `json` に → 右だけ JSON に変わる
- 式に `.server.port` → 右が `8080`
- 式に `.server.(` → 赤い下線つきエラーが出て、実行されない
- `examples/` に壊れた YAML を作って開く → 右にエラー、アプリは落ちない

**DoD**

- [ ] 受入 **A1**（開く）・**A2**（形式切り替え）・**A8**（壊れた YAML）が満たされる
- [ ] フルテストがパス
- [ ] `uv run ruff check src/yaqpy/gui` に致命的な指摘がない

**コミット**：`feat(gui): add the two-pane main page`

---

### T1-14. `yaqpy --gui`（CLI からの起動）

**目的**：`yaqpy-gui` に加えて、**`uv run yaqpy --gui`** でも GUI を起動できるようにする。

**前提**：T1-12 が済んでいること（`yaqpy.gui.app.main_entry` を呼ぶだけなので、GUI 本体の完成は待たなくてよいが、**T1-13 の後に置く**と「起動して動く」ことまで一気に確認できる）。

**設計の決めごと**

| 決めごと | 内容 | 理由 |
|---|---|---|
| gui の import は**関数の中で遅延** | `cli/main.py` のモジュール先頭では import しない | flet 未導入でも CLI 本体（`yaqpy '.a' file.yaml`）が動くこと、CLI の起動が GUI 側の副作用に巻き込まれないこと |
| 併用は**拒否**する | `--gui` と式・ファイルを一緒に渡すとエラー（終了コード 1） | 黙って無視すると、`yaqpy --gui a.yaml` で「開いてくれる」と誤解させる。起動時のファイル指定は将来の宿題（設計書 12 章 Q8） |
| `-V` は優先 | version 判定の**直後**に分岐を置く | `yaqpy --gui -V` はバージョンを出して終わる |
| stdin に触れない | `resolve_invocation` より**前**で分岐する | パイプ入力を消費してしまうと、後続のプロセスが困る |
| **依存方向の例外**を 1 か所だけ認める | `cli/main.py` だけが `yaqpy.gui` を import してよい | 下の ⚠ を参照。例外は表で明示し、「遅延している」ことを別のテストで縛る |

> ⚠ **落とし穴（実測済み）**：`cli/main.py` に gui の import を足すだけだと、T1-5 で作った依存方向テストが落ちます。
>
> ```text
> FAIL: test_dependency_direction (module='yaqpy.cli.main', imported='yaqpy.gui')
> AssertionError: True is not false : yaqpy.cli.main must not import yaqpy.gui
> ```
>
> `FORBIDDEN["yaqpy.cli"]` に `yaqpy.gui` が入っており、`imports_of()` は `ast.walk` で**関数の中の import も拾う**ためです。**テストを消すのではなく、例外を 1 件だけ明示して**通します（変更 3）。

**変更 1**：`src/yaqpy/cli/parser.py` に `--gui` を足す（`build_parser` の misc グループ）

置換前：

```python
    m.add_argument("-V", "--version", action="store_true", help="Print version information and quit")
    return parser
```

置換後：

```python
    m.add_argument("-V", "--version", action="store_true", help="Print version information and quit")
    m.add_argument("--gui", action="store_true",
                   help="Launch the desktop GUI (needs: pip install 'yaqpy[gui]')")
    return parser
```

**変更 2**：`src/yaqpy/cli/main.py`（3 か所）

**2-a** 型注釈のために `argparse` を import する。

置換前：

```python
import logging
import os
```

置換後：

```python
import argparse
import logging
import os
```

**2-b** 起動用の関数を足す（`main` の直前）。

置換前：

```python
def main(argv: list[str] | None = None, *, stdout: TextIO | None = None,
```

置換後：

```python
def _launch_gui(ns: argparse.Namespace, err: TextIO) -> int:
    """``yaqpy --gui``: hand over to the desktop GUI.

    The import is deliberately lazy (inside this function): the CLI must keep working
    when the optional ``gui`` extra (flet) is not installed. ``yaqpy.gui.app`` itself
    does not import flet at module level, so this import is always safe.
    """
    if ns.args or ns.expression or ns.from_file:
        err.write("Error: --gui cannot be combined with an expression or files\n")
        return EXIT_ERROR
    from yaqpy.gui import app as gui_app

    return gui_app.main_entry(stderr=err)


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None,
```

**2-c** `main` の中で、**version 判定の直後・ログ設定の前**に分岐を入れる。

置換前：

```python
    logging.basicConfig(level=logging.DEBUG if ns.verbose else logging.WARNING,
```

置換後：

```python
    if ns.gui:
        return _launch_gui(ns, err)
    logging.basicConfig(level=logging.DEBUG if ns.verbose else logging.WARNING,
```

> `gui_app.main_entry(...)` は**モジュール属性経由**で呼ぶこと（`from yaqpy.gui.app import main_entry` にしない）。テストで `mock.patch("yaqpy.gui.app.main_entry")` が効くための書き方です。

**変更 3**：`tests/unit/test_architecture.py`（3 か所。T1-5 の後の状態に対する差分）

**3-a** 例外の表を足す（`module_name` の直前）。

置換前：

```python
def module_name(path: Path) -> str:
```

置換後：

```python
# 例外：`yaqpy --gui` のためだけに、cli/main.py は gui を（関数の中で遅延して）import してよい。
# 「遅延している」ことは test_cli_reaches_gui_only_lazily が別途検査する。
ALLOWED_EXCEPTIONS: set[tuple[str, str]] = {("yaqpy.cli.main", "yaqpy.gui")}


def module_name(path: Path) -> str:
```

**3-b** 方向テストが例外を見るようにする。

置換前：

```python
                for imported in imports_of(path):
                    for bad in forbidden:
                        with self.subTest(module=module, imported=imported):
```

置換後：

```python
                for imported in imports_of(path):
                    for bad in forbidden:
                        if (module, bad) in ALLOWED_EXCEPTIONS:
                            continue
                        with self.subTest(module=module, imported=imported):
```

**3-c** 「遅延 import」を縛るテストを足す。

置換前：

```python
    def test_no_removed_modules(self) -> None:
```

置換後：

```python
    def test_cli_reaches_gui_only_lazily(self) -> None:
        """cli/main.py の gui import は関数の中だけ。モジュール先頭にあると、
        flet 未導入の環境や CLI 単体の起動が gui の import 副作用に巻き込まれる。"""
        tree = ast.parse((SRC / "cli" / "main.py").read_text(encoding="utf-8"))
        for node in tree.body:                      # 先頭（トップレベル）の文だけを見る
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                with self.subTest(imported=name):
                    self.assertFalse(name == "yaqpy.gui" or name.startswith("yaqpy.gui."),
                                     "cli/main.py must import yaqpy.gui lazily (inside a function)")

    def test_no_removed_modules(self) -> None:
```

> **例外が `cli/main.py` 1 件だけなので、`args.py` / `parser.py` が gui を import した場合は、従来の `test_dependency_direction` がそのまま検出します**（別テストは要りません）。

**作成**：`tests/unit/test_cli_gui_flag.py`

> GUI は起動しません。`main_entry` はモックに差し替え、`flet_available` を偽にしたケースだけ実物の `main_entry` を通します（flet が入っている環境でもウィンドウは開きません）。

```python
"""``yaqpy --gui`` フラグのテスト（GUI を実際に起動しない）。

main_entry はモックに差し替えるので、flet が入っている環境でもウィンドウは開かない。
"""

from __future__ import annotations

import io
import unittest
from unittest import mock

from yaqpy.cli.main import main
from yaqpy.cli.parser import build_parser, parse_args


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_default_is_off(self) -> None:
        self.assertFalse(parse_args([".a"]).gui)

    def test_flag_is_parsed(self) -> None:
        ns = parse_args(["--gui"])
        self.assertTrue(ns.gui)
        self.assertEqual(ns.args, [])

    def test_flag_is_documented_in_help(self) -> None:
        self.assertIn("--gui", build_parser().format_help())


class DelegationTests(unittest.TestCase):
    def test_delegates_to_the_gui_entry_point(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            code, out, err = run("--gui")
        self.assertEqual(code, 0)
        entry.assert_called_once()
        self.assertEqual(out, "")

    def test_the_gui_exit_code_is_propagated(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=7):
            code, _, _ = run("--gui")
        self.assertEqual(code, 7)

    def test_stderr_is_handed_over_for_the_install_hint(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry", return_value=0) as entry:
            run("--gui")
        self.assertIn("stderr", entry.call_args.kwargs)

    def test_missing_flet_prints_the_install_hint(self) -> None:
        """flet が無い環境の再現。実物の main_entry を通すが、起動はしない。"""
        with mock.patch("yaqpy.gui.app.flet_available", return_value=False):
            code, out, err = run("--gui")
        self.assertEqual(code, 1)
        self.assertIn('pip install "yaqpy[gui]"', err)
        self.assertIn("uv sync --extra gui", err)
        self.assertEqual(out, "")

    def test_version_flag_still_wins(self) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, _ = run("--gui", "-V")
        self.assertEqual(code, 0)
        self.assertIn("version", out)
        entry.assert_not_called()


class RejectionTests(unittest.TestCase):
    """--gui と式・ファイルの併用は、黙って無視せずエラーにする。"""

    def _assert_rejected(self, *argv: str) -> None:
        with mock.patch("yaqpy.gui.app.main_entry") as entry:
            code, out, err = run(*argv)
        self.assertEqual(code, 1)
        self.assertIn("cannot be combined", err)
        self.assertEqual(out, "")
        entry.assert_not_called()

    def test_positional_file(self) -> None:
        self._assert_rejected("--gui", "sample.yaml")

    def test_expression_and_file(self) -> None:
        self._assert_rejected("--gui", ".a", "sample.yaml")

    def test_expression_flag(self) -> None:
        self._assert_rejected("--gui", "--expression", ".a")

    def test_from_file_flag(self) -> None:
        self._assert_rejected("--gui", "--from-file", "expr.yq")


if __name__ == "__main__":
    unittest.main()
```

**変更 4**：`tests/acceptance/test_cli.py` に、サブプロセスで確かめるテストを 3 件足す

> 起動前に必ず失敗する引数だけを使います（テスト中に GUI が立ち上がらないように）。

置換前：

```python
class SecurityTests(CliTestCase):
```

置換後：

```python
class GuiFlagTests(CliTestCase):
    """`--gui` の入口だけを検査する（GUI 本体は起動しない: 起動前に必ず失敗する引数のみ使う）。"""

    def test_gui_flag_is_listed_in_help(self) -> None:
        r = yq("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--gui", r.stdout)

    def test_gui_flag_rejects_an_expression(self) -> None:
        r = yq("--gui", ".a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot be combined", r.stderr)

    def test_gui_flag_rejects_a_file(self) -> None:
        path = self.write("a.yaml", "a: 1\n")
        r = yq("--gui", path)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot be combined", r.stderr)


class SecurityTests(CliTestCase):
```

**検証**

```bash
uv run python -m unittest tests.unit.test_cli_gui_flag tests.unit.test_architecture -v
uv run python -m unittest tests.acceptance.test_cli.GuiFlagTests -v
```

```bash
# flet を入れていない環境（uv sync のみ）では、案内が出て終了コード 1
uv run yaqpy --gui ; echo "exit=$?"
# flet を入れた環境では、ウィンドウが開く（T1-13 が済んでいる場合）
uv run --extra gui yaqpy --gui
# 併用は拒否される
uv run yaqpy --gui '.a' ; echo "exit=$?"
```

**DoD**

- [ ] `test_cli_gui_flag` が **12 件**、`GuiFlagTests`（acceptance）が **3 件**、`test_architecture` の追加が **1 件**パス
- [ ] flet 未導入の環境で `uv run yaqpy --gui` が導入案内（`pip install "yaqpy[gui]"` / `uv sync --extra gui`）を出して**終了コード 1**
- [ ] `uv run yaqpy --gui '.a'` が `cannot be combined` を出して終了コード 1
- [ ] flet 導入済みの環境で `uv run --extra gui yaqpy --gui` がウィンドウを開く（`yaqpy-gui` と同じ挙動）
- [ ] `echo 'a: 1' | uv run yaqpy .a` など**既存の CLI が壊れていない**（フルテスト・acceptance 全件パス）
- [ ] `git diff --stat` が**数行〜数十行**の差分になっている（全行が変わっていたら**改行コードの事故**。セクション 0 の 5 を参照）

**コミット**：`feat(cli): add --gui to launch the desktop app`

---

## 4. Phase G1 の完了条件

| # | 条件 | 確認方法 |
|---|---|---|
| D1 | 受入 A1・A2・A8 が通る | 手動（T1-13） |
| D2 | 自動テストが全件パス | フルテスト |
| D3 | `gui/` 以外の依存ゼロが保たれている | `tests.unit.test_architecture` |
| D4 | Presenter 層が flet 非依存 | `test_gui_logic_stays_flet_free` |
| D5 | 表示の丸めが保存用テキストに影響しない | `TruncationTests` |
| D6 | flet 未導入時に案内が出る | `tests.unit.test_gui_entry` ＋ `uv run yaqpy --gui` |
| D7 | `uv run yaqpy --gui` と `uv run yaqpy-gui` の**両方**で起動できる | 手動（T1-14） |
| D8 | 既存の CLI が壊れていない（`--gui` 追加の副作用なし） | acceptance 全件パス |

追加されたテスト件数の目安：`test_api` +4、`test_architecture` +3（T1-5 で +2、T1-14 で +1）、`test_gui_state` +10、`test_gui_errors_ja` +11、`test_gui_intake` +6、`test_gui_presenter` +18、`test_gui_entry` +2、`test_cli_gui_flag` +12、acceptance `GuiFlagTests` +3 = **+69 件**。

---

## 5. G2 への引き継ぎ

| 引き継ぐもの | G2 での使われ方 |
|---|---|
| `MainPresenter` | `build_candidates()` / `filter_candidates()` を**足す**（既存メソッドは触らない） |
| `MainPage._on_expression_change` | 300 ms デバウンスに差し替える |
| `MainPage` の式バー | プロパティのプルダウンと絞り込みを**上に 1 行足す** |
| `RunViewModel.input_format` | 候補を作るときの入力形式として使う（形式判定を二重に書かないため） |

```bash
git checkout -b feat/gui-g2-filter
```

---

## 6. つまずいたときの対処

| 症状 | 対処 |
|---|---|
| `TypeError: evaluate() got an unexpected keyword argument 'budget'` | T1-2 の変更 2（シグネチャ）が入っていない |
| `EvaluateResult.__init__() got an unexpected keyword argument 'input_format'` | T1-3 の変更 1（dto）が入っていない |
| `test_only_standard_library` が flet で落ちる | T1-5 の除外が入っていない |
| `test_dependency_direction` が `yaqpy.cli.main must not import yaqpy.gui` で落ちる | T1-14 の変更 3-a・3-b（`ALLOWED_EXCEPTIONS`）が入っていない |
| `test_cli_reaches_gui_only_lazily` が落ちる | `cli/main.py` の**先頭**で `from yaqpy.gui import ...` している。関数（`_launch_gui`）の中へ移す |
| `yaqpy --gui` を実行しても何も起きない／通常の CLI として解釈される | 変更 2-c の分岐が `logging.basicConfig` より**後ろ**にある、または `parser.py` に `--gui` が無い |
| `git diff --stat` で**全行が変更**になっている | 改行コードが CRLF に化けた。`git checkout -- <file>` で戻して、Edit ツールで置換し直す（セクション 0 の 5） |
| `AttributeError: module 'flet' has no attribute 'DropdownOption'` | G0 メモの「3. MISSING だった API」を見て正しい名前に直す |
| ウィンドウは出るがボタンが反応しない | `async def` ハンドラを `on_click` に渡しているか確認。Flet 1.0 は async ハンドラを受け付ける |
| 変換中にウィンドウが固まる | `_evaluate_sync` を直接呼んでいないか確認。必ず `await asyncio.to_thread(...)` 経由 |
| `RecursionError` | 巨大ファイル。`Limits.max_depth` は既定 1000。まずは小さいファイルで確認する |

---

## 7. 推奨モデルのまとめ

| タスク | Haiku 4.5 | Sonnet 5 / 4.6 | 理由 |
|---|---|---|---|
| T1-1, T1-2, T1-3, T1-6, T1-11, T1-14 | **可** | 可 | 置換前後が明示された機械的な作業（T1-14 のテストは実物で検証済み。**Edit ツールで置換すること**） |
| T1-4, T1-5, T1-7, T1-8, T1-9 | やや厳しい | **推奨** | テストが落ちたときの原因切り分けが要る |
| T1-10, T1-13 | **不可** | **必須** | 非同期・状態遷移・Flet API の擦り合わせという判断が集中する |

> **Haiku でやる場合のコツ**：T1-2 / T1-3 のような「置換前・置換後」が全文で書かれたタスクに限ること。1 タスクずつ渡し、**毎回フルテストを実行させて**次に進むこと。

---

**前**：[Phase G0（PoC）](./0919-03_31_yaqpy-gui-phaseG0.md) ／ **次**：[Phase G2（フィルタ）](./0919-05_31_yaqpy-gui-phaseG2.md)
