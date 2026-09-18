# pyyq

`yq`（Go 版 [mikefarah/yq](https://github.com/mikefarah/yq) v4.53.6）の式言語と基本機能を **Python 3.13 の標準ライブラリだけ**で再実装した、YAML/JSON 処理ライブラリ兼 CLI ツールです。

設計書：[docs/0917-02_31_design-python-yq.md](docs/0917-02_31_design-python-yq.md)（Phase 0 ＋ Phase 1 ＝ MVP を実装済み）

## 概要

- **依存ゼロ**：実行時のサードパーティ製ライブラリは 0 個（`dependencies = []`）。テストで機械的に検査しています
- **YAML 自前実装**：コメント・キー順・アンカー・スカラーの元の書き方（`0x1F`、`1.50`、クォート）を保持するパーサー／エミッタ
- **Go 版との互換性**：Go 版のテストシナリオ 1,091 件を抽出して互換テストにしています（下記）
- **Library + CLI**：`import pyyq` で関数として使う方法と、`pyyq` コマンドの両方に対応
- **拡張可能な設計**：ヘキサゴナル（Ports & Adapters）。CLI・GUI・API が共通の `YqService` を呼ぶ構造で、GUI（tkinter）と API（WSGI）は Phase 3 で追加予定
- **対応フォーマット**：YAML（入出力）、JSON（入出力）、properties（出力）、TOON（入出力。Go 版にはない拡張）

## 動作環境

- Python 3.13 以上
- パッケージ管理・実行に [uv](https://docs.astral.sh/uv/) を使用（`uv` がなくても `PYTHONPATH=src python -m pyyq` で動きます）

## セットアップ

```bash
git clone https://github.com/sgtao/pyyq
cd pyyq
uv sync
```

## 使い方

```bash
# 値の取得
uv run pyyq '.server.port' examples/sample.yaml

# 値の更新（インプレース書き換え。コメント・キー順はそのまま）
uv run pyyq -i '.server.port = 9090' examples/sample.yaml

# フォーマット変換（YAML → TOON。LLM 向けにトークン数を削減する Go 版にはない拡張）
uv run pyyq --toon '.' examples/sample.yaml
```

詳細、対応演算子の一覧は **[USAGE.ja.md](USAGE.ja.md)** を参照してください。

## 開発・テスト

```bash
# ユニットテスト（65 件）
uv run python -m unittest discover -s tests/unit -t .

# CLI 受け入れテスト（34 件。Go 版 acceptance_tests/*.sh から移植）
uv run python -m unittest tests.acceptance.test_cli

# Go 版シナリオのゴールデンテスト（1,091 件）
uv run python -m unittest tests.golden.test_operators
uv run python tools/golden_report.py            # 合格率の一覧。--fails で不一致の詳細

# 依存ゼロ・レイヤ間の import 方向の検査
uv run python -m unittest tests.unit.test_architecture

# ゴールデンデータの再抽出（Go 版ソースが隣にある場合）
uv run python tools/extract_go_scenarios.py ../11_ref-mikefarah-yq/pkg/yqlib tests/golden/operators

# 配布物
uv build
```

## リポジトリ構成

```text
src/pyyq/
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
└── cli/                            … argparse、引数解釈（純粋関数）、main
tests/
├── unit/  acceptance/  golden/     … unittest（標準ライブラリのみ）
└── support/golden.py               … Go 版 resultToString と同じ形式で比較するハーネス
tools/
├── extract_go_scenarios.py         … Go テストからシナリオを JSON 抽出
└── golden_report.py                … 合格率レポート
```

## License

[MIT License](LICENSE)

Go 版 yq（MIT）の設計・テストシナリオを参考にしています（[NOTICE](NOTICE)）。

---

🤖 Built with [Claude Code](https://claude.com/claude-code)
