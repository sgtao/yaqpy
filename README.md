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
git clone <このリポジトリのURL>
cd pyyq
uv sync
```

## 使い方

### CLI として

```bash
# 値の取得
uv run pyyq '.server.port' examples/sample.yaml

# 値の更新（コメント・キー順はそのまま）
uv run pyyq '.server.port = 9090' examples/sample.yaml

# インプレース書き換え（一時ファイル → os.replace で原子的に置換）
uv run pyyq -i '.server.port = 9090' examples/sample.yaml

# フォーマット変換（YAML → JSON、1 行）
uv run pyyq -o json -I 0 '.server' examples/sample.yaml

# 入力なしで文書を作る
uv run pyyq -n '.a.b = "hello"'

# 複数ファイルのマージ（eval-all）
uv run pyyq ea 'select(fi == 0) * select(fi == 1)' base.yaml override.yaml

# 整形（-P）、ドキュメント区切りなし（-N）、結果がなければ終了コード 1（-e）
uv run pyyq -P -N -e '.items[] | select(.price > 500) | .name' examples/sample.yaml
```

主なフラグは Go 版と同じです：`-o/-p`（形式）、`-i`、`-n`、`-I`、`-r[=false]`、`-N`、`-e`、`-P`、`-0`、`-M`、`--from-file`、`--expression`、`--header-preprocess`、`-c`、`--yaml-fix-merge-anchor-to-spec`、`--security-disable-env-ops` など。`-o=j -I=0` のような pflag 風の書き方も受け付けます。pyyq 独自のフラグは `--toon`（TOON で出力）と `--toon-delimiter {comma,tab,pipe}` です。

### ライブラリとして

```python
import pyyq

text = """\
# サーバー設定
server:
  port: 8080   # 開発用
  hosts: [a, b]
"""

print(pyyq.evaluate(".server.port = 9090", text))
# # サーバー設定
# server:
#   port: 9090 # 開発用
#   hosts: [a, b]

pyyq.query(".server.hosts[]", {"server": {"hosts": ["a", "b"]}})   # -> ['a', 'b']
pyyq.update(".b = .a + 1", {"a": 1})                                # -> {'a': 1, 'b': 2}

yq = pyyq.Yq(pyyq.Options(output_format="json", indent=0))
expr = yq.compile(".server")                                        # 事前コンパイル（キャッシュ・スレッド安全）
yq.evaluate(expr, text)                                             # -> '{"port":8080,"hosts":["a","b"]}\n'
```

- ライブラリの既定は `SecurityPolicy.strict()`（`env`・`load`・`system` を禁止）。必要なら `Options(security=SecurityPolicy(allow_env=True))` を渡します。CLI は Go 版と同じ既定（env・file を許可、system は禁止）です
- 設定はすべて呼び出しごとの `Options`（変更不可の dataclass）で渡すため、設定の違う評価を同時に実行できます（グローバル状態なし）
- `Limits(max_steps=..., timeout_seconds=..., max_depth=..., max_input_bytes=...)` で評価量に上限を掛けられます

## TOON 入出力（Go 版にはない拡張）

[TOON（Token-Oriented Object Notation）](https://github.com/toon-format/spec) 仕様 v4.1（2026-07-26 版）に沿ったエンコーダとデコーダを標準ライブラリだけで実装しています。LLM に渡すデータのトークン数を減らしたいときに使います。

```bash
# .toon ファイルは拡張子で自動判定（出力も既定は TOON）
uv run pyyq '.items[0].name' data.toon
uv run pyyq -o yaml '.' data.toon          # TOON → YAML
uv run pyyq -p toon -o json '.' < data.toon   # 標準入力は -p で形式を指定
```

```bash
# 標準出力を TOON にする
uv run pyyq -o toon '.' examples/sample.yaml

# --toon は -o toon の短縮形
uv run pyyq --toon '.items' examples/sample.yaml

# ファイルに書く（リダイレクト、または -i で .toon ファイルをその場で書き換え）
uv run pyyq --toon '.items' examples/sample.yaml > items.toon

# 区切り文字をタブ／パイプにする（既定はカンマ）。字下げ幅は -I
uv run pyyq --toon --toon-delimiter tab '.items' examples/sample.yaml
```

```text
server:
  port: 8080
  hosts[2]: a,b
  tls:
    enabled: true
    cert: /etc/cert.pem
backup:
  enabled: true
  cert: /etc/cert.pem
  schedule: 0 3 * * *
items[2]{name,price}:
  pen,120
  book,980
```

- **コメントは失われます**。TOON 仕様はコメント行（`#` で始まる行）の読み飛ばしをデコーダに義務づけ、エンコーダがコメントを出力することを禁じています。YAML → TOON では JSON 出力と同じくコメントは黙って落ちます
- アンカー／エイリアスは展開してから出力します（JSON と同じ）
- 数値は仕様の正規形（`1.50` → `1.5`、`0x1F` → `31`、`1e21` → `1e+21`）にします。`.inf` / `.nan` は TOON の数値にできないため文字列として出力します
- 同じキー集合を持つオブジェクトの配列は表形式（`items[2]{name,price}:`）、同じキー集合を持つオブジェクトのオブジェクトはキー付き表形式（`users[2:]{age,city}:`）になります。後者は `ToonOptions(keyed_tabular=False)` で無効にできます
- 複数の結果・複数ドキュメントは空行で区切って出力します（TOON には文書区切りがないため）。TOON 入力は常に 1 ドキュメントです
- デコーダは既定で strict（件数・セル数の不一致、字下げ、重複キーをエラー）です。`ToonOptions(strict=False)` で緩和できます。旧仕様の `key[0]:`・`[N,]{...}`・`[#N]` も読めます
- ライブラリでは `Options(output_format="toon", toon=ToonOptions(delimiter="\t", indent=2))` で指定します

## 実装済みの演算子（Phase 1 ＝ 38 種）

`.`、`.a` / `."a b"` / `.a?` / `.a*`、`.[0]` / `.[]` / `.[1:3]`、`..` / `...`、`|`、`,`、`select`、`=` / `|=`、`+=` / `-=` / `*=`、`+`、`-`、`*`（`*+ *? *d *n *c` を含むディープマージ）、`/`、`%`、`//`、`==` / `!=`、`<` `<=` `>` `>=`、`and` / `or` / `not`、リテラル、`[ ]`、`{ }`、`length`、`keys`、`key`、`has`、`del`、`to_entries` / `from_entries` / `with_entries`、`map` / `map_values`、`sort_by` / `sort`、`path`、`as $x` / `$x`、`env` / `strenv`、`tag`、`style`、`line_comment` / `head_comment` / `foot_comment` / `comments`、`test`、`document_index` / `di`、`file_index` / `fi` / `filename`、`parent`、`explode`、`anchor` / `alias`、`min` / `max`、`any` / `all`、`set_path` / `del_paths`、`kind`、`line` / `column`、日時の加減算と比較（RFC3339）

未実装（Phase 2 以降）の演算子は式の解析時に `unknown operator` として報告されます。文字列補間 `\(exp)` も Phase 2 です。

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

### 互換テストの結果（2026-09-17 時点）

| 対象 | シナリオ数 | 判定対象 | 合格（完全一致＋意味一致） | 合格率 |
|---|---:|---:|---:|---:|
| MVP 演算子（Phase 1 のファイル） | 780 | 748 | 748（734＋14） | **100%** |
| 全シナリオ | 1,091 | 841 | 837（808＋29） | 99.5% |

- 「判定対象」は、未実装演算子（`unsupported` 228 件）・Go テスト内の変数を解決できなかったもの（12 件）・別フォーマットが必要なもの（10 件）を除いた数です
- 残り 4 件の不一致はすべて文字列補間 `\(exp)`（Phase 2）です。`tests/golden/manifest.json` に既知の非互換として記録しています
- 「意味一致」は `D<doc>, P[<path>], (<tag>)::` の部分が一致し、YAML 部分を読み込んだ値が同じもの（数値の表記ゆれなど）

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
│   ├── json_codec.py props_codec.py registry.py
├── app/                            … YqService、DTO、ポート（FileSystem/Environment）、printer
└── cli/                            … argparse、引数解釈（純粋関数）、main
tests/
├── unit/  acceptance/  golden/     … unittest（標準ライブラリのみ）
└── support/golden.py               … Go 版 resultToString と同じ形式で比較するハーネス
tools/
├── extract_go_scenarios.py         … Go テストからシナリオを JSON 抽出
└── golden_report.py                … 合格率レポート
```

## 設計書との差分

| 項目 | 設計書 | 実装 | 理由 |
|---|---|---|---|
| YAML の段構成 | scanner → parser → composer → emitter | 行指向の parser（composer を統合）＋ emitter | 1 つの再帰下降パーサーの方がコメント割り当てを一箇所で扱いやすかったため。段を分ける改修は `formats/yaml/` の内側で閉じる |
| `evaluate_together` | 全ドキュメントに設定 | `eval-all` のときだけ設定 | Go 版の `readDocuments`（all-at-once）だけが設定しており、stream モードの `[.x]` などの挙動に影響するため Go 版に合わせた |
| 空行の保持 | — | 保持しない | Go 版（go-yaml）も保持しないため。コメントは head / line / foot として保持する |
| 日時演算 | Phase 2 | RFC3339 の加減算・比較のみ Phase 1 に前倒し | Go 版の `+`/`-`/比較のテストに含まれており、実装コストが小さかったため |

## ライセンス

MIT License。Go 版 yq（MIT）の設計・テストシナリオを参考にしています（[NOTICE](NOTICE)）。
