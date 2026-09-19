###### [toREADME](./README.md)
# yaqpy 使い方ガイド

---
[toTop](#totoppage)
## CLI での使い方

### 基本操作

```bash
# 値の取得
uv run yaqpy '.server.port' examples/sample.yaml

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

---
[toTop](#totoppage)
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
[toTop](#totoppage)
## GUI の使い方

デスクトップアプリです（[Flet](https://flet.dev/) 製。`[gui]` extra が必要です）。

```bash
uv sync --extra gui
uv run yaqpy-gui          # 専用コマンド
uv run yaqpy --gui        # CLI のフラグでも起動できます（式・ファイルとは併用できません）
```

flet が入っていない環境で起動すると、導入方法を案内して終了コード 1 で終わります。通常の CLI（`yaqpy '.a' file.yaml`）には影響しません。

### 画面の構成

| 場所 | できること |
|---|---|
| ファイルバー | ファイルを開く／閉じる。**ドラッグ＆ドロップには v1 では対応していません**。何も開いていないときは、左ペインに YAML / JSON を貼り付けても開けます |
| 形式バー | 入力形式・出力形式（`auto` は拡張子で判定）、インデント、整形（`-P`） |
| プロパティ | 開いた文書から作った候補（`.server.port = 8080` など）をプルダウンで選びます。文字を打つと絞り込めます。選ぶと式欄が置き換わってすぐ実行されます。`[＋ 式に追加]` は、いまの式に `\| <候補>` をつなげます |
| 式 | yq の式を直接書きます。打ち終わって 0.3 秒後に構文が検査され、誤りは赤枠と `^` で示されます。Enter か `[▶ 実行]` で実行します。実行中は `[■ 中止]` で止められます |
| 左ペイン | 開いた**原文そのまま**（読み取り専用） |
| 右ペイン | 変換結果。`[💾 保存]` で別名保存、`[📋]` でクリップボードにコピー（どちらも**全量**。表示は上限行数で丸められます） |
| 設定 | セキュリティ（`env` / `load` 演算子の許可）、タイムアウト、最大入力、表示行数の上限、ダークテーマ。**保存はされず、アプリを閉じると既定に戻ります** |

- 保存先が**いま開いているファイルと同じ**なら、上書きしてよいかを確認します（既定は「やめる」）
- `env` などの許可されていない演算子を使うと、状態バーに理由と `[設定を開く]` が出ます。該当の設定を許可すると自動で再実行されます
- `system` 演算子は GUI では使えません

### CLI との対応

| GUI の操作 | 相当する CLI |
|---|---|
| アプリを起動する | `yaqpy --gui`（または `yaqpy-gui`） |
| ファイルを開く | `yaqpy '.' file.yaml` |
| 式に `.server.port` を入れて実行 | `yaqpy '.server.port' file.yaml` |
| 出力形式を json にする | `yaqpy -o json '.' file.yaml` |
| インデントを 4 にする | `yaqpy -I 4 '.' file.yaml` |
| 整形（-P）を ON | `yaqpy -P '.' file.yaml` |
| 結果を別名保存 | `yaqpy '.' file.yaml > out.yaml` |
| 設定で env を許可 | CLI は既定で許可（`--security-disable-env-ops` で不許可）。GUI は既定で**不許可** |

---
[toTop](#totoppage)
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
[toTop](#totoppage)
## 実装済みの演算子（Phase 1 ＝ 38 種）

`.`、`.a` / `."a b"` / `.a?` / `.a*`、`.[0]` / `.[]` / `.[1:3]`、`..` / `...`、`|`、`,`、`select`、`=` / `|=`、`+=` / `-=` / `*=`、`+`、`-`、`*`（`*+ *? *d *n *c` を含むディープマージ）、`/`、`%`、`//`、`==` / `!=`、`<` `<=` `>` `>=`、`and` / `or` / `not`、リテラル、`[ ]`、`{ }`、`length`、`keys`、`key`、`has`、`del`、`to_entries` / `from_entries` / `with_entries`、`map` / `map_values`、`sort_by` / `sort`、`path`、`as $x` / `$x`、`env` / `strenv`、`tag`、`style`、`line_comment` / `head_comment` / `foot_comment` / `comments`、`test`、`document_index` / `di`、`file_index` / `fi` / `filename`、`parent`、`explode`、`anchor` / `alias`、`min` / `max`、`any` / `all`、`set_path` / `del_paths`、`kind`、`line` / `column`、日時の加減算と比較（RFC3339）

未実装（Phase 2 以降）の演算子は式の解析時に `unknown operator` として報告されます。文字列補間 `\(exp)` も Phase 2 です。

---
[toTop](#totoppage)
