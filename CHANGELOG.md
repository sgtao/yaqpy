###### [toREADME](./README.md)
# 変更履歴（CHANGELOG）

---
[toTop](#toreadme)
## [0.4.0] - 未リリース

**スキーマ変換の支援と、コマンド自身による説明の版です。** OpenAI・Gemini・Anthropic の**リクエストボディを相互に変換する「レシピ」**と、その結果を確かめる仕組み（落とした項目の報告・変換先スキーマとの照合・ドライラン）を加えました。あわせて、`--print-spec` `--example` `--guide-prompt` `--skill-md` で、yaqpy が自分の使い方（AI に式を書かせるお願い文、Claude Code のスキル）を出力できるようになりました。本体は引き続き Python の標準ライブラリだけで動きます。使い方は [USAGE.ja.md](USAGE.ja.md#変換レシピapi-のリクエストを別の-api-用にするgo-版にはない拡張) にあります。

### 新しくできること

| 分類 | 機能 |
|---|---|
| **変換レシピ** | `--recipe 名前` で、同梱の 6 つ（`openai-to-gemini` `gemini-to-openai` `openai-to-anthropic` `anthropic-to-openai` `gemini-to-anthropic` `anthropic-to-gemini`）か、自作のレシピ（`--recipe ./my.yaqpy`）を使う。`--list-recipes` `--recipe-test` |
| **確かめる仕組み** | 結果は標準出力へ、**落とした項目（`dropped`）・レシピが知らない項目（`NOT HANDLED`）・補った項目（`added`）・変換先スキーマに合わない箇所（`target schema`）**は標準エラー出力へ。`--report` で詳細（変更のパス単位の差分つき）。**既定ではファイルを書かず**、`--apply --out-dir DIR` のときだけ書く（元のファイルは書き換えない）。複数ファイルは表で報告 |
| **整える** | `prune_null` `prune_empty`（演算子と `--prune-null` `--prune-empty`）：変換で残った `null` や空の入れ物を取り除く |
| **自己説明** | `--print-spec`（式の記法・**使える／使えない演算子の一覧**・形式・レシピ・やってはいけない書き方）、`--example`（別名 `--sample`。実行済みの例）、`--guide-prompt`（別名 `--prompts`。AI へのお願い文）、`--skill-md`（Claude Code のスキル） |
| ライブラリ | `yaqpy.apply_recipe(名前 or Recipe, text)`、`yaqpy.list_recipes()`、`yaqpy.build_recipe(...)`、`RecipeError` |

- **レシピは式のファイル（`.yaqpy`）＋説明のファイル（`.recipe.yaml`）**です。説明には、運ぶ項目（`carries`）・落とす項目と理由（`drops`）・補う項目（`adds`）・目標スキーマ（`target_schema`）・テストケース（`tests`）を書けます。書き間違いのキーはエラーにします
- **変換するのは**、テキストのメッセージ・system の指示・サンプリング設定（`temperature` `top_p` `top_k` 最大トークン数 `stop` `n` `seed` ペナルティ）・関数ツール・`tool_choice`・JSON 出力の指定（OpenAI ⇄ Gemini）です。**変換しないもの**（`model`・画像などテキスト以外・ツール呼び出しの履歴・変換先にない設定）は、**落として報告**します
- **`model` はすべての変換で落とします**（モデル名はベンダーをまたいで通用しません）。変換先で必須なら、目標スキーマとの照合が「不足」と知らせます
- **補うものは 3 つだけです**：Anthropic の `max_tokens`（必須のため、入力になければ **4096**。レシピの既定値であって入力の値ではありません）と、Gemini → OpenAI の `response_format.json_schema.name`（`response`）は**報告します**。`parameters` のない関数の空の `input_schema` は、「引数なし」と同じ意味なので報告しません
- **目標スキーマは各社の公式の定義から書いています**（OpenAI の OpenAPI 定義、Gemini の Discovery ドキュメント、Anthropic のドキュメントと SDK）。参照元は各スキーマファイルの `$comment` にあります。**実際の API は呼びません**
- **レシピは、ファイル・環境変数・外部コマンドに触れません**（同梱のものも、自作のものも。`--security-*` に関係なく常に無効）。説明ファイルの `target_schema` `expression_file` が指せるのも、レシピと同じフォルダのファイルだけです
- 実行例と出力は、実際に実行して確かめたものです。変換の往復（例：OpenAI → Gemini → OpenAI）で、会話・ツール・サンプリング設定が元に戻ることをテストで確かめています

### 変更（挙動が変わるもの）

- **`ascii_upcase` と `ascii_downcase` が使えるようになりました**（後述の「修正」）
- `--help` の末尾に、`schema`・レシピ・自己説明の使用例を加えました
- 新しい引数（`--recipe` など）は、追加だけです。既存の式・フラグの挙動は変わりません

### ライブラリ・開発者向けの変更

- 新しい層 **`yaqpy.recipes`**（データと、プレーンな Python の値への検査。`app` `cli` `gui` `api` を import しない。アーキテクチャ検査に追加）。レシピの実行は `yaqpy.app.recipe_service.RecipeService`（`SecurityPolicy.strict()` で固定）
- `FormatRegistry.guess_from_filename(name)` を追加（拡張子から形式を求め、なければ `None`。`from_filename` はこれを使い、なければ YAML）
- `EvalEnv` などの既存の型は変えていません。`FileSystemPort` も変えていません
- **同梱データ**：`yaqpy/recipes/builtin/`（`*.yaqpy` `*.recipe.yaml` `*.schema.json`）は wheel に含まれます
- 単体テスト 749 → **919**、CLI 受け入れテスト 63 → **73**（stdout/stderr の分離、パイプでの連鎖、`--apply` が入力に触れないこと、SKILL.md を置いて例を実行することを含む）

### 修正

- **`ascii_upcase` と `ascii_downcase` が、変数束縛の `as` の先頭 2 文字として読まれていた**のを修正（字句解析は最長一致ではなく最初に合った規則を取るため）。`as` と `ref` は、後ろに英数字・`_` が続くときは規則にしません。字句解析の全規則の綴りが、その規則で最後まで読まれることを確かめるテストを加えました

### 互換性の見える化

互換テストの結果は v0.3.0 から変わりません（この版は Go 版にない機能の追加が中心で、演算子・形式の互換テストへの影響はありません）。

| | v0.3.0 | v0.4.0 |
|---|---:|---:|
| 演算子シナリオ（1,091 件）で一致 | 1,047 | **1,047**（完全一致 1,016 ＋ 意味的に一致 31） |
| 　未実装の演算子に当たるもの | 28 | 28（`load` `envsubst` `eval`） |
| 　既知の差異 | 4（`shuffle` の並び） | 4 |
| 形式シナリオ（154 件）で一致 | 149 | 149 |

- `prune_null` `prune_empty` `schema` と、レシピ、自己説明は Go 版にないため、互換テストの対象外です

### 既知の制限（この版のもの）

- **レシピはリクエストのみ**です（レスポンスの変換はありません）。**会話の中のツール呼び出しの履歴**（`tool_calls` `tool_use` `functionCall` など）と、**画像・音声・ファイル**は変換せず、落として報告します
- 目標スキーマとの照合は、JSON Schema の完全な検証ではありません（`type` `enum` `const` `required` `properties` `additionalProperties` `items` `minItems` `maxItems` `minimum` `maximum` `anyOf` `oneOf` `allOf`、ローカルの `$ref` だけ）。完全な検証は、のちの版の予定です
- Anthropic のドキュメントは、新しいモデルでは `temperature` が非推奨（1.0 のみ受け付ける）としています。Anthropic 向けの変換結果は、使うモデルで確かめてください
- 自己説明（`--guide-prompt` `--skill-md` など）の文章は日本語です。GUI はレシピに対応していません
- `prune_null` は配列の要素を消しません（`del(.. | select(. == null))` とは違います）
- v0.3.0 までの制限（`load` などの未実装、TOML のコメントは保持されない、など）は変わりません


---
[toTop](#toreadme)
## [0.3.0] - 2026-09-21

**演算子の拡充の版です。** v0.2.0 までは、`join` や `unique` など多くの演算子を実行すると `unknown operator` になりました。この版で、**ファイル・環境変数・外部コマンドに触れるもの（`load` `load_str` `eval` `envsubst` `system`）と `error` を除く、Go 版 yq のすべての演算子**が使えます。本体は引き続き Python の標準ライブラリだけで動きます。各演算子の使い方は [USAGE.ja.md](USAGE.ja.md#演算子) にあります。

### 新しくできること

| 分類 | 演算子・機能 |
|---|---|
| 文字列 | `join` `split` `sub` `match` `capture` `test` `trim` `upcase` `downcase` `to_string` `to_number`、**文字列補間** `"…\(式)…"`（`--string-interpolation=false` で無効に） |
| 配列・マップ | `reverse` `shuffle` `first` `filter` `unique` `unique_by` `group_by` `flatten` `pivot` `pick` `omit` `sort_keys` `with` `reduce` `array_to_map` `contains` |
| encode / decode | `to_json` `to_yaml` `to_xml` `to_props` `to_csv` `to_tsv`、対応する `from_*`、`@json` `@yaml` `@xml` `@props` `@csv` `@tsv`（と `…d`）、`@base64` `@base64d` `@uri` `@urid` `@sh` |
| 日時 | `now` `tz` `from_unix` `to_unix` `format_datetime` `with_dtf`。Go の**時間の書式**（`Monday, 02-Jan-06 at 3:04PM MST` など）を読み書きし、`+=` `-=` `<` `sort_by` も `with_dtf` の書式で動きます |
| 文書の分割 | `split_doc`、**`-s` / `--split-exp` / `--split-exp-file`**（結果ごとに、式で名付けた別のファイルへ書く。`$index` が使えます） |

- **正規表現は Go（RE2）に近づけています**：`$` は文字列の終わりだけに一致（YAML の複数行文字列の末尾の改行に一致しません）、`(?<名前>…)`、`[[:alpha:]]`、置換の `$1` `${名前}`、`match` の `offset` は UTF-8 のバイト数。`\pL` などの Unicode クラスと `(?U)` は、エラーで知らせます
- `tz("Asia/Tokyo")` のような IANA 名には、**OS の時間帯データ**が要ります。Windows では `pip install tzdata` を実行してください（`UTC` と `Local` は不要）。実行時の依存が増えるわけではありません
- `-s` は安全のため、**名前に `..` を含むものを書きません**（Go 版にない制限。名前はデータから決まるため）。`--security-disable-file-ops` を付けると使えず、ライブラリの既定（`SecurityPolicy.strict()`）でも拒否されます
- 空の文字列を `from_yaml` などで読むと `null` になります（Go 版は形式によって `EOF` エラー）
- `from_yaml | … | to_yaml` の往復で、元の文字列に末尾の改行がなければ付けません（Go 版と同じ）
- `first` は、Go 版と同じく、マップに使うと最初の**キー**を返します

### ライブラリ・開発者向けの変更

- `Yq(clock=...)`、`YqService(clock=...)`：`now` と `shuffle` が読む時計を差し替えられます（テスト用）
- `Options.string_interpolation`、`EvaluateRequest.split_expression`
- **`FileSystemPort` に `write_file(path, text)` が加わりました**（`-s` がファイルとディレクトリを作るため）。自作のポート実装は、このメソッドを足してください
- 互換テストのハーネスは、Go のテストと同じく時計を固定して `now` の結果を比べます。形式に依存するシナリオ（`requiresFormat`）も実行します
- `tzdata` を開発用の依存グループ（`dev`）に加えました（IANA 名のテスト用）

### 修正

- `test` 演算子が、`test(正規表現; "g")` のように 2 つ目の引数を受け取れなかったのを修正

### 互換性の見える化

| | v0.2.0 | v0.3.0 |
|---|---:|---:|
| 演算子シナリオ（1,091 件）で一致 | 837 | **1,047** |
| 　未実装の演算子に当たるもの | 228 | **28**（`load` `envsubst` `eval`） |
| 　既知の差異 | 4（文字列補間） | 4（`shuffle` の並び） |
| 　環境や外部コマンドに依存して比べられない | 22 | 12 |
| 形式シナリオ（154 件）で一致 | 146 | **149**（不一致 5 件は TOML のコメント保持） |

- `shuffle` の並びが Go 版と違うのは、Go の乱数列（`math/rand`）を再現しないためです（並べ替えとしては正しい）
- 演算子シナリオの合格率は 99.6%（比べられる 1,051 件のうち 1,047 件）、XML・CSV/TSV・properties の形式シナリオは全件が一致します

### 既知の制限（この版で変わったもの）

- **使えない演算子**：`load` `load_str` `eval` `envsubst` `system` `error`（実行すると `Error: unknown operator ...`）。安全性の設計をしてから入れる予定です
- **未対応のオプション**：`-f`（`--front-matter`）、`-C`（色付き出力）
- 時刻の精度はマイクロ秒（Go はナノ秒）、年は 1〜9999 です
- v0.2.0 までの制限（TOML のコメントは保持されない、CSV の文字コードは UTF-8 のみ、など）は変わりません

---
[toTop](#toreadme)
## [0.2.0] - 2026-09-21

**形式の拡充とスキーマ出力の版です。** XML・CSV / TSV・TOML を読み書きでき、properties も読めるようになりました。あわせて、データから JSON Schema を作る `schema` を加えました。本体は引き続き Python の標準ライブラリだけで動きます。

### 新しくできること

**形式の追加**（詳しい規則は [USAGE.ja.md](USAGE.ja.md) の各節）

| 形式 | 入力 | 出力 | 拡張子・名前 |
|---|:-:|:-:|---|
| XML | ○ | ○ | `.xml` / `-p xml` `-o xml`（別名 `x`） |
| CSV / TSV | ○ | ○ | `.csv` `.tsv` / `csv` `tsv`（別名 `c` `t`） |
| TOML | ○ | ○ | `.toml` / `toml` |
| properties | **○（新）** | ○ | `.properties` / `props` |

- **XML**：Go 版 yq と同じ変換規則（属性 `+@名前`、本文 `+content`、コメント・処理命令・`<!DOCTYPE>` を保持）。宣言された実体は**展開しない**ので、外部実体や Billion laughs の危険がありません。入れ子は 200 段まで。本文と子要素が交互に並ぶ文書は、書き戻すと本文を要素の前にまとめます（単語は残り、前後関係は保たれません。Go 版は本文を落とします）。実在の XML 498 ファイルを往復して、要素・属性・単語が変わらないことを確認しました
- **CSV / TSV**：1 行目がヘッダ、セルは YAML の値として読みます（数値・真偽値・null、`cool: true` のような構造も）。`--csv-auto-parse=false` `--csv-separator` `--tsv-auto-parse=false`
- **TOML**：自前のパーサ（CPython の TOML 適合テスト 62 ファイルを全件クリア）で、**数値の元の書き方（`0xFF`）とインラインテーブル／`[table]` の区別を保ったまま**読み書きします（`pyproject.toml` の値を書き換えても見た目が変わりません）。**コメントは保持されません**。そのため **`-i` は既定で拒否**します（`--toml-allow-lossy` で許可）
- **properties の入力**：`a.b.c = x` を階層に、`pets.0` / `pets[0]`（`--properties-array-brackets`）を配列にします。項目の直前のコメントは項目のコメントになります
- XML・CSV・TOML・properties の Go 版フラグ（`--xml-*` `--csv-*` `--tsv-auto-parse`）は Go 版と同じ名前・既定値です
- 形式は登録するだけで、`-p auto` の拡張子判定と **GUI の形式の選択肢・「開く」ダイアログにも自動で出ます**

**スキーマの出力：`schema`**（Go 版にない拡張）

- `yaqpy --schema data.yaml`、または式の中で `schema`（`.items[] | schema`）。データから **JSON Schema（Draft 2020-12）** を作り、JSON でも YAML でも出せます
- `type`・`properties`・`required`（全サンプルにあるキーだけ）・`items`・`format`（日付・日時）を推論します。`--schema-strict`（`additionalProperties: false`）、`--schema-enum-max N`（`enum` の推定）、`--schema-per-doc`（文書ごと）はオプションです
- 生成したスキーマは元のデータを必ず通します

### GUI の見た目

- 見出し「オリジナル」「変換結果」の横に、**いま採用している形式**（`xml`・`toon` など）を札で表示します。形式バーが `auto` でも指定でも、実際に使う形式名が出ます（エラーのときも消えません）
- 開いたファイルの名前（と「貼り付けたテキスト」）を、ボタンと同じ大きさの**太字**にしました
- 「プロパティ」の行と「式」の行の間を広げました（ラベルが重なって見えないように）

### 修正

- **JSON の `{}`（空のオブジェクト）が `[]`（空の配列）になるバグを修正**しました。`{"a": {}}` が `a: []` になっていました（v0.1.0 からの不具合）
- **YAML の出力を go-yaml に合わせました**：`cool: true` のような、プレーンにできない文字列は `'...'`（従来は `"..."`）、複数行の行コメントの 2 行目以降と、フットコメントのあとの空行を落とさない
- properties の出力：コメント付きの項目の前に空行を入れる（Go 版と同じ）。`-r=false` では空白を含む値を `"..."` で囲む

### 互換性の見える化

Go 版の**形式のシナリオ 154 件**（`tests/golden/formats/`）を互換テストに加えました。実行できるもののうち合格したのは次のとおりです（演算子のシナリオ 1,091 件は従来どおり 837 件が一致）。

| 形式 | シナリオ | 合格 | 内訳・不一致の理由 |
|---|---:|---:|---|
| XML | 52 | 51 | 残り 1 件は `from_yaml` 演算子が未実装（v0.3.0 の予定）。書式だけが違うもの 2 件を含みます |
| CSV / TSV | 18 | 18 | すべて完全一致 |
| TOML | 62 | 57 | 残り 5 件は**コメントを保持する**もの（今の版は保持しない） |
| properties | 22 | 20 | 残り 2 件は `from_yaml`・`array_to_map` が未実装 |

`python tools/golden_report.py --formats` で一覧を確認できます。

### 既知の制限（この版で変わったもの）

- **未対応のフォーマット**：INI・HCL・Lua・shell 変数・base64・URI など（CSV / TSV / XML / TOML / properties の入力は使えるようになりました）
- **TOML** のコメントは保持されません（`-i` は既定で拒否）。XML は文字コード宣言（`encoding="ISO-8859-1"` など）があっても UTF-8 として読みます。CSV の文字コードは UTF-8 のみです
- 演算子の未実装は、この版では変わりません（`from_yaml`・`join`・`split` など。v0.3.0 で拡充する予定です）

---
[toTop](#toreadme)
## [0.1.0] - 2026-09-20

**初版です。** YAML / JSON をコマンドや Python から、**式で取り出し・更新・変換**できます。Go 版 [yq](https://github.com/mikefarah/yq)（v4.53.6）の式を手本にし、**Python の標準ライブラリだけ**で実装しています。

インストール方法は [README](README.md#インストール) を参照してください（PyPI には公開していません。GitHub のリリースから入れます）。

### できること

**コマンド（`yaqpy`）**

- 式で値を取り出す：`yaqpy '.server.port' config.yaml`
- 条件で絞り込む：`yaqpy '.items[] | select(.price > 500) | .name' config.yaml`
- 値を更新する（`-i` でファイルをその場で書き換え）：`yaqpy -i '.server.port = 9090' config.yaml`
- 形式を変換する：YAML ⇔ JSON ⇔ TOON、properties への出力（`-o json` など）
- 標準入力・複数ファイル・複数ドキュメントに対応

**書式を壊さない**

更新しても、**コメント、キーの並び順、アンカー（`&` / `*`）、数値やクォートの元の書き方**（`0x1F`、`1.50`、`'yes'`）がそのまま残ります。`-i` は一時ファイルを経由して置き換えるので、途中で失敗しても元のファイルは壊れません。

**Python ライブラリ**

`import yaqpy` で、`evaluate` / `query` / `update` などが使えます。

```python
import yaqpy
yaqpy.evaluate(".server.port", "server:\n  port: 8080\n")   # '8080\n'
```

**デスクトップ GUI（`yaqpy-gui` または `yaqpy --gui`）**

コマンドが苦手でも、画面で試せます。

- ファイルを開く（または貼り付け）と、左に**原文そのまま**、右に**変換結果**が出ます
- **プロパティのプルダウン**から選ぶだけで式が入ります。文字を打つと候補が絞り込まれます
- 式を直接書くこともできます。書き間違いは、**赤枠と位置の表示**でその場で分かります
- 出力形式（YAML / JSON / properties / TOON）、字下げ、整形を選べます
- 結果を**別名で保存**、またはクリップボードにコピーできます。開いたファイルは、確認なしには上書きしません
- 重い処理でも画面は固まらず、`[中止]` で止められます
- 初心者向けの手引き [USAGE-GUI.ja.md](USAGE-GUI.ja.md) を用意しています（式の書き方を含みます）

**TOON 形式の入出力**

LLM に渡すデータのトークン数を減らすための形式 [TOON](https://github.com/toon-format/spec) を読み書きできます（Go 版 yq にはない拡張です）。

### 安心して使うために

- **依存ライブラリなし**：本体の実行に必要なのは Python 3.13 以上だけです（GUI を使うときだけ、任意で Flet を追加します）
- **安全側の既定**：ライブラリとして使うときは、ファイル読み込み・環境変数・外部コマンドの演算子が**すべて無効**です。GUI も、環境変数の読み取りは既定で不許可で、設定画面で許可できます（外部コマンドは GUI では使えません）
- **Go 版 yq との互換性**：Go 版のテストシナリオ 1,091 件を互換テストにしています。実装済みの機能に当たる 841 件のうち 837 件が一致します

### 既知の制限

この版では、次のものは**使えません**。詳しくは [Go 版 yq との違い](USAGE.ja.md#go-版-yq-との違い) を参照してください。

- **未実装の演算子**：`join` `split` `unique` `reverse` `pick` `reduce` `load` など。式としては解釈されますが、実行すると `Error: unknown operator ...` で終了します（GUI では状態バーに同じ内容が出ます）
- **未対応のフォーマット**：CSV / TSV / XML / TOML。properties は出力のみです
- **未対応のオプション**：`-s`（`--split-exp`）、`-f`（`--front-matter`）、`-C`（色付き出力）、文字列補間 `\(...)`
- **GUI**：
  - ファイルのドラッグ＆ドロップには対応していません（貼り付けは使えます）
  - 設定は保存されず、アプリを閉じると既定に戻ります
  - 複数ファイルの同時表示（`eval-all` 相当）はできません
  - 数十 MiB の巨大なファイルでは、読み込み・書き出しの途中で `[中止]` がすぐには効きません
  - 窓を閉じたときの終了は Windows で確認しています（ほかの OS は未確認です）
- **Python 3.13 以上**が必要です

---
[toTop](#toreadme)
