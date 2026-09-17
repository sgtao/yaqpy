# pyyq

`yq`（Go 版 mikefarah/yq）の Python 実装。標準ライブラリのみで動作する YAML/JSON/XML/TOML/INI/CSV 処理ライブラリ兼 CLI ツールです。

## 概要

- **依存ゼロ**：サードパーティ製ライブラリを一切使わず、Python 標準ライブラリのみで実装
- **YAML 自前実装**：コメント・キー順序を保持できる独自パーサー/エミッタ
- **Library + CLI**：Python から関数として呼び出す使い方と、コマンドラインから使う使い方の両方に対応
- **拡張可能な設計**：ヘキサゴナルアーキテクチャ（Ports & Adapters）を採用し、将来 GUI・API サーバーへ拡張可能
- **対応フォーマット**：YAML, JSON, XML, TOML（読込）, INI, CSV/TSV

## 動作環境

- Python 3.13 以上
- パッケージ管理・実行に [uv](https://docs.astral.sh/uv/) を使用

## セットアップ

```bash
# リポジトリを取得
git clone <このリポジトリのURL>
cd pyyq

# 依存関係の同期（開発用ツールも含む）
uv sync
```

## 開発・テスト

```bash
# CLI を直接実行
uv run pyyq eval '.a.b' input.yaml

# テストの実行（標準 unittest）
uv run python -m unittest

# ビルド
uv build
```

## 使い方

### CLI として

```bash
# 値の取得
uv run pyyq eval '.name' config.yaml

# 値の更新（インプレース書き換え）
uv run pyyq eval -i '.version = "1.0.0"' config.yaml

# フォーマット変換（YAML → JSON）
uv run pyyq eval -o json '.' config.yaml
```

### ライブラリとして

```python
from pyyq import evaluate, query

# 式を評価して文字列で取得
result = evaluate('.a.b', yaml_text)

# Python オブジェクトとして取得
values = query('.items[]', {"items": [1, 2, 3]})
```

## ライセンス

MIT License
