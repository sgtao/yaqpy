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
# ユニットテスト（213 件。GUI の Presenter などを含む。実際にウィンドウは開きません）
uv run python -m unittest discover -s tests/unit -t .

# CLI 受け入れテスト（49 件。Go 版 acceptance_tests/*.sh から移植＋`--gui` の入口）
uv run python -m unittest tests.acceptance.test_cli

# Go 版シナリオのゴールデンテスト（1,091 件）
uv run python -m unittest tests.golden.test_operators
uv run python tools/golden_report.py            # 合格率の一覧。--fails で不一致の詳細

# 依存ゼロ・レイヤ間の import 方向の検査
uv run python -m unittest tests.unit.test_architecture

# ゴールデンデータの再抽出（Go 版 yq のソースが手元にある場合）
uv run python tools/extract_go_scenarios.py <yq のソース>/pkg/yqlib tests/golden/operators

# 配布物のビルド
uv build
```

Go 版のテストシナリオ 1,091 件の内訳は、一致 837 件（完全一致 808 ＋ 意味的に一致 29）、既知の差異 4 件、未実装の機能に当たるもの 228 件、そのほか（未解決 12 件・スキップ 10 件）です。

---
[toTop](#toreadme)
## リポジトリ構成

```text
src/yaqpy/
├── errors.py options.py api.py     … 例外・設定・公開 API
├── core/
│   ├── model/                      … Node（値は文字列＋タグで保持）、タグ解決、Python 変換、日時
│   ├── lang/                       … 字句解析（Go 版と同じルール表）→ 操車場法 → AST
│   ├── engine/                     … Context / Navigator / ステップ上限
│   └── operators/                  … 演算子（@operator で登録）
├── formats/
│   ├── yaml/                       … 自前 YAML（parser / emitter / codec）
│   ├── json_codec.py props_codec.py toon_codec.py registry.py
├── app/                            … YqService、DTO、ポート（FileSystem/Environment）、printer
├── cli/                            … argparse、引数解釈（純粋関数）、main
└── gui/                            … Flet の GUI（任意依存。presenter は Flet 非依存）
tests/
├── unit/  acceptance/  golden/     … unittest（標準ライブラリのみ）
└── support/golden.py               … Go 版 resultToString と同じ形式で比較するハーネス
tools/
├── extract_go_scenarios.py         … Go テストからシナリオを JSON 抽出
└── golden_report.py                … 合格率レポート
docs/                               … 設計書・GUI 設計書・Flet 実測メモ
```

---
[toTop](#toreadme)
