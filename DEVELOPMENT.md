###### [toREADME](./README.md)
# yaqpy 開発者向けガイド

---
[toTop](#toreadme)
## セットアップ

[uv](https://docs.astral.sh/uv/) を使います（`uv` がなくても `PYTHONPATH=src python -m yaqpy` で動きます）。

```bash
git clone https://github.com/sgtao/yaqpy
cd yaqpy
uv sync                  # GUI も開発する場合は: uv sync --extra gui
uv run yaqpy '.server.port' examples/sample.yaml
```

---
[toTop](#toreadme)
## 設計の概要

- **ヘキサゴナル（Ports & Adapters）**：CLI・GUI・ライブラリが共通の `YqService` を呼びます。API（WSGI）は今後追加予定です
- **YAML は自前実装**：コメント・キー順・アンカー・スカラーの元の書き方（`0x1F`、`1.50`、クォート）を保持するパーサー／エミッタ
- **依存方向はテストで検査**：実行時の依存ゼロ（`dependencies = []`）と、レイヤ間の import 方向を `tests/unit/test_architecture.py` が検査します

---
[toTop](#toreadme)
## テスト

```bash
# ユニットテスト（916 件。各形式・schema・演算子（性質テストを含む）・レシピ・自己説明・GUI の Presenter など。実際にウィンドウは開きません）
uv run python -m unittest discover -s tests/unit -t .

# CLI 受け入れテスト（73 件。Go 版 acceptance_tests/*.sh から移植（`-s` の分割出力を含む）＋`--gui` の入口＋レシピ・自己説明（実プロセスでの stdout/stderr の分離など））
uv run python -m unittest tests.acceptance.test_cli

# Go 版シナリオのゴールデンテスト（1,091 件）
uv run python -m unittest tests.golden.test_operators
uv run python tools/golden_report.py            # 合格率の一覧。--fails で不一致の詳細

# Go 版の形式シナリオ（XML・CSV/TSV・TOML・properties の 154 件）
uv run python -m unittest tests.golden.test_formats
uv run python tools/golden_report.py --formats  # 形式ごとの合格率。--file xml --fails で詳細

# 依存ゼロ・レイヤ間の import 方向の検査
uv run python -m unittest tests.unit.test_architecture

# ゴールデンデータの再抽出（Go 版 yq のソースが手元にある場合）
uv run python tools/extract_go_scenarios.py <yq のソース>/pkg/yqlib tests/golden/operators tests/golden/formats

# 配布物のビルド
uv build
```

Go 版の演算子のテストシナリオ 1,091 件の内訳は、一致 1,047 件（完全一致 1,016 ＋ 意味的に一致 31）、既知の差異 4 件（`shuffle` の並び。理由は `tests/support/golden.py` の `KNOWN_DIFFERENCES`）、未実装の演算子に当たるもの 28 件（`load` `envsubst` `eval`）、そのほか（環境や外部コマンドに依存して比べられない 12 件）です。形式のシナリオ 154 件（XML 52・CSV/TSV 18・TOML 62・properties 22）は、149 件が一致します（不一致 5 件は TOML のコメント保持）。`now` を含むシナリオは、Go のテストと同じく時計を固定して（`GO_TEST_NOW`）実行します。

IANA の時間帯名を使うテスト（`tz("Australia/Sydney")` など）には、OS の時間帯データが要ります。Windows では、`uv sync` が入れる dev グループの `tzdata` が担います（実行時の依存ではありません。なければそのテストだけスキップされます）。不一致の記録は `tests/golden/formats_manifest.json` にあり、形式ごとの最低合格率は `tests/golden/test_formats.py` の `MIN_PASS_RATE` で守っています。

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
│   ├── xml_tokens.py xml_codec.py  … XML（Go の encoding/xml と同じ寛容な字句解析。実体は展開しない）
│   └── csv_codec.py toml_codec.py  … CSV/TSV、TOML（自前の TOML 1.0 パーサ）
├── recipes/                        … レシピ（データと、Python の値への検査。app/cli/gui/api を import しない）
│   ├── model.py loader.py catalog.py paths.py   … レシピの型、メタデータの読み込み、同梱レシピ、パスの書式（.a[].b[type!=text]）
│   ├── conform.py diff.py analysis.py            … 目標スキーマとの照合、パス単位の差分、落とした項目・補った項目の報告
│   └── builtin/                                   … 同梱の 6 レシピ（*.yaqpy ＋ *.recipe.yaml）と、3 つの API の目標スキーマ（*.schema.json）
├── app/                            … YqService、DTO、ポート（FileSystem/Environment）、printer（-s の SplitWriter を含む）、RecipeService（レシピの実行。常に SecurityPolicy.strict()）、selfdoc / examples（自己説明。登録表から自動生成し、例は実行して確かめる）、recipe_text（報告の文章）
├── cli/                            … argparse、引数解釈（純粋関数）、main、recipe_cli（--recipe ほか）、describe_cli（--print-spec ほか）
└── gui/                            … Flet の GUI（任意依存。presenter は Flet 非依存）
tests/
├── unit/  acceptance/  golden/     … unittest（標準ライブラリのみ）
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
