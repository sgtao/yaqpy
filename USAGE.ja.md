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

Go 版と同じです：`-o/-p`（形式）、`-i`、`-n`、`-I`、`-r[=false]`、`-N`、`-e`、`-P`、`-0`、`-M`、`--from-file`、`--expression`、`--header-preprocess`、`-c`、`--yaml-fix-merge-anchor-to-spec`、`--security-disable-env-ops`、`-s` / `--split-exp` / `--split-exp-file`（結果ごとに別のファイルへ。[文書の分割](#文書の分割v030-で追加)）、`--string-interpolation[=false]`（文字列補間の切り替え）など。`-o=j -I=0` のような pflag 風の書き方も受け付けます。yaqpy 独自のフラグは `--toon`（TOON で出力）と `--toon-delimiter {comma,tab,pipe}` です。

- 出力形式は `-o`（`yaml` / `json` / `props` / `toon` / `xml` / `csv` / `tsv` / `toml`）で指定します。**`-p`（入力形式）だけを指定した場合、出力は Go 版との互換のため YAML のまま**です（警告が出ます）
- 入力形式は、ファイルの拡張子（`.yaml` `.yml` `.json` `.toon` `.xml` `.csv` `.tsv` `.properties` `.toml`）から自動判定します。拡張子が不明なとき、および標準入力は YAML として扱います

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
## XML 入出力

Go 版 yq と同じ変換規則で、XML を読み書きします（`.xml` は拡張子で自動判定、`-p xml` / `-o xml`、別名 `x`）。標準ライブラリだけで実装しています。

```bash
# XML → YAML（コメント・属性・処理命令もそのまま出ます）
uv run yaqpy -o yaml '.' examples/sample.xml

# 値を取り出す（スカラーは YAML 出力にすると 1 行ずつ出ます）
uv run yaqpy -o yaml '.shop.item[].name' examples/sample.xml

# XML のまま更新（宣言・コメント・並び順は保たれます）
uv run yaqpy '.shop.item[0].price = "150"' examples/sample.xml

# XML → JSON、YAML → XML
uv run yaqpy -o json -I 0 '.shop.item' examples/sample.xml
uv run yaqpy -o xml '.' examples/sample.yaml
```

```yaml
# 商品一覧
+p_xml: version="1.0" encoding="UTF-8"
shop:
  +@name: stationery
  item:
    - +@id: "1"
      name: pen
      price: "120"
    - +@id: "2"
      name: book
      price: "980"
```

### 変換の規則

| XML | YAML / JSON での形 |
|---|---|
| 要素 `<a>…</a>` | マップのキー `a` |
| 同じ名前の兄弟要素 | 配列（1 つだけなら配列にならない） |
| 属性 `<a x="1">` | `+@x` というキー（接頭辞は `--xml-attribute-prefix`） |
| 属性や子要素と並ぶ本文 | `+content` というキー（名前は `--xml-content-name`）。本文が子要素で分かれると配列 |
| 空の要素 `<a/>` `<a></a>` | `null` |
| 処理命令 `<?xml version="1.0"?>` | `+p_xml` というキー（接頭辞は `--xml-proc-inst-prefix`） |
| `<!DOCTYPE …>` などの指令 | `+directive` というキー（名前は `--xml-directive-name`）。原文のまま保持 |
| コメント `<!-- … -->` | YAML のコメント（先頭・行末・末尾）。XML へ書き戻すと元の位置に戻る |
| 本文の値 | **すべて文字列**（`"4"`、`"true"`）。数値にするには `.shop.item[].price |= to_number`（または `.shop.item[].price tag = "!!int"` のようにタグを付け替え）とします |
| CDATA | 中身がそのまま文字列になる |

### XML のフラグ

Go 版と同じ名前・既定値です：`--xml-attribute-prefix`（`+@`）、`--xml-content-name`（`+content`）、`--xml-proc-inst-prefix`（`+p_`）、`--xml-directive-name`（`+directive`）、`--xml-keep-namespace`（既定 true）、`--xml-raw-token`（既定 true。false にすると名前空間 URL に置き換える）、`--xml-strict-mode`（厳密な構文検査）、`--xml-skip-proc-inst`、`--xml-skip-directives`。字下げ幅は `-I`（既定 2）。ライブラリでは `Options(xml=XmlOptions(...))` で渡します。

### 読み方と安全性

- **寛容に読みます**（Go 版の `encoding/xml` と同じ）：閉じタグの不一致や、閉じていない要素があってもエラーにしません。ファイルの先頭に要素の外の文字があるとエラーです
- **実体は展開しません**：`<!ENTITY …>` で宣言された実体（`&name;`）は文字列のまま残り、出力では `&amp;name;` になります。外部実体（`SYSTEM`）やパラメータ実体を読みに行くこともなく、ネットワークやファイルへのアクセスは起きません。実体を膨らませて資源を使い切る攻撃（Billion laughs）も成立しません。使えるのは `&lt;` `&gt;` `&amp;` `&apos;` `&quot;` と数値参照（`&#65;`）だけです
- 要素の入れ子は **200 段まで**（`Limits.max_depth` がそれより小さければそちら）、入力は `Limits.max_input_bytes` までです。超えるとエラーになります
- 出力は要素名・属性名に空白や `<` `>` `=` `/` などが含まれると、壊れた XML を出す代わりにエラーにします（Go 版は出力してしまいます）

### Go 版との違い・注意

- スカラー 1 つだけを XML で出力すると、Go 版と同じく**末尾の改行が付きません**（`-o yaml` で取り出すと 1 行ずつ出ます）
- XML の入力は UTF-8 として読みます。`encoding="ISO-8859-1"` などの宣言があっても文字コードの変換はしません（Go 版は変換します）
- 出力できるのは**マップ**（と、その中の配列・スカラー）だけです。トップが配列だと `cannot encode !!seq to XML - only maps can be encoded` になります
- **混在コンテンツ**（`<a>Hello <b>bold</b> world</a>` のように、本文と子要素が交互に並ぶもの）は、本文が `+content` の配列にまとまります。XML に書き戻すときは本文を空白で区切って要素の前にまとめて書くので、**単語は残りますが、子要素との前後関係は保たれません**（Go 版は本文を書かずに落とします）
- 互換テスト：Go 版の XML シナリオ 52 件がすべて合格です。ネストした配列を `-I 4` で YAML にしたときの字下げなど、**書式だけが異なる**（値は同じ）ものが 2 件あります

---
[toTop](#toreadme)
## CSV / TSV 入出力

Go 版 yq と同じ規則で、CSV と TSV を読み書きします（`.csv` `.tsv` は拡張子で自動判定、`-p csv` / `-o csv`、別名 `c`、TSV は `tsv` / `t`）。

```bash
# CSV → YAML（1 行目がヘッダ。各行が 1 つのマップになり、全体は配列）
uv run yaqpy -o yaml '.' examples/sample.csv

# 絞り込んで CSV のまま出力（配列にして渡します）
uv run yaqpy '[.[] | select(.price > 200)]' examples/sample.csv

# セルを更新（引用符も自動で付く）
uv run yaqpy '(.[] | select(.name == "pen") | .price) = 130' examples/sample.csv

# YAML の配列 → CSV、CSV → TSV、必要な列だけの表
uv run yaqpy -o csv '.items' examples/sample.yaml
uv run yaqpy -o tsv '.' examples/sample.csv
uv run yaqpy -o csv '[.[] | [.name, .price]]' examples/sample.csv
```

```yaml
- name: pen
  price: 120
  in_stock: true
- name: book
  price: 980
  in_stock: false
- name: note, A4
  price: 250
  in_stock: true
```

### 読み方

- **セルは YAML の値として読みます**：`120` は数値、`true` は真偽値、`null` と空のセルは null、`cool: true` や `[a, b]` はマップや配列になります（セルの中に構造を持たせられます）
- `--csv-auto-parse=false`（TSV は `--tsv-auto-parse=false`）にすると、マップ・配列にはせず文字列のままにします（数値・真偽値・null の読み取りは変わりません）
- 区切り文字は `--csv-separator ';'`（1 文字。`\t` などの書き方も可）。TSV の区切りはタブ固定です
- 引用符（`"..."`、`""` でエスケープ、セル内の改行）は Go 版の `encoding/csv` と同じ規則です。行ごとの列数が違うとき（`record on line 3: wrong number of fields`）、引用符が壊れているときはエラーです。空行は読み飛ばし、UTF-8 の BOM は無視します
- 文字コードは UTF-8 のみです（Excel の cp932 / Shift_JIS は、UTF-8 に変換してから読んでください）

### 書き方

| 渡すデータ | 出力 |
|---|---|
| スカラーの配列 `[a, b, c]` | 1 行 |
| マップの配列 | ヘッダ行＋各行。**ヘッダは最初のマップのキー**、ほかのマップにないキーは空のセルになり、最初のマップにないキーは出ません |
| 配列の配列 | ヘッダなしの表 |
| スカラー | その値と改行 |
| マップ・入れ子の配列など | エラー（`csv encoding only works for arrays ...`）。黙って壊れた CSV を出しません |

引用符が付くのは、区切り文字・`"`・改行を含むセル、先頭が空白のセルです（Go 版と同じ）。

---
[toTop](#toreadme)
## properties 入出力

Java の `.properties` を読み書きします（`.properties` は拡張子で自動判定、`-p props` / `-o props`、別名 `p` / `properties`）。読み取りは Go 版 yq と同じ規則です。

```bash
# properties → YAML（キーの「.」が階層に、数字が配列の添字になる。コメントは項目に付く）
uv run yaqpy -o yaml '.' examples/sample.properties

# properties のまま更新（コメント・空行も保たれます）
uv run yaqpy '.db.port = "6543"' examples/sample.properties

# YAML → properties
uv run yaqpy -o props '.server' examples/sample.yaml
```

```yaml
db:
  # データベース
  host: localhost
  port: "5432"
features:
  # 機能フラグ
  - search
  - export
```

- 書式は `key = value`、`key: value`、`key value`。`#` と `!` で始まる行はコメント、行末の `\` で次の行に続けられます。`\t` `\n` `\uXXXX` などのエスケープを解釈します
- `a.b.c` は入れ子のマップ、`pets.0` `pets.1` のように**数字の部分があると配列**になります（`--properties-array-brackets` を付けると `pets[0]` の書き方で読み書きします）。途中の穴は null で埋めます
- 値はすべて**文字列**です（`port: "5432"`）。数値にするには `tag = "!!int"` でタグを付け替えます。`${name}` は展開しません
- 項目の直前のコメントは、その項目（マップならキー、配列なら要素）のコメントになります。項目の後ろに孤立したコメントは捨てます
- 同じキーが複数あると、後の値が使われます。`a = 1` のあとに `a.b = 2` のように、値のある場所に階層を作ろうとするとエラーです
- 配列の添字は 100000 まで、キーの階層は 200 段までです（巨大な配列や深い入れ子を作らせないための上限）
- 出力は、コメント付きの項目の前に空行を 1 つ入れます（Go 版と同じ）。`-r=false` を付けると、空白を含む値を `"..."` で囲みます。区切りは `--properties-separator`（既定 ` = `）

---
[toTop](#toreadme)
## TOML 入出力

TOML 1.0 を読み書きします（`.toml` は拡張子で自動判定、`-p toml` / `-o toml`）。`pyproject.toml` のような設定ファイルの値を書き換える用途を想定しています。

```bash
# TOML → YAML
uv run yaqpy -o yaml '.' examples/sample.toml

# 値の取得
uv run yaqpy '.project.version' examples/sample.toml

# TOML のまま更新（標準出力へ。書式・並び順・インラインテーブルはそのまま）
uv run yaqpy '.project.version = "0.2.0"' examples/sample.toml > new.toml

# YAML → TOML
uv run yaqpy -o toml '.' examples/sample.yaml
```

```toml
[project]
name = "demo"
version = "0.2.0"
authors = [{ name = "Ann", email = "ann@example.com" }]
license = { file = "LICENSE" }

[tool.build]
retries = 3
mask = 0xFF

[[tool.hooks]]
name = "lint"
[[tool.hooks]]
name = "test"
```

### 読み方

- 標準の `tomllib` ではなく**自前のパーサ**で読みます（`tomllib` は `0xFF` を `255` にし、インラインテーブルと `[table]` を区別できないため）
- **数値・日時・真偽値は原文のまま**保持します（`0xDEADBEEF`、`1_000`、`6.626e-34`、`1979-05-27T07:32:00-08:00`）。`.A += 1` を `0xDEADBEEF` に行うと `0xDEADBEF0` になります
- **表の種類を覚えています**：`{ a = 1 }`（インラインテーブル）と `[table]`、`[[array.of.tables]]` は、TOML に書き戻すと元と同じ形になります
- 空の入力・コメントだけの入力は、文書がないものとして何も出力しません
- 構文エラーは行と桁つきで報告します（`unterminated basic string (line 1, column 5)`）。同じキーの重複、テーブルの再定義、`01` のような先頭のゼロ、末尾カンマのあるインラインテーブルなど、TOML 1.0 に反するものはエラーです
- 入れ子（配列・インラインテーブル・テーブル名の深さ）は 200 段までです

### 書き方

- 値を先に、そのあとに `[テーブル]` と `[[テーブルの配列]]` を書きます（TOML の規則上、値をテーブルの後ろに置けないため）。YAML のフロー形式のマップ（`{a: 1}`）は、インラインテーブルにはせずテーブルとして書きます
- キーは英数字と `_` `-` だけなら裸のキー、それ以外（空白・`.`・日本語など）は `"..."` で囲みます。文字列は常に `"..."` で、制御文字は `\uXXXX` にするので、出力は必ず有効な TOML です
- `null` は TOML にないため、トップや表の中の値としては書かず、配列の中では `""` にします
- YAML の行末コメント（`port: 8080 # 開発用`）と、キーの前のコメントは TOML のコメントとして書きます
- トップがマップでないもの（配列など）はエラーです。スカラーは値だけを出します

### コメントと `-i`（その場更新）

**TOML を読むとき、コメントは保持されません**（今の版では読み飛ばします）。そのため、**`-i` で TOML ファイルを書き換えようとすると、既定では拒否します**（ファイルは変更されません）。

```text
Error: refusing to update a TOML file in place: its comments are not kept, so the file would lose them. ...
```

- 結果を別のファイルに書く（`> new.toml`）のが安全です
- コメントを失ってもよいと分かっているときだけ `--toml-allow-lossy` を付けると `-i` が使えます
- Go 版 yq はコメントを保つので、TOML のコメント保持は今後の課題です（互換テストで実際に不一致になるのは、コメントを保つ 5 件だけです）

### Go 版との違い

- 互換テスト：Go 版の TOML シナリオ 62 件のうち 57 件が合格（91.9%）。残る 5 件はいずれもコメントの保持に関するものです。エラー文言は Go 版と同じ内容に位置（行・桁）を加えています
- 日時はすべて原文のまま扱い、`!!timestamp` にします（時刻だけの値は文字列）。Go 版は、オフセット付きの RFC 3339 と日付だけ以外（オフセットのないローカル日時 `1979-05-27T07:32:00` など）をエラーにしますが、yaqpy は読めます
- 文字列の出力は TOML の規則に従います（Go 版は `%q` で、TOML にないエスケープを書くことがあります）

---
[toTop](#toreadme)
## スキーマの出力：`schema`（Go 版にはない拡張）

データを見て、それを表す **JSON Schema（Draft 2020-12）** を出力します。相手から受け取った JSON / YAML の形をすぐ把握したいとき、API のリクエストボディの型を確かめたいときなどに使います。

```bash
# 演算子として（式の途中にも置けます）
uv run yaqpy 'schema' examples/sample.yaml            # 入力と同じ形式（YAML）で出力
uv run yaqpy -o json 'schema' examples/sample.yaml    # JSON Schema を JSON で
uv run yaqpy '.items[] | schema' examples/sample.yaml # items の各要素を 1 つにまとめた形

# 短縮形：--schema は式 'schema' の意味（式があれば '<式> | schema'）
uv run yaqpy --schema examples/sample.yaml
```

```yaml
$schema: https://json-schema.org/draft/2020-12/schema
type: object
properties:
  server:
    type: object
    properties:
      port:
        type: integer
      hosts:
        type: array
        items:
          type: string
      tls:
        type: object
        properties:
          enabled:
            type: boolean
          cert:
            type: string
        required:
          - enabled
          - cert
    required:
      - port
      - hosts
      - tls
  # …（backup と items は省略）
required:
  - server
  - backup
  - items
```

- JSON でも YAML でも（TOML など他の形式でも）出力でき、同じ内容です。入力が YAML・JSON・XML・CSV・TOML のどれでも使えます。出力形式は入力と同じか `-o` で指定します
- 結果は通常のノードなので、`schema | .properties | keys` のようにさらに加工できます

### 推論するもの

| キーワード | 内容 |
|---|---|
| `type` | `string` `integer` `number` `boolean` `null` `object` `array`。整数と小数が混ざれば `number`。**型が混ざれば配列**（`type: [string, "null"]`）。日付・バイナリは `string` |
| `properties` | オブジェクトのキーごとの型。キーが最初に現れた順 |
| `required` | **すべてのサンプルに現れたキーだけ**。1 つでも欠けたキーは入りません |
| `items` | 配列の要素すべてをまとめた型。要素が複数のオブジェクトなら、キーの和集合になり、`required` は共通のキーだけ。空の配列は `items` を書きません |
| `format` | 文字列サンプルがすべて日時なら `date-time`、すべて日付なら `date` |
| `additionalProperties: false` | `--schema-strict` を付けたときだけ。既定は書かない（開いたまま） |
| `enum` | `--schema-enum-max N` を付けたときだけ。**文字列だけ**の項目で、値の種類が N 以下で、**同じ値が繰り返し出るとき**。全部違う値の列は自由な文章とみなして `enum` にしません |

- アンカー・エイリアス・マージキー（`<<: *a`）は、コピーの上で展開してから調べます。`<<` がプロパティとして出ることはなく、元のデータは変わりません
- 推測はサンプルに見えたことだけです（1 つしかない値から範囲や長さは推測しません）。生成したスキーマは、元のデータを必ず通します（テストで確認しています）

### 複数の文書・要素

- `schema` は、受け取ったノードすべてを **1 つのスキーマにまとめます**（`.items[] | schema` は各要素をまとめた形）
- 複数ドキュメントのファイルは、通常の `eval` では**文書ごとに** 1 つずつ出力します。**全文書を 1 つにまとめる**には `ea`（eval-all）を使います：`uv run yaqpy ea schema multi.yaml`
- `--schema-per-doc` を付けると、`ea` でも要素ごとに 1 つずつ出力します

### 制限

- 入れ子が 250 段を超えるデータは、途中で切らずにエラーにします。`Limits(max_steps=..., timeout_seconds=...)` の制限も効きます
- `enum` の推定は、1 か所あたり 200 種類までの値だけを数えます（それを超えると `enum` にしません）

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
## 演算子

Go 版 yq の演算子のうち、**ファイル・環境変数・外部コマンドに触れるもの（`load` `load_str` `eval` `envsubst` `system`）と `error` を除いて**すべて実装しています。この節の例は、実際に実行して結果を確かめたものです（`yaqpy 式 ファイル` の形で、入力は例の下に書いた YAML）。

### 基本

`.`、`.a` / `."a b"` / `.a?` / `.a*`、`.[0]` / `.[]` / `.[1:3]`、`..` / `...`、`|`、`,`、`select`、`=` / `|=`、`+=` / `-=` / `*=`、`+`、`-`、`*`（`*+ *? *d *n *c` を含むディープマージ）、`/`、`%`、`//`、`==` / `!=`、`<` `<=` `>` `>=`、`and` / `or` / `not`、リテラル、`[ ]`、`{ }`、`length`、`keys`、`key`、`has`、`del`、`to_entries` / `from_entries` / `with_entries`、`map` / `map_values`、`sort_by` / `sort`、`path`、`as $x` / `$x`、`env` / `strenv`、`tag`、`style`、`line_comment` / `head_comment` / `foot_comment` / `comments`、`document_index` / `di`、`file_index` / `fi` / `filename`、`parent`、`explode`、`anchor` / `alias`、`min` / `max`、`any` / `all`、`set_path` / `del_paths`、`kind`、`line` / `column`、`schema`（Go 版にはない拡張。[スキーマの出力](#スキーマの出力schemago-版にはない拡張)）

### 文字列（v0.3.0 で追加）

| 演算子 | 内容 | 例 → 結果 |
|---|---|---|
| `join(区切り)` | 配列の要素をつないで 1 つの文字列に（`null` は空文字） | `.tags \| join(", ")`（`tags: [a, b, c]`）→ `a, b, c` |
| `split(区切り)` | 文字列を配列に（区切りが空なら 1 文字ずつ。`null` は結果なし） | `.path \| split("/")`（`path: usr/local/bin`）→ `[usr, local, bin]` |
| `sub(正規表現; 置換)` | 一致した部分をすべて置換。置換には `$1` `${1}` `${名前}` `$0` が使えます | `.a \|= sub("([a-z]+)-([0-9]+)", "$2-$1")`（`a: abc-42`）→ `a: 42-abc` |
| `test(正規表現)` | 一致するか（`true` / `false`） | `.[] \| test("^a")`（`[apple, banana]`）→ `true` `false` |
| `match(正規表現)` `match(正規表現; "g")` | `string` `offset` `length` `captures` を持つマップ。`"g"` で一致をすべて | `[match("a"; "g") \| .offset]`（`banana`）→ `[1, 3, 5]` |
| `capture(正規表現)` | 名前付きグループ `(?P<名前>…)` をキーにしたマップ | `capture("(?P<key>[a-z]+)-(?P<num>[0-9]+)")`（`abc-42`）→ `key: abc` `num: "42"` |
| `trim` | 前後の空白を取る | `.a \| trim`（`a: "  hi  "`）→ `hi` |
| `upcase` `downcase` | 大文字・小文字にする | `.a \| upcase`（`a: hello`）→ `HELLO` |
| `to_string` | 文字列にする（数値・真偽値は `"12"` のように引用符付きの文字列、マップや配列は YAML の文字列） | `.a \| to_string`（`a: 12`）→ `"12"`（`-r=false` のとき） |
| `to_number`（`tonumber`） | 文字列を数値にする（`3` → 整数、`3.5` `-1e3` → 小数、`0x1F` も整数）。読めなければエラー | `.[] \| to_number`（`["3", "3.5"]`）→ `3` `3.5` |
| **文字列補間** `"…\(式)…"` | 二重引用符の文字列の中に式の値を埋め込む | `"Hello, \(.name)!"`（`name: World`）→ `Hello, World!` |

- 文字列補間は `--string-interpolation=false` で無効にできます（Go 版と同じフラグ）。`\\(` と書くと補間せず `\(` になります。式の中の `)` は `\)` と書きます。マップや配列の値は、YAML の文字列として入ります
- 2 つの引数は `;` で区切ります。`sub("a", "b")` のように `,` でも動きますが、`match` の `"g"` は `;` のあとに書いたときだけオプションになります（`match("a", "g")` の `"g"` は無視されます。Go 版と同じ）

#### 正規表現：Go（RE2）との違い

yaqpy は Python の `re` を使い、Go 版の正規表現に近づける処理を入れています。

- `$`（`(?m)` なし）と `\z` は**文字列の終わりだけ**に一致します（Python の `$` は末尾の改行の手前にも一致しますが、Go に合わせました。YAML の複数行文字列は末尾に改行が付くので違いが出ます）
- `(?<名前>…)`（Go 1.22 以降）、`[[:alpha:]]` などの POSIX クラス、`\Q…\E`、先頭の `(?i)` `(?m)` `(?s)` が使えます
- `sub` の置換は Go の書き方（`$1` `${名前}` `$$`）です。`\1` は特別な意味を持ちません
- `match` の `offset` と `length` は **UTF-8 のバイト数**です（Go 版と同じ。日本語を含む文字列では文字数と一致しません）
- **使えない**もの：`\pL` `\p{Greek}` などの Unicode クラス、`(?U)`、先頭以外のインラインフラグ（`a(?i)b`）。エラーで知らせます

### 配列・マップ（v0.3.0 で追加）

| 演算子 | 内容 | 例 → 結果 |
|---|---|---|
| `reverse` | 配列を逆順に | `reverse`（`[1, 2, 3]`）→ `[3, 2, 1]` |
| `shuffle` | 配列をランダムに並べ替える | 順序は実行のたびに変わります（[違い](#go-版-yq-との違い)） |
| `first` / `first(条件)` | 先頭の要素 / 条件に合う最初の要素 | `first(. > 7)`（`[7, 8, 9]`）→ `8` |
| `filter(条件)` | 条件に合う要素だけの配列 | `filter(. > 1)`（`[1, 2, 3]`）→ `[2, 3]` |
| `unique` `unique_by(式)` | 重複を取り除く（最初のものを残す） | `unique_by(.n)`（`[{n: a, v: 1}, {n: b, v: 2}, {n: a, v: 3}]`）→ `n: a` と `n: b` の 2 件 |
| `group_by(式)` | 式の値が同じ要素をまとめる（出てきた順） | `group_by(.k)` → `k` ごとの配列の配列 |
| `flatten` `flatten(深さ)` | 入れ子の配列を平らに | `flatten(1)`（`[1, [2, [3]]]`）→ `[1, 2, [3]]` |
| `pivot` | 行と列を入れ替える（配列の配列、またはマップの配列） | `pivot`（`[[1, 2], [3, 4]]`）→ `[[1, 3], [2, 4]]` |
| `pick([キー…])` `omit([キー…])` | 指定したキー（配列なら番号）だけを残す / 取り除く | `pick(["a", "c"])`（`{a: 1, b: 2, c: 3}`）→ `{a: 1, c: 3}` |
| `sort_keys(式)` | マップのキーを並べ替える（式が指すマップを、その場で） | `sort_keys(.)`（`{b: 1, a: 2}`）→ `{a: 2, b: 1}` |
| `with(パス; 更新)` | パスが指す各項目に、更新の式を適用する | `with(.a.b; . = "new")`（`a: {b: old}`）→ `a: {b: new}` |
| `reduce`（`.[] as $x ireduce (初期値; 更新)`） | 畳み込み | `.[] as $x ireduce (0; . + $x)`（`[1, 2, 3, 4]`）→ `10` |
| `array_to_map` | 配列を、番号をキーにしたマップに | `array_to_map`（`[a, b]`）→ `{0: a, 1: b}` |
| `contains(値)` | 文字列・配列・マップが値を含むか | `contains(["b"])`（`[a, b, c]`）→ `true` |

- `first`（引数なし）をマップに使うと、Go 版と同じく**最初のキー**を返します

### encode / decode（v0.3.0 で追加）

| 演算子 | 内容 |
|---|---|
| `to_json` `to_json(インデント)` `@json` | 値を JSON の**文字列**にする（既定の字下げは 2。`to_json(0)` と `@json` は 1 行） |
| `to_yaml` `to_yaml(インデント)` `@yaml` | 値を YAML の文字列に（既定の字下げは 2） |
| `to_xml` `to_xml(インデント)` `@xml` / `to_props` `@props` / `to_csv` `@csv` / `to_tsv` `@tsv` | それぞれの形式の文字列に（CSV・TSV は末尾の改行なし） |
| `from_json` `from_yaml`（`@jsond` `@yamld`）/ `from_xml` `@xmld` / `from_props` `@propsd` / `from_csv` `@csvd` / `from_tsv` `@tsvd` | 文字列を読んで値にする |
| `@base64` `@base64d` | base64 にする / 戻す（`=` の付け忘れは補い、前後の空白と途中の改行は無視） |
| `@uri` `@urid` | URL エンコード（空白は `+`）/ 戻す |
| `@sh` | シェルに安全に渡せる形にする（`it's here` → `it\'s' here'`） |

```bash
uv run yaqpy '.b = (.a | to_json(0))' x.yaml      # a: {c: 1}  →  b: '{"c":1}'
uv run yaqpy '.b = (.a | from_json)' x.yaml       # a: '{"x": 1}'  →  b が {x: 1} のマップに
uv run yaqpy '.a |= (from_yaml | .foo = "cat" | to_yaml)' x.yaml   # 文字列の中の YAML を書き換える
```

- 読み込み（`from_*`）で、元の文字列に末尾の改行がなければ、書き戻し（`to_*`）でも付けません（`from_yaml | … | to_yaml` で往復しても、行が増えません）
- 空の文字列を読むと `null` になります（Go 版は形式によってエラー `EOF` になります）
- `@base64` `@uri` `@sh` は**文字列だけ**を受け取ります（数値などは、先に `@yaml` や `to_string` で文字列にします）

### 日時（v0.3.0 で追加）

| 演算子 | 内容 | 例 → 結果 |
|---|---|---|
| `now` | 現在時刻（RFC 3339）。`!!timestamp` | `now` → `2021-05-19T01:02:03Z` |
| `tz("地域名")` | 別のタイムゾーンにする。IANA 名（`Asia/Tokyo`）、`UTC`、`Local`（この PC の時間帯） | `now \| tz("Asia/Tokyo")` → `2021-05-19T10:02:03+09:00` |
| `from_unix` | UNIX 時間（秒）を日時にする（この PC の時間帯。ミリ秒まで） | `1675301929 \| from_unix \| tz("UTC")` → `2023-02-02T01:38:49Z` |
| `to_unix` | 日時を UNIX 時間（秒）にする | `now \| to_unix` → `1621386123` |
| `format_datetime("書式")` | 日時を書式で文字列にする | `.a \|= format_datetime("Monday, 02-Jan-06 at 3:04PM")` |
| `with_dtf("書式"; 式)` | 式の中の日時演算（`format_datetime` `tz` `to_unix` `+=` `-=` `<` `sort_by`）が、RFC 3339 ではなくこの書式の文字列を読み書きするようにする | `.a \|= with_dtf("02-Jan-2006"; format_datetime("2006-01-02"))` |

- **書式は Go の書き方**です。基準の日時 `Mon Jan 2 15:04:05 MST 2006`（2006 年 1 月 2 日 15 時 4 分 5 秒）を、欲しい形で書きます：`2006-01-02`、`02-Jan-2006`、`Monday, 02-Jan-06 at 3:04PM MST`、`15:04:05.000`。数字の意味は、`2006` 年（`06` は下 2 桁）、`01` `1` `Jan` `January` 月、`02` `2` `_2` 日、`Mon` `Monday` 曜日、`15` 時（24 時間）、`03` `3` 時（12 時間）、`04` 分、`05` 秒、`PM` 午前・午後、`MST` 時間帯の略称、`-0700` `-07:00` `Z07:00` オフセット、`.000` 小数秒
- 加減算の期間は Go の書き方です：`.a += "3h10m"`、`.a -= "1.5h"`（`ns` `us` `ms` `s` `m` `h`）
- `format_datetime` の結果は YAML の値として読み直します（`2006-01-02` の結果は日付、`2` は整数、`Monday` は文字列）
- 時刻は**マイクロ秒**までです（Go はナノ秒）。年は 1〜9999 です
- **`tz("Asia/Tokyo")` のような IANA 名には、OS の時間帯データが要ります。** Windows には標準で入っていないので、`pip install tzdata` を実行してください（多くの macOS・Linux では不要です）。データがないと `unknown time zone Asia/Tokyo (this system has no time zone database; …)` になります。`UTC` と `Local` はデータなしで使えます
- 未知の略称（`AEDT` など）は、Go と同じく**オフセット 0** の時間帯として名前だけ保ちます

### 文書の分割（v0.3.0 で追加）

- **`split_doc`**：一致した節点それぞれを別の文書にして、出力で `---` で区切ります（`.[] | split_doc`）
- **`-s` / `--split-exp`**：結果ごとに、別のファイルに書き出します。ファイル名は式で決めます（式は各結果に対して評価され、`$index` が 0 から数えた通し番号です）

```bash
# 文書ごとに、.a の値をファイル名にして書く（test_doc1.yml と test_doc2.yml ができる）
uv run yaqpy -s '.a' multi.yaml

# 配列の要素ごとに name.yml を作る（区切りの --- なし）
uv run yaqpy -N -s '.name' '.[]' people.yaml

# 通し番号で（part_0.json, part_1.json …）
uv run yaqpy -o json -s '"part_" + $index' multi.yaml

# 式をファイルから（--split-exp-file）
uv run yaqpy --split-exp-file name.yq multi.yaml
```

- 名前に拡張子（`.` のあとの英数字）がなければ、出力形式に合わせて付きます（`yml` `json` `properties` `xml` `toml` `csv` …）。必要なディレクトリは作ります
- 2 つ目以降のファイルは、Go 版と同じく、文書が変わるところで `---` から始まります（`-N` で消せます）
- **`-i` とは同時に使えません**（`write in place cannot be used with split file`）
- **安全のため、名前に `..` を含むものは書きません**（名前はデータから決まるので、文書の中身でツリーの外に書けないようにするためです。Go 版にはない制限です）。`--security-disable-file-ops` を付けると `-s` も使えません。ライブラリ（`SecurityPolicy.strict()`）でも、`allow_file=True` にするまで使えません

### まだ使えないもの

`load` `load_str`（ファイルを読む）、`eval`、`envsubst`、`system`（外部コマンド）、`error` は**実装していません**。式としては解釈されますが、**実行すると `Error: unknown operator ...` で終了します**。ファイル・環境変数・外部コマンドに触れるため、安全性の設計をしてから入れる予定です（改修計画の O3）。
---
[toTop](#toreadme)
## Go 版 yq との違い

yaqpy は Go 版 yq（v4.53.6）の**独立した再実装**です。

| 分類 | 内容 |
|---|---|
| 追加した機能 | TOON 形式の入出力、**`schema` 演算子（JSON Schema の出力）**、Python ライブラリ API、デスクトップ GUI（XML・CSV/TSV・properties・TOML は Go 版にもあり、同じ規則で実装） |
| **未実装の演算子** | `load` `load_str` `eval` `envsubst` `system` `error`。式としては解釈されますが、実行すると `Error: unknown operator ...` で終了します（ファイル・環境変数・外部コマンドに触れるため、安全性の設計をしてから入れる予定です） |
| 未対応のフォーマット | INI・HCL・Lua・shell 変数・KYaml など、Go 版にあるその他の形式（base64・URI・`sh` は形式ではなく演算子 `@base64` `@uri` `@sh` として使えます）。TOML はコメントを保持しない（`-i` は既定で拒否） |
| 未対応のオプション | `-f`（`--front-matter`）、`-C`（色付き出力） |
| 演算子の細かい違い | ① **`shuffle` の並びは Go 版と違います**（Go の乱数列を再現しないため。並べ替えとしては正しい）② 正規表現は Python の `re` を、Go（RE2）に近づけて使っています。`\pL` などの Unicode クラスと `(?U)` は使えません（[正規表現](#正規表現gore2との違い)）③ 空の文字列を `from_*` で読むと、Go 版は形式によって `EOF` エラー、yaqpy は `null` ④ `-s` は名前に `..` を含むものを書きません ⑤ `tz` の IANA 名は OS の時間帯データが要ります（Windows は `pip install tzdata`）⑥ 時刻の精度はマイクロ秒（Go はナノ秒）、年は 1〜9999 |
| その他 | Python 3.13 以上が必要 |

**互換性テスト**：Go 版の演算子のテストシナリオ 1,091 件を互換テストにしています。実行できて結果を比べられる 1,051 件のうち 1,047 件が一致します（99.6%。残り 4 件は `shuffle` の並びの違いで、既知の差異です）。ほかは、未実装の演算子に当たる 28 件（`load` `envsubst` `eval`）と、環境や外部コマンドに依存して比べられない 12 件です。形式（XML・CSV/TSV・TOML・properties）のシナリオ 154 件は、149 件が一致します（不一致 5 件は TOML のコメントを保持するもの）。`schema` は Go 版にないため、互換テストの対象外です。

**安全側の既定**：ライブラリとして使うときは、ファイル読み込み（`load` など）・ファイルへの書き出し（`-s`）・環境変数（`env` / `strenv`）・外部コマンド（`system`）が**すべて無効**です。CLI は Go 版と同じく、環境変数とファイル読み込み・書き出しが有効です（外部コマンドは無効）。

> 現状、`env` / `strenv` と `-s` だけが「許可されていなければ拒否」の検査を実装しています。`load` `load_str` `system` は演算子自体が未実装です。

---
[toTop](#toreadme)
