###### [toREADME](./README.ja.md)
# yaqpy 開発者向けガイド

---
[toTop](#toreadme)
## セットアップ

[uv](https://docs.astral.sh/uv/) を使います（`uv` がなくても `PYTHONPATH=src python -m yaqpy` で動きます）。

```bash
git clone https://github.com/sgtao/yaqpy
cd yaqpy
uv sync                  # GUI も開発する場合は: uv sync --extra gui（Web 版も: uv sync --extra gui --extra web）
uv run yaqpy '.server.port' examples/sample.yaml
```

---
[toTop](#toreadme)
## 設計の概要

- **ヘキサゴナル（Ports & Adapters）**：CLI・GUI（デスクトップ・Web 版）・ライブラリが共通の `YqService` を呼びます。API（WSGI）は今後追加予定です
- **Web 版の GUI も同じ画面**：`yaqpy-web`（`yaqpy --web`）は、デスクトップ版（`yaqpy-gui`）と同じ Flet の画面を `flet.fastapi` ＋ uvicorn で配ります（`gui/_web.py`）。評価は `SandboxFileSystem` と空の環境変数の上で動き、サーバーのファイル・環境変数に届きません（`gui/_di.py` の `make_web_service`）。Flet の Web 表示の実測は `docs/flet-1.0-api-notes.md` の 7 章
- **YAML は自前実装**：コメント・キー順・アンカー・スカラーの元の書き方（`0x1F`、`1.50`、クォート）を保持するパーサー／エミッタ
- **依存方向はテストで検査**：実行時の依存ゼロ（`dependencies = []`）と、レイヤ間の import 方向を `tests/unit/test_architecture.py` が検査します

---
[toTop](#toreadme)
## テスト

テストは **pytest**（`uv sync` が入れる dev 依存。設定は `pyproject.toml` の `[tool.pytest.ini_options]`）で走らせます。テストクラスは `unittest.TestCase` を継承しない素のクラス（`class XxxTests:`）で、`subTest` の代わりに `@pytest.mark.parametrize`、`assertXxx` の代わりに素の `assert` を使います。

```bash
# 全部まとめて（並列。pytest-xdist）
uv run pytest -n auto

# ユニットテスト（1,722 件。各形式・schema・演算子（性質テストを含む）・レシピ・自己説明・入力形式の自動判定・GUI の Presenter・実行ログ・ログ画面など。実際にウィンドウは開きません。Web 版のサーバーは、[web] extra があれば 127.0.0.1 の空きポートで実際に起動して確かめます）
uv run pytest tests/unit -n auto

# CLI 受け入れテスト（103 件。Go 版 acceptance_tests/*.sh から移植（`-s` の分割出力を含む）＋`--gui` の入口＋レシピ・自己説明・自動判定（実プロセスでの stdout/stderr の分離など）＋`examples/` の実ファイルの変換（`test_examples.py`））
uv run pytest tests/acceptance -n auto

# Go 版シナリオのゴールデンテスト（演算子 1,091 件・形式 154 件）
uv run pytest tests/golden
uv run python tools/golden_report.py            # 合格率の一覧。--fails で不一致の詳細
uv run python tools/golden_report.py --formats  # 形式ごとの合格率。--file xml --fails で詳細

# 依存ゼロ・レイヤ間の import 方向の検査
uv run pytest tests/unit/test_architecture.py

# マーカーで絞る（tests/conftest.py が golden・acceptance・gui を自動で付ける）
uv run pytest -m "not acceptance and not golden"    # 速いテストだけ
uv run pytest -m gui                                # GUI 関連だけ

# カバレッジ（計測のみ。下限は設けていません）
uv run pytest --cov=yaqpy --cov-report=term-missing

# ゴールデンデータの再抽出（Go 版 yq のソースが手元にある場合）
uv run python tools/extract_go_scenarios.py <yq のソース>/pkg/yqlib tests/golden/operators tests/golden/formats

# 配布物のビルド
uv build
```

Go 版の演算子のテストシナリオ 1,091 件の内訳は、一致 1,047 件（完全一致 1,016 ＋ 意味的に一致 31）、既知の差異 4 件（`shuffle` の並び。理由は `tests/support/golden.py` の `KNOWN_DIFFERENCES`）、未実装の演算子に当たるもの 28 件（`load` `envsubst` `eval`）、そのほか（環境や外部コマンドに依存して比べられない 12 件）です。形式のシナリオ 154 件（XML 52・CSV/TSV 18・TOML 62・properties 22）は、149 件が一致します（不一致 5 件は TOML のコメント保持）。`now` を含むシナリオは、Go のテストと同じく時計を固定して（`GO_TEST_NOW`）実行します。

IANA の時間帯名を使うテスト（`tz("Australia/Sydney")` など）には、OS の時間帯データが要ります。Windows では、`uv sync` が入れる dev グループの `tzdata` が担います（実行時の依存ではありません。なければそのテストだけスキップされます）。不一致の記録は `tests/golden/formats_manifest.json` にあり、形式ごとの最低合格率は `tests/golden/test_formats.py` の `MIN_PASS_RATE` で守っています。

---
[toTop](#toreadme)
## 対応する Python の版（3.11・3.12・3.13）

`requires-python = ">=3.11"` で、**3.11・3.12・3.13 で動作を確認**します（開発用の `.venv` と `.python-version` は 3.13）。3.11 が下限なので、次の 3.12 以降の機能は **使わない**でください。

- `type X = ...` 文 → `X: TypeAlias = ...`、PEP 695 のジェネリクス（`def f[T]`、`class C[T]`）→ `TypeVar`
- `typing.override`、`itertools.batched`、`Path.walk`、`copy.replace`、`warnings.deprecated`、`argparse` の `deprecated=`
- 入れ子の引用符を含む f 文字列（PEP 701）

```bash
uv run python tools/check_pythons.py             # 下限の検査（vermin）＋ 3 つの版で全テスト（約 6 分）
uv run python tools/check_pythons.py 3.11        # 1 つの版だけ
uv run python tools/check_pythons.py --quick     # tests/acceptance（examples/ の実変換）だけ
```

- 版ごとに別の環境（`.venv-py3.11` など。`.gitignore` 済み）を作り、開発用の `.venv` を壊しません。Python 本体は uv が取得します（`mise` などは不要）
- `examples/` のファイルを実際に変換して期待どおりか調べるのは `tests/acceptance/test_examples.py`（期待値は 3.13 の出力を目で確かめたもの）。3 つの版で同じテストが通ることが「実変換が期待どおり」の確認です
- 3.14 以降を名乗るときは、同じ手順で通してから `pyproject.toml` の classifiers と `tools/check_pythons.py` の `VERSIONS` に足します
- Web 版のテスト（`flet-web` が要る）は、`--extra web` を付けた版でだけ走ります（既定では skip）

---
[toTop](#toreadme)
## リポジトリ構成

```text
src/yaqpy/
├── errors.py options.py api.py     … 例外・設定・公開 API
├── core/
│   ├── model/                      … Node（値は文字列＋タグで保持）、タグ解決、Python 変換、日時（Go の時間レイアウトの読み書き）
│   ├── lang/                       … 字句解析（Go 版と同じルール表）→ 操車場法 → AST
│   ├── engine/                     … Context / Navigator / ステップ上限
│   └── operators/                  … 演算子（@operator で登録）。sequences・structure（配列・マップ）、strings・regex（文字列と Go 互換の正規表現）、codecs（encode/decode）、datetime_ops、documents（split_doc）、schema、prune（prune_null / prune_empty）ほか
├── formats/
│   ├── yaml/                       … 自前 YAML（parser / emitter / codec）
│   ├── json_codec.py props_codec.py toon_codec.py registry.py
│   ├── sniff.py                    … 入力形式の中身での判定（yaqpy 独自。FormatRegistry.guess が使う）
│   ├── xml_tokens.py xml_codec.py  … XML（Go の encoding/xml と同じ寛容な字句解析。実体は展開しない）
│   └── csv_codec.py toml_codec.py  … CSV/TSV、TOML（自前の TOML 1.0 パーサ）
├── recipes/                        … レシピ（データと、Python の値への検査。app/cli/gui/api を import しない）
│   ├── model.py loader.py catalog.py paths.py   … レシピの型、メタデータの読み込み、同梱レシピ、パスの書式（.a[].b[type!=text]）
│   ├── conform.py diff.py analysis.py            … 目標スキーマとの照合、パス単位の差分、落とした項目・補った項目の報告
│   └── builtin/                                   … 同梱の 6 レシピ（*.yaqpy ＋ *.recipe.yaml）と、3 つの API の目標スキーマ（*.schema.json）
├── app/                            … YqService、DTO、ポート（FileSystem/Environment）、printer（-s の SplitWriter を含む）、RecipeService（レシピの実行。常に SecurityPolicy.strict()）、selfdoc / examples（自己説明。登録表から自動生成し、例は実行して確かめる）、recipe_text（報告の文章）
├── cli/                            … argparse、引数解釈（純粋関数）、main、recipe_cli（--recipe ほか）、describe_cli（--print-spec ほか）
└── gui/                            … Flet の GUI（任意依存。presenter は Flet 非依存）。pages/（main・settings・ask_ai・log の各画面と clipboard）、_run（画面の組み立て。デスクトップ・Web 共通。タブは MAIN/SETTINGS/ASK_AI/LOG の並びで、LOG はデスクトップだけ）、run_log（実行ログの組み立て・読み戻し・保存先の整理。Flet 非依存）、log_presenter（ログ画面のロジック）、expression_file（`.yaqpy` の読み書きの規則）、ask_ai（相談文への反映）、web_assets（Web 版の index.html にドロップ用のスクリプトを足す）、_web（Web 版のサーバー。uvicorn を使うのはここだけ）、_upload（Web 版のアップロード受け取り）、web_config（Web 版の設定・上限。Flet 非依存）、app（yaqpy-gui / yaqpy-web の入口とヘルプ）、logo と assets/（ロゴ。原本はリポジトリの assets/images で、コピーが一致することをテストで確認）
tests/
├── unit/  acceptance/  golden/     … pytest（tests/conftest.py が golden/acceptance/gui にマーカーを付ける）
├── golden/formats/                 … Go 版の形式シナリオ（抽出した JSON）と formats_manifest.json
├── data/testsets/                  … schema の試験に使う 10 個のデータ（23_testSets のコピー）
└── support/golden.py golden_formats.py jsonschema_mini.py
                                    … 演算子・形式のシナリオを比較するハーネス、試験用の小さなスキーマ検証器
tools/
├── extract_go_scenarios.py         … Go テストからシナリオ（演算子・形式）を JSON 抽出
└── golden_report.py                … 合格率レポート（--formats で形式別）
docs/                               … 設計書・GUI 設計書・Flet 実測メモ
```

---
[toTop](#toreadme)
## レシピを足す・直す

- 同梱のレシピは `src/yaqpy/recipes/builtin/名前.yaqpy`（式）と `名前.recipe.yaml`（`carries` `drops` `adds` `target_schema` `tests`）の組です。目標スキーマは同じ場所の `*.schema.json` で、**各ファイルの `$comment` に参照元（公式の定義の URL と読んだ日）**があります。API の仕様が変わったら、そこを読み直して直します
- 式は、USAGE.ja.md の「式の書き方の規約」で書きます（代入の右辺の任意キーは `pick`、`select` の後ろに定数を続けない、など）。守らないと、エラーにならずに結果だけが変わります
- `tests:` の期待値は、式を実行して作り、公式の仕様と**人が突き合わせてから**固定します（実行結果をそのまま正解にしない）
- 足したら、`tests/unit/test_recipes_builtin.py`（`NAMES`・往復テスト）を更新し、`yaqpy --recipe 名前 --recipe-test` を通します。`carries` `drops` は、テストの入力のすべてのキーが「運ぶ」か「落とす」に入っていること（`NOT HANDLED` が出ないこと）をテストが確かめます
- **wheel に入ること**：`*.yaqpy` `*.recipe.yaml` `*.schema.json` は `yaqpy/recipes/builtin/` の中に置けば、ビルド（`uv build`）に含まれます
- 自己説明（`--print-spec` など）は登録表から作るので、演算子・形式・レシピを足すと、出力も変わります。USAGE.ja.md の「まだ使えないもの」の一覧（`<!-- yaqpy:unimplemented-operators:begin -->` の間）は、実装と一致することをテストが確かめます。**未実装の演算子を実装したら、その一覧と `tests/unit/test_selfdoc.py` の `NOT_IMPLEMENTED` を更新してください**

---
[toTop](#toreadme)
