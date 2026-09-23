###### [toREADME](./README.ja.md)
# yaqpy 使い方ガイド

> 例は、リポジトリを clone した状態（`uv run yaqpy ... examples/sample.yaml`）で書いています。[GitHub のリリースからインストール](README.ja.md#インストール)した場合は、`uv run yaqpy` を `yaqpy` に読み替え、`examples/sample.yaml` は手元の YAML ファイルに置き換えてください。

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

Go 版と同じです：`-o/-p`（形式）、`-i`、`-n`、`-I`、`-r[=false]`、`-N`、`-e`、`-P`、`-0`、`-M`、`--from-file`、`--expression`、`--header-preprocess`、`-c`、`--yaml-fix-merge-anchor-to-spec`、`--security-disable-env-ops`、`-s` / `--split-exp` / `--split-exp-file`（結果ごとに別のファイルへ。[文書の分割](#文書の分割v030-で追加)）、`--string-interpolation[=false]`（文字列補間の切り替え）など。`-o=j -I=0` のような pflag 風の書き方も受け付けます。yaqpy 独自のフラグは、`--toon`（TOON で出力）と `--toon-delimiter {comma,tab,pipe}`、`--schema` 系（[スキーマの出力](#スキーマの出力schemago-版にはない拡張)）、`--prune-null` `--prune-empty`（[結果を整える](#結果を整えるprune_null-と-prune_emptygo-版にはない拡張)）、`--recipe` `--list-recipes` `--recipe-test` `--report` `--apply` `--out-dir`（[変換レシピ](#変換レシピapi-のリクエストを別の-api-用にするgo-版にはない拡張)）、`--print-spec` `--example` `--guide-prompt` `--skill-md`（[yaqpy が自分を説明する](#yaqpy-が自分を説明する--print-spec---example---guide-prompt---skill-md)）です。

- 出力形式は `-o`（`yaml` / `json` / `props` / `toon` / `xml` / `csv` / `tsv` / `toml`）で指定します。**`-p`（入力形式）だけを指定した場合、出力は Go 版との互換のため YAML のまま**です（警告が出ます）
- 入力形式は、ファイルの拡張子（`.yaml` `.yml` `.json` `.toon` `.xml` `.csv` `.tsv` `.properties` `.toml`）から自動判定します。拡張子で決まらないとき（次の節）は、中身を見て判定します

---
[toTop](#toreadme)
## 入力形式の自動判定：拡張子で決まらないときは中身を見る（Go 版にはない拡張）

Go 版 yq は、入力形式をファイルの拡張子だけで決めます（`-p auto`、既定）。拡張子が無い・見覚えがない・標準入力（パイプ）のときは、**Go 版は常に YAML 扱い**にします。yaqpy は、**そのときだけ**中身を見て、形式を推測します。拡張子が分かるときは、これまでどおり拡張子だけで決まります（振る舞いは変わりません）。

```bash
# 拡張子が無いファイル（中身は TOML）
uv run yaqpy -o json -I 0 '.' app_noext
# {"name":"yaqpy","version":"0.4.0"}

# 標準入力（パイプ）。JSON の中身を判定
echo '{"name": "yaqpy", "tags": ["a","b"]}' | uv run yaqpy -o json -I 0 '.'
# {"name":"yaqpy","tags":["a","b"]}
```

- **拡張子が最優先**です。`.json` のファイルは、中身がどう見えても JSON として読みます。中身を見るのは、拡張子が形式を決められなかったとき（拡張子が無い・知らない拡張子・標準入力・貼り付け）だけです
- 見るのは**先頭のごく一部**（コメントを除いた最初の 10 行程度）です。ファイル全体は読みません（巨大な JSON は、形の確認だけに切り替えます）
- 見分けるのは `json` `xml` `toml` `props`（properties）`csv` `tsv` です。**`<` で始まれば XML**、**`{` か `[` で始まり、そのまま JSON として読めれば JSON**、**`[section]` の見出しや、引用符・配列・日付を持つ `key = value` の並びなら TOML**、**素の `key = value` の並びなら properties**、**同じ個数の `,` か `\t` が並ぶ複数行なら CSV/TSV** です
- **一つに決められない、またはどの形式としても読めないときは、これまでどおり YAML 扱い**にします（エラーにはしません）。単純な `key: value` の YAML や配列は、もともと他の形式の見た目に当てはまらないので、そのまま YAML と判定されます
- ライブラリでは `yaqpy.detect_format(text)` が同じ判定をする単体の関数です。ファイル名を持たないテキストの形式を知りたいときに使います（[ライブラリとしての使い方](#ライブラリとしての使い方)）
- GUI では、**貼り付けたテキスト**と、**開くダイアログで選んだ、見覚えのない拡張子（または拡張子なし）のファイル**が、この判定の対象です（[GUI の使い方](#gui-の使い方)）

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
## 結果を整える：`prune_null` と `prune_empty`（Go 版にはない拡張）

別の形に組み立て直すと、入力になかったキーが `null` で残り、空になったまとまりが `{}` で残ることがあります。API に `"temperature": null` や `"generationConfig": {}` を送ると、キーを書かないのとは意味が変わる場合があります。この 2 つが、それを取り除きます。

| 演算子（フラグ） | すること |
|---|---|
| `prune_null`（`--prune-null`） | 値が `null` のマップの項目を消す。**配列の要素は消しません**（ほかの要素の位置が変わるため。`del(.. \| select(. == null))` とは違います） |
| `prune_empty`（`--prune-empty`） | 値が空のマップ・空の配列の項目を、内側から消す（`{a: {b: {}}}` は `{}` になる。いちばん外側は残ります） |

```bash
echo '{"a": null, "b": {"c": null}, "d": 1}' | uv run yaqpy -o json -I 0 --prune-null --prune-empty
# {"d":1}

# 範囲を絞る：.cfg の中だけ整え、ほかは触らない（with は元の文書を返します）
uv run yaqpy -o json 'with(.cfg; prune_null)' body.json
```

> **当てた範囲のすべてに効きます。** JSON Schema の `"default": null` のような「データとしての null」も消えます。API の本文全体にフラグを当てるより、`with(.generationConfig; prune_null)` のように範囲を絞るか、そもそも `null` を作らない書き方にします（同梱のレシピは、そうしています）。

---
[toTop](#toreadme)
## 変換レシピ：API のリクエストを別の API 用にする（Go 版にはない拡張）

**レシピ**は、名前を付けて使い回せる変換です。OpenAI・Gemini・Anthropic の**リクエストボディ**を、相互に変換するものを同梱しています。変換そのものは、これまでの式（`select` や代入）で書けたものです。レシピが足すのは、**その結果を確かめて、何を落としたかを知らせる**仕組みです。

| 名前 | 変換 |
|---|---|
| `openai-to-gemini` / `gemini-to-openai` | OpenAI Chat Completions ⇄ Gemini generateContent |
| `openai-to-anthropic` / `anthropic-to-openai` | OpenAI Chat Completions ⇄ Anthropic Messages |
| `gemini-to-anthropic` / `anthropic-to-gemini` | Gemini generateContent ⇄ Anthropic Messages |

```bash
uv run yaqpy --list-recipes                                       # 一覧
uv run yaqpy --recipe openai-to-gemini examples/openai-request.json
```

変換した本文は**標準出力**へ、報告は**標準エラー出力**へ出ます（`|` でほかのコマンドに渡しても、報告は混ざりません）。

```text
recipe openai-to-gemini: examples/openai-request.json
  dropped .model - Gemini takes the model in the URL of the call (models/{model}:generateContent), and model names do not carry over between vendors
  dropped .stream - Gemini streams by calling streamGenerateContent, not by a field of the body
  dropped .messages[].content[type!=text] - only text parts are converted; images, audio and files are dropped
```

```json
{
  "systemInstruction": {"parts": [{"text": "You are a weather assistant."}]},
  "contents": [
    {"role": "user", "parts": [{"text": "What is the weather in Oslo?"}]},
    {"role": "model", "parts": [{"text": "Let me check."}]},
    {"role": "user", "parts": [{"text": "Thanks."}]}
  ],
  "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512, "stopSequences": ["END"]},
  "tools": [{"functionDeclarations": [{"name": "get_weather", "description": "Get the weather of a city", "parametersJsonSchema": {…}}]}],
  "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}
}
```

（見やすさのために整形・省略しています。実際の出力は、既定のインデントで 1 項目ずつ改行されます。）

- 入力は、拡張子から判定します（`.json` `.yaml` など）。標準入力と、拡張子がないときは、レシピが読む形式（JSON）です。出力は、レシピの形式（JSON）です。`-o yaml` や `-I 0` で変えられます
- **`--recipe` は、`-i` `-n` `-s` `-P` `--schema` `eval-all` `--expression` `--from-file` と一緒には使えません**（エラーになります）。レシピが式の代わりで、引数はすべて入力ファイルだからです

### 何を変換するか

| 内容 | OpenAI | Gemini | Anthropic |
|---|---|---|---|
| system の指示 | `system` / `developer` のメッセージ | `systemInstruction.parts` | `system`（text ブロックの配列） |
| 会話 | `messages`（`user` / `assistant`） | `contents`（`user` / `model`。role がなければ `user`） | `messages`（`user` / `assistant`） |
| 最大トークン数 | `max_completion_tokens`（古い `max_tokens` も読む） | `generationConfig.maxOutputTokens` | `max_tokens`（**必須**） |
| 乱数・確率 | `temperature` `top_p` | `temperature` `topP` `topK` | `temperature` `top_p` `top_k` |
| 停止列 | `stop`（文字列か配列） | `stopSequences` | `stop_sequences` |
| 候補数・乱数の種・ペナルティ | `n` `seed` `frequency_penalty` `presence_penalty` | `candidateCount` `seed` `frequencyPenalty` `presencePenalty` | なし（落として報告） |
| 関数ツール | `tools[].function` | `tools[].functionDeclarations[]`（`parametersJsonSchema`） | `tools[]`（`input_schema`） |
| ツールの選択 | `tool_choice`（`auto` `none` `required`／関数名） | `toolConfig.functionCallingConfig`（`AUTO` `NONE` `ANY`＋`allowedFunctionNames`） | `tool_choice`（`auto` `none` `any` `tool`） |
| 応答の形 | `response_format`（`json_object` `json_schema`） | `responseMimeType` `responseJsonSchema` | 変換しない（落として報告） |
| ストリーム・利用者 | `stream` `user` | （本文にない） | `stream` `metadata.user_id` |

- **1 通のメッセージに、テキストが 1 つだけなら、OpenAI 側の `content` は文字列**にします（多くの互換サーバーが読める形）。複数ならテキストパーツの配列です
- OpenAI ⇄ Anthropic では、`parallel_tool_calls: false` と `tool_choice.disable_parallel_tool_use: true` を対応させます

### 変換しないもの（落として、報告します）

| 落とすもの | 理由 |
|---|---|
| **`model`（すべての変換）** | モデル名はベンダーをまたいで通用しません。変換先で必要なら、目標スキーマとの照合が「不足」と知らせます。Gemini ではモデルは URL（`models/{model}:generateContent`）で指定します |
| 画像・音声・ファイルなど、テキスト以外のパーツ | テキストだけを変換します |
| ツール呼び出しの履歴（`tool_calls` `role: tool` `tool_use` `tool_result` `functionCall` `functionResponse`） | 会話のテキストだけを変換します。**履歴に含まれる場合は、その分が欠けます**（報告に出ます） |
| 変換先にない設定（`n` `seed` `top_k` `parallel_tool_calls` など） | 上の表のとおり |
| 関数ツール以外のツール（Gemini の `googleSearch` など、Anthropic のサーバーツール） | 関数だけを変換します |
| レシピが知らないキー（`reasoning_effort` `thinking` `safetySettings` など） | **「NOT HANDLED」として報告します**（黙って落としません） |

### 補うもの

| 補うもの | 理由 |
|---|---|
| Anthropic への変換で、`max_tokens: 4096` | Messages API は `max_tokens` が必須です。**4096 はレシピの既定値**で、入力の値ではありません（`max_tokens` か `max_completion_tokens` があれば、その値を使います） |
| Gemini → OpenAI で、`response_format.json_schema.name: "response"` | OpenAI は JSON Schema に名前を要求しますが、Gemini には名前がありません |
| `parameters` のない関数に、空の `input_schema`（**報告には出ません**） | Anthropic の `input_schema` は必須です（`{"type": "object", "properties": {}}`）。「引数なし」と同じ意味なので、報告しません |

### 報告の読み方

変換のたびに、次の項目を標準エラー出力へ出します。**何も出なければ、落としたものも補ったものも、目標スキーマとの食い違いもありません**。

| 表示 | 意味 |
|---|---|
| `dropped パス - 理由` | レシピが「運ばない」と宣言している項目が、入力にあった |
| `NOT HANDLED パス` | 入力にあるが、レシピが運ぶとも落とすとも言っていない項目（**書き足すか、利用者が確かめてください**） |
| `added パス = 値 - 理由` | 入力になく、レシピが自分で補った |
| `target schema: パス: …` | 変換結果が、変換先のスキーマに合わない（不足・余分・型・値・範囲・個数） |

`--report` を付けると、変換結果の代わりに、詳しい報告を標準出力へ出します。

```bash
uv run yaqpy --recipe openai-to-anthropic --report examples/openai-request.json
```

```text
Recipe:  openai-to-anthropic (builtin)
Input:   examples/openai-request.json (json)
Output:  json
Verdict: needs a look (see below)

Dropped (the recipe declares that it does not carry these over):
  .model  [.model]  - model names do not carry over between vendors; name the model where you send the request
  .messages[].content[type!=text]  [.messages[1].content[1]]  - only text parts are converted; …

Changes (before -> after). A move is a candidate: the same value at another path. Paths are
compared as they are, so list items are compared by position.
  moved    .messages[0].content -> .system[0].text  ("You are a weather assistant.")
  moved    .max_completion_tokens -> .max_tokens  (512)
  moved    .stop -> .stop_sequences[0]  ("END")
  …
Target schema:
  .model: required, but the result has no such key
```

- **変更（Changes）の `moved`（移動）は「候補」です**：入力から消えた値が、別のパスに現れたときに、その対応を示します。同じ値が複数あるとき（`true` や `"user"` など）は、対応を決められないので、`removed`/`added` のままです
- **パスは、そのまま比べます**。配列を組み替えると、位置ごとの比較になります（値を追えるものは `moved` で示します）
- `--prune-null` `--prune-empty` を付けると、変換結果にも掛けられます（[結果を整える](#結果を整えるprune_null-と-prune_emptygo-版にはない拡張)）

### ファイルにまとめて書く：`--apply --out-dir`

変換した結果をファイルへ書くのは、`--apply` を付けたときだけです。**元のファイルは書き換えません**（`-o` は出力形式なので、書き先は `--out-dir DIR` で指定します）。

```bash
uv run yaqpy --recipe openai-to-gemini --apply --out-dir converted a.json b.json c.json
```

```text
input   result  dropped  not handled  schema issues  output
a.json  ok      3        0            0              converted\a.json
b.json  check   1        1            0              converted\b.json
c.json  error   -        -            -              -
(dropped = declared by the recipe; 'check' = something not handled or not fitting the target schema. Re-run without --apply, or with --report, for the details.)
```

（`c.json` は壊れた JSON で、標準エラー出力に `Error: c.json: bad JSON: Expecting value` が出ます。`b.json` は、レシピが知らない `reasoning_effort` を含むので `check` です。パスの区切りは、Windows では `\` です。）

- ファイル名は入力と同じです（拡張子は出力形式に合わせます）。**入力と同じ場所に書く指定や、別の入力と同じ名前になる指定は、そのファイルだけエラー**にして、元のファイルには触れません
- 1 つのファイルが失敗しても、残りは続けます。終了コードは、失敗があれば 1 です（`check` は 0 です）
- 標準入力（`-`）は、名前がないので使えません

### 目標スキーマとの照合

変換結果が「その API が受け付ける形か」を、レシピに付けた**目標スキーマ**（JSON Schema）と比べます。

- 3 つの API のスキーマは、各社の公式の定義から書いています（OpenAI は OpenAPI 定義、Gemini は Discovery ドキュメント、Anthropic は API ドキュメントと SDK のパラメータ）。**参照元は、各スキーマファイルの `$comment` に書いてあります**
- 比べるのは、キーの有無・余分なキー・型・値の範囲・配列の個数です（`type` `enum` `const` `required` `properties` `additionalProperties` `items` `minItems` `maxItems` `minimum` `maximum` `anyOf` `oneOf` `allOf`、ローカルの `$ref`）。**JSON Schema の完全な検証器ではありません**（`validate` は、のちの版の予定です）
- **実際の API は呼びません**。鍵が要り、課金されるためです。最後の確認は、利用者が行います

### 注意

- **Anthropic への変換**：公式ドキュメントは、新しいモデルでは `temperature` が非推奨（1.0 のみ受け付ける）としています。使うモデルで確かめてください
- **Gemini → 他の API**：`parameters`（OpenAPI 形式のスキーマ）は、型名を小文字にして JSON Schema として渡します。`nullable` のような OpenAPI 固有のキーは変換しません（`parametersJsonSchema` なら、そのまま渡します）
- `allowedFunctionNames` が複数あるとき、OpenAI では `tool_choice: required`、Anthropic では `tool_choice: any` になります（名前の絞り込みは失われます）。1 つのときは、その関数を指定します
- レシピの変換は、**ここに書いた範囲のリクエスト**です。レスポンスの変換は、まだありません

### 自分のレシピを作る

レシピは、**式のファイル**（`.yaqpy`）と、あってもなくてもよい**説明のファイル**（同じ名前の `.recipe.yaml`）です。

```bash
uv run yaqpy --recipe ./my.yaqpy input.json          # 式のファイル。my.recipe.yaml があれば読む
uv run yaqpy --recipe ./my.recipe.yaml input.json    # 説明のファイルだけでもよい（expression: か expression_file: を書く）
uv run yaqpy --recipe ./my.yaqpy --recipe-test       # tests: に書いたケースを実行
```

式のファイルの中身は、ふつうの yaqpy の式です（`#` でコメントが書けます。`--from-file` で読むファイルと同じです）。説明のファイルは YAML で、次のキーが書けます（**書き間違いはエラー**にします。黙って無視しません）。

| キー | 内容 |
|---|---|
| `name` `title` `description` `version` | 名前・題名・説明・版 |
| `input` / `output` | `format`（`json` など。既定は `json`）と `api`（表示用） |
| `carries` | 式が読む入力のパス（`.messages` `.generationConfig.temperature` など） |
| `drops` | 意図して落とす入力のパスと理由（`path:` `reason:`）。入力にあれば `dropped` と報告します |
| `adds` | 式が自分で補う出力のパスと理由。`unless:` に入力のパスを並べると、それが入力にあるときは報告しません |
| `target_schema` | 目標スキーマ（JSON のファイル名か、その場に書いたマッピング） |
| `prune` | `[nulls, empties]`：結果全体に `prune_null` `prune_empty` を掛ける（`null` とは書けません。YAML が「値の null」と読むためです） |
| `tests` | `name` `input` `expected` の一覧。`--recipe-test` で実行 |
| `notes` | 利用者への注意書き |

パスの書き方：`.a.b`（キー）、`.items[]`（配列のすべての要素）、`.parts[type=text]` / `.parts[type!=text]`（マップの要素のうち、その値がある／ない）。**`carries` と `drops` を書くと**、入力にあるそれ以外の項目が `NOT HANDLED` として報告されます。**書かなければ**、その報告は出ません（差分と目標スキーマの照合だけです）。YAML の `[ ]` の中に `[]` を含むパスを書くときは、`".items[]"` のように引用符で囲みます。

#### 式の書き方の規約

同梱のレシピは、次の規約で書いています。**式を誤ると、エラーにならずに結果だけが変わります**。

1. **キーがあるときだけ書く**：`(select($in.temperature != null) | .generationConfig.temperature) = $in.temperature`。`select` は、代入の左辺に置くか、パイプの最後に置きます
2. **`select` の後ろに定数やオブジェクトを続けない**：`(… \| select(条件) \| "値") // 既定` は、条件が偽でも "値" を返します（Go 版 yq と同じ挙動）。ロールの書き換えは、代入で書きます：`(.contents[] \| select(.role == "assistant") \| .role) = "model"`
3. **代入の右辺では、存在しないキーは `null` ではなく「結果なし」になる**：`.tools = [.. \| {"n": .name, "d": .description}]` は、`description` のない要素がまるごと消えます。任意のキーは `pick(["description"])` で足します
4. **代入の右辺の中に、別の代入を入れない**（効きません）
5. **`null` をデータとして持つものは、`prune_null` を全体に掛けない**（ツールの引数スキーマの `"default": null` など）

`yaqpy --print-spec` と `--guide-prompt` は、この規約と、使えない書き方の一覧を出します。

#### 安全性

**レシピは、ファイル・環境変数・外部コマンドに触れません**（同梱のものも、自作のものも同じです）。`--security-disable-*` を付けなくても、`env(…)` などは `env operations have been disabled` で拒否されます。ほかの人のレシピを試すときも、本文の外に何も読まれません。説明ファイルの `target_schema:` `expression_file:` が指せるのは、**レシピと同じフォルダのファイルだけ**です（絶対パスや `..` はエラーにします。説明ファイルを、任意のファイルを読む手段にさせないためです）。

### ライブラリから使う

```python
import yaqpy

run = yaqpy.apply_recipe("openai-to-gemini", body_text)     # 名前か、build_recipe で作った Recipe
run.output                                                  # 変換した本文（テキスト）
run.report.dropped                                          # 落とした項目（declared=False は NOT HANDLED）
run.report.added, run.report.issues, run.report.clean
yaqpy.list_recipes()                                        # 同梱のレシピ
```

ライブラリはファイルを読まないので、レシピは**名前か `Recipe` オブジェクト**で渡します（パスは受け付けません）。

---
[toTop](#toreadme)
## yaqpy が自分を説明する：`--print-spec` `--example` `--guide-prompt` `--skill-md`

AI に yaqpy の式を書かせたいとき、Claude Code などのスキルに登録したいときのために、yaqpy 自身が説明を出します。**どれも「出力して終了」で、ファイルは読みません**。

| フラグ | 出力 |
|---|---|
| `--print-spec` | 式の記法、**使える演算子と使えない演算子の一覧**、形式、レシピ、**やってはいけない書き方**（Markdown） |
| `--example`（別名 `--sample`） | 使用例。入力・コマンド・結果の 3 点セットで、**結果は、出力するときに実際に実行したもの** |
| `--guide-prompt`（別名 `--prompts`） | AI に yaqpy の式を書かせるためのお願い文（記法・演算子・禁止事項・例・答え方） |
| `--skill-md` | Claude Code などの `SKILL.md` としてそのまま置ける文書。ここまでの全機能（形式・`schema`・レシピ・変換）を含みます |

```bash
uv run yaqpy --print-spec > spec.md
uv run yaqpy --skill-md > .claude/skills/yaqpy/SKILL.md      # スキルとして置く
uv run yaqpy --guide-prompt | clip                            # Windows：お願い文をコピー
```

- **登録表から自動生成します**：演算子の一覧は、字句解析の規則表と演算子の登録表から作ります。演算子やレシピを足すと、出力も変わります。**「使えない演算子」の一覧は、実際に `unknown operator` になるものと一致することをテストで確かめています**
- **例は、実行して確かめています**：出力する例と同じものを、自動テストが実行し、期待する結果と一致することを確かめます
- 言語は日本語です（識別子・コマンド・演算子名は原文のままです）。`mdss-convert` の `--guide-prompt` `--print-spec` に相当し、名前の別名は `--sample` `--prompts` です（`mdss-convert` の終了コード 2/3/4 は採りません。成功は 0、引数の誤りは 1 です）

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
- レシピ（[変換レシピ](#ライブラリから使う)）は `yaqpy.apply_recipe("openai-to-gemini", text)`、一覧は `yaqpy.list_recipes()` です。ライブラリはファイルを読まないので、レシピは名前か `Recipe` オブジェクトで渡します
- `yaqpy.detect_format(text)` は、テキストの中身だけから形式を推測します（[入力形式の自動判定](#入力形式の自動判定拡張子で決まらないときは中身を見るgo-版にはない拡張)と同じ判定。ファイル名を持たないテキストの形式を知りたいときに使います）。`Options(input_format="auto")` を渡したときは、`evaluate` 系の呼び出しも同じ判定を自動でします（既定の `input_format="yaml"` は変えていません）

  ```python
  yaqpy.detect_format('{"a": 1}')                 # -> 'json'
  yaqpy.detect_format('name = "x"\n')              # -> 'toml'
  yaqpy.evaluate(".a", '{"a": 5}', options=yaqpy.Options(input_format="auto"))   # -> '5\n'
  ```
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
- **実行時間の保証がありません**：Go の RE2 は入力の長さに比例した時間で終わりますが、Python の `re` は `(a+)+$` のような式と特定の入力の組み合わせで、極端に時間がかかること（バックトラック）があります。1 回の一致の途中では `Limits.timeout_seconds` でも止められません。**他人が書いた式や、信用できない入力に正規表現を使うサービス**（今後の API サービスなど）では、式の長さや入力の大きさを制限してください

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

次の演算子は**実装していません**。式としては解釈されますが、**実行すると `Error: unknown operator ...` で終了します**。ファイル・環境変数・外部コマンドに触れる（`error` を除く）ため、安全性の設計をしてから入れる予定です（改修計画の O3）。

<!-- yaqpy:unimplemented-operators:begin  (yaqpy --print-spec の「使えない演算子」と一致することを、テストで確かめています) -->
`envsubst` `error` `eval` `load` `load_base64` `load_props` `load_str` `load_xml` `str_load` `system` `xml_load`
<!-- yaqpy:unimplemented-operators:end -->

この一覧は、実装から自動生成される `yaqpy --print-spec` の「使えない演算子」と同じです（[yaqpy が自分を説明する](#yaqpy-が自分を説明する--print-spec---example---guide-prompt---skill-md)）。
---
[toTop](#toreadme)
## Go 版 yq との違い

yaqpy は Go 版 yq（v4.53.6）の**独立した再実装**です。

| 分類 | 内容 |
|---|---|
| 追加した機能 | TOON 形式の入出力、**`schema` 演算子（JSON Schema の出力）**、**`prune_null` `prune_empty`**、**変換レシピ（`--recipe`。API のリクエストの相互変換）**、**自己説明（`--print-spec` `--example` `--guide-prompt` `--skill-md`）**、**入力形式の中身での自動判定**（拡張子で決まらないときだけ。Go 版は拡張子のみで、決まらなければ常に YAML）、Python ライブラリ API、デスクトップ GUI（XML・CSV/TSV・properties・TOML は Go 版にもあり、同じ規則で実装） |
| **未実装の演算子** | `load` 系（`load` `load_str` `load_props` `load_xml` `load_base64` など）`eval` `envsubst` `system` `error`（[一覧](#まだ使えないもの)）。式としては解釈されますが、実行すると `Error: unknown operator ...` で終了します（ファイル・環境変数・外部コマンドに触れるため、安全性の設計をしてから入れる予定です） |
| 未対応のフォーマット | INI・HCL・Lua・shell 変数・KYaml など、Go 版にあるその他の形式（base64・URI・`sh` は形式ではなく演算子 `@base64` `@uri` `@sh` として使えます）。TOML はコメントを保持しない（`-i` は既定で拒否） |
| 未対応のオプション | `-f`（`--front-matter`）、`-C`（色付き出力） |
| 演算子の細かい違い | ① **`shuffle` の並びは Go 版と違います**（Go の乱数列を再現しないため。並べ替えとしては正しい）② 正規表現は Python の `re` を、Go（RE2）に近づけて使っています。`\pL` などの Unicode クラスと `(?U)` は使えません（[正規表現](#正規表現gore2との違い)）③ 空の文字列を `from_*` で読むと、Go 版は形式によって `EOF` エラー、yaqpy は `null` ④ `-s` は名前に `..` を含むものを書きません ⑤ `tz` の IANA 名は OS の時間帯データが要ります（Windows は `pip install tzdata`）⑥ 時刻の精度はマイクロ秒（Go はナノ秒）、年は 1〜9999 |
| その他 | Python 3.13 以上が必要 |

**互換性テスト**：Go 版の演算子のテストシナリオ 1,091 件を互換テストにしています。実行できて結果を比べられる 1,051 件のうち 1,047 件が一致します（99.6%。残り 4 件は `shuffle` の並びの違いで、既知の差異です）。ほかは、未実装の演算子に当たる 28 件（`load` `envsubst` `eval`）と、環境や外部コマンドに依存して比べられない 12 件です。形式（XML・CSV/TSV・TOML・properties）のシナリオ 154 件は、149 件が一致します（不一致 5 件は TOML のコメントを保持するもの）。`schema` は Go 版にないため、互換テストの対象外です。

**安全側の既定**：ライブラリとして使うときは、ファイル読み込み（`load` など）・ファイルへの書き出し（`-s`）・環境変数（`env` / `strenv`）・外部コマンド（`system`）が**すべて無効**です。CLI は Go 版と同じく、環境変数とファイル読み込み・書き出しが有効です（外部コマンドは無効）。

> 現状、`env` / `strenv` と `-s` だけが「許可されていなければ拒否」の検査を実装しています。`load` `load_str` `system` は演算子自体が未実装です。

---
[toTop](#toreadme)
