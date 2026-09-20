###### [toREADME](./README.md)
# yaqpy 使い方ガイド

> 例は、リポジトリを clone した状態（`uv run yaqpy ... examples/sample.yaml`）で書いています。[GitHub のリリースからインストール](README.md#インストール)した場合は、`uv run yaqpy` を `yaqpy` に読み替え、`examples/sample.yaml` は手元の YAML ファイルに置き換えてください。

---
[toTop](#toreadme)
## CLI での使い方

### 基本操作

```bash
# 値の取得
uv run yaqpy '.server.port' examples/sample.yaml

# 標準入力から読む
cat examples/sample.yaml | uv run yaqpy '.server.hosts[]'

# 値の更新（コメント・キー順はそのまま）
uv run yaqpy '.server.port = 9090' examples/sample.yaml

# インプレース書き換え（一時ファイル → os.replace で原子的に置換）
uv run yaqpy -i '.server.port = 9090' examples/sample.yaml

# フォーマット変換（YAML → JSON、1 行）
uv run yaqpy -o json -I 0 '.server' examples/sample.yaml

# 入力なしで文書を作る
uv run yaqpy -n '.a.b = "hello"'

# 複数ファイルのマージ（eval-all）
uv run yaqpy ea 'select(fi == 0) * select(fi == 1)' base.yaml override.yaml

# 整形（-P）、ドキュメント区切りなし（-N）、結果がなければ終了コード 1（-e）
uv run yaqpy -P -N -e '.items[] | select(.price > 500) | .name' examples/sample.yaml
```

### 主なフラグ

Go 版と同じです：`-o/-p`（形式）、`-i`、`-n`、`-I`、`-r[=false]`、`-N`、`-e`、`-P`、`-0`、`-M`、`--from-file`、`--expression`、`--header-preprocess`、`-c`、`--yaml-fix-merge-anchor-to-spec`、`--security-disable-env-ops` など。`-o=j -I=0` のような pflag 風の書き方も受け付けます。yaqpy 独自のフラグは `--toon`（TOON で出力）と `--toon-delimiter {comma,tab,pipe}` です。

- 出力形式は `-o`（`yaml` / `json` / `props` / `toon`）で指定します。**`-p`（入力形式）だけを指定した場合、出力は Go 版との互換のため YAML のまま**です（警告が出ます）
- 入力形式は、ファイルの拡張子（`.yaml` `.yml` `.json` `.toon`）から自動判定します。拡張子が不明なとき、および標準入力は YAML として扱います

---
[toTop](#toreadme)
## TOON 入出力（Go 版にはない拡張）

[TOON（Token-Oriented Object Notation）](https://github.com/toon-format/spec) 仕様 v4.1（2026-07-26 版）に沿ったエンコーダとデコーダを標準ライブラリだけで実装しています。LLM に渡すデータのトークン数を減らしたいときに使います。

```bash
# .toon ファイルは拡張子で自動判定（出力も既定は TOON）
uv run yaqpy '.items[0].name' data.toon
uv run yaqpy -o yaml '.' data.toon          # TOON → YAML
uv run yaqpy -p toon -o json '.' < data.toon   # 標準入力は -p で形式を指定
```

```bash
# 標準出力を TOON にする
uv run yaqpy -o toon '.' examples/sample.yaml

# --toon は -o toon の短縮形
uv run yaqpy --toon '.items' examples/sample.yaml

# ファイルに書く（リダイレクト、または -i で .toon ファイルをその場で書き換え）
uv run yaqpy --toon '.items' examples/sample.yaml > items.toon

# 区切り文字をタブ／パイプにする（既定はカンマ）。字下げ幅は -I
uv run yaqpy --toon --toon-delimiter tab '.items' examples/sample.yaml
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

---
[toTop](#toreadme)
## GUI の使い方

デスクトップアプリです（`uv sync --extra gui` のあと `uv run yaqpy-gui` または `uv run yaqpy --gui`）。画面の見方、式の書き方（初心者向け）、保存・設定・エラーの読み方は **[USAGE-GUI.ja.md](USAGE-GUI.ja.md)** にまとめています。

---
[toTop](#toreadme)
## ライブラリとしての使い方

```python
import yaqpy

text = """\
# サーバー設定
server:
  port: 8080   # 開発用
  hosts: [a, b]
"""

print(yaqpy.evaluate(".server.port = 9090", text))
# # サーバー設定
# server:
#   port: 9090 # 開発用
#   hosts: [a, b]

yaqpy.query(".server.hosts[]", {"server": {"hosts": ["a", "b"]}})   # -> ['a', 'b']
yaqpy.update(".b = .a + 1", {"a": 1})                                # -> {'a': 1, 'b': 2}

yq = yaqpy.Yq(yaqpy.Options(output_format="json", indent=0))
expr = yq.compile(".server")                                        # 事前コンパイル（キャッシュ・スレッド安全）
yq.evaluate(expr, text)                                             # -> '{"port":8080,"hosts":["a","b"]}\n'
```

- ライブラリの既定は `SecurityPolicy.strict()`（`env`・`load`・`system` を禁止）。必要なら `Options(security=SecurityPolicy(allow_env=True))` を渡します。CLI は Go 版と同じ既定（env・file を許可、system は禁止）です
- 設定はすべて呼び出しごとの `Options`（変更不可の dataclass）で渡すため、設定の違う評価を同時に実行できます（グローバル状態なし）
- `Limits(max_steps=..., timeout_seconds=..., max_depth=..., max_input_bytes=...)` で評価量に上限を掛けられます

---
[toTop](#toreadme)
## 実装済みの演算子（Phase 1 ＝ 38 種）

`.`、`.a` / `."a b"` / `.a?` / `.a*`、`.[0]` / `.[]` / `.[1:3]`、`..` / `...`、`|`、`,`、`select`、`=` / `|=`、`+=` / `-=` / `*=`、`+`、`-`、`*`（`*+ *? *d *n *c` を含むディープマージ）、`/`、`%`、`//`、`==` / `!=`、`<` `<=` `>` `>=`、`and` / `or` / `not`、リテラル、`[ ]`、`{ }`、`length`、`keys`、`key`、`has`、`del`、`to_entries` / `from_entries` / `with_entries`、`map` / `map_values`、`sort_by` / `sort`、`path`、`as $x` / `$x`、`env` / `strenv`、`tag`、`style`、`line_comment` / `head_comment` / `foot_comment` / `comments`、`test`、`document_index` / `di`、`file_index` / `fi` / `filename`、`parent`、`explode`、`anchor` / `alias`、`min` / `max`、`any` / `all`、`set_path` / `del_paths`、`kind`、`line` / `column`、日時の加減算と比較（RFC3339）

未実装（Phase 2 以降）の演算子も、式の構文としては解釈されます（`validate` や `compile` は成功します）が、**実行すると `Error: unknown operator ...` で終了します**。文字列補間 `\(exp)` も Phase 2 です。未実装の一覧は次節を参照してください。

---
[toTop](#toreadme)
## Go 版 yq との違い

yaqpy は Go 版 yq（v4.53.6）の**独立した再実装**です。

| 分類 | 内容 |
|---|---|
| 追加した機能 | TOON 形式の入出力、Python ライブラリ API、デスクトップ GUI |
| **未実装の演算子** | `join` `split` `sub` `match` `capture` `trim` `upcase` `downcase` `to_string` `to_number` `unique` `unique_by` `group_by` `reverse` `shuffle` `sort_keys` `flatten` `first` `pick` `omit` `with` `reduce` `pivot` `contains` `filter` `eval` `error` `envsubst` `encode` / `decode`（`@base64` など）`load` `load_str` `split_doc` `system` と、日時の `now` `tz` `from_unix` `to_unix` `format_datetime` `with_dtf`。式としては解釈されますが、実行すると `Error: unknown operator ...` で終了します |
| 未対応のフォーマット | CSV / TSV / XML / TOML など、Go 版にあるその他の形式。properties は入力不可 |
| 未対応のオプション | `-s`（`--split-exp`）、`-f`（`--front-matter`）、`-C`（色付き出力）。文字列補間 `\(...)` |
| その他 | 日時は RFC3339 形式のみ。Python 3.13 以上が必要 |

**互換性テスト**：Go 版のテストシナリオ 1,091 件を互換テストにしています。実装済みの機能に当たる 841 件のうち 837 件が一致します（残り 4 件は既知の差異）。

**安全側の既定**：ライブラリとして使うときは、ファイル読み込み（`load` など）・環境変数（`env` / `strenv`）・外部コマンド（`system`）の各演算子が**すべて無効**です。CLI は Go 版と同じく、環境変数とファイル読み込みが有効です（外部コマンドは無効）。

> 現状、`env` / `strenv` だけが「許可されていなければ拒否」の検査を実装しています。`load` `load_str` `system` は演算子自体が未実装です。

---
[toTop](#toreadme)
