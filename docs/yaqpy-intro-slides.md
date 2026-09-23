---
title: yaqpy 入門｜YAML の設定を、コメントを消さずに一行で書き換える
palette: ocean
purpose: outreach
---
<!-- slide: title, layout: title-xl -->
# 設定ファイルの値を変えたいだけ。<br>==コメントは、消さない。==
subtitle: yaqpy（ヤクピー）— YAML and more, Query editor in Python
badges: [pip install yaqpy, Python 標準ライブラリのみ, コマンド・ライブラリ・GUI]
---
<!-- slide: contrast -->
badge: こんな経験、ありませんか？
## たった 1 か所を直したら、<br>==ファイルの見た目が変わった==
```contrast
example:
  title: Python の PyYAML で YAML を「読んで・直して・書き戻す」と
  rows:
    - tag: 消える
      text: 手書きのコメントが消える（safe_dump はコメントを落とす）
    - tag: 崩れる
      text: 字下げや空行が整えなおされ、差分が大量に出る
    - tag: 面倒
      text: たった 1 行の変更にも、スクリプトを書いて動かす手間がかかる
verdict:
  - { label: 本当にやりたいこと, text: port を 8080 → 9090 に変える、それだけ }
  - { connector: ↓ yaqpy なら }
  - { label: 答え, text: 1 行のコマンドで、ほかは 1 文字も動かさない }
```
point: 出典の調査では、コメントを残すには ruamel.yaml などの別ライブラリが必要と整理されています（sources 参照）
---
<!-- slide: points -->
badge: 30 秒でわかる yaqpy
## yaqpy ＝ ==「式」で取り出し・更新・変換==する道具
lead: YAML・JSON・XML・CSV・TOML などの設定やデータを、短い式で扱えます
- **取り出す**：`yaqpy '.server.port' config.yaml` → `8080`
- **書き換える**：`yaqpy -i '.server.port = 9090' config.yaml`（コメント・並び順はそのまま）
- **変換する**：`yaqpy -o json '.server' config.yaml`（YAML → JSON など）
> 式の言語は、人気の CLI ツール mikefarah/yq（Go 製・GitHub 約 1.6 万スター）を手本にしています
point: 名前は ==Y==AML ==A==nd more, ==Q==uery editor in ==PY==thon の略
---
<!-- slide: diagram-flow -->
badge: しくみ
## 「入力 → 式 → 出力」。<br>これだけ覚えれば使える
lead: 入力の形式は自動で判定。式は yq とほぼ同じ書き方
```diagram
type: flow
nodes: ["データ", "yaqpy", "式", "結果", "保存・共有"]
labels: ["YAML / JSON / XML / CSV / TOML など", "標準ライブラリだけで動く", ".a.b / select / map ...", "画面・標準出力・ファイル", "-i でその場更新も可"]
```
point: 使い方は ==コマンド・Python ライブラリ・GUI（デスクトップ／ブラウザ）== の 4 通り。式はどれも同じ
---
<!-- slide: table -->
badge: 実際の出力
## 同じ YAML から、==欲しい形==で取り出す
lead: examples/sample.yaml（コメント・アンカー付きの設定）に対して、yaqpy v0.7.0 で実行した結果
| やりたいこと | コマンド | 出力 |
|---|---|---|
| 値を取り出す | `yaqpy '.server.port' sample.yaml` | `8080` |
| 絞り込む | `yaqpy '.items[] \| select(.price > 500) \| .name' sample.yaml` | `book` |
| JSON にする | `yaqpy -o json -I 0 '.server' sample.yaml` | `{"port":8080,"hosts":["a","b"],...}` |
| CSV にする | `yaqpy -o csv '.items' sample.yaml` | `name,price` / `pen,120` / `book,980` |
| 更新する | `yaqpy '.server.port = 9090' sample.yaml` | `port: 9090 # 開発用` |
> 最後の行に注目：値だけが変わり、コメント「# 開発用」はそのまま残ります
---
<!-- slide: contrast -->
badge: 最大の特長
## ==書式を壊さない==更新
```contrast
example:
  title: yaqpy '.server.port = 9090' の前後（sample.yaml）
  rows:
    - tag: 残る
      text: コメント（# サーバー設定、# 開発用）とキーの並び順
    - tag: 残る
      text: "アンカー &tls とマージキー <<: *tls（展開されません）"
    - tag: 残る
      text: 数値・引用符の書き方（0x1F、1.50、'yes' など）
verdict:
  - { label: 変わるのは, text: 指定した値だけ }
  - { connector: ↓ だから }
  - { label: 差分は, text: 1 行だけ。レビューも楽で、安心してコミットできる, tone: warn }
```
point: 設定ファイルの更新を ==CI やスクリプトに組み込む==ときに効きます
---
<!-- slide: table -->
badge: 対応フォーマット
## 7 つの形式を、==読んでも書いても==OK
lead: 入力も出力も、標準ライブラリだけで実装しています
| 形式 | 入力 | 出力 | ひとこと |
|:---|:-:|:-:|:---|
| YAML | ○ | ○ | コメント・アンカー・並び順を保持して更新 |
| JSON | ○ | ○ | 1 行（-I 0）にも整形にも |
| XML | ○ | ○ | 属性・コメント・処理命令も往復 |
| CSV / TSV | ○ | ○ | 1 行目をヘッダにして表として扱う |
| TOML | ○ | ○ | コメントは保持しない（-i は既定で拒否） |
| properties | ○ | ○ | Java の設定ファイル形式 |
| TOON | ○ | ○ | LLM 向けにトークンを減らす形式 |
> 拡張子で決まらないとき（標準入力・拡張子なし）は、中身を見て形式を自動判定します（yq にはない拡張）
---
<!-- slide: chart-bar, layout: side-list -->
badge: AI 時代の使いどころ
## LLM に渡すデータを、==半分近く軽く==する
lead: yaqpy は TOON（Token-Oriented Object Notation）を入出力できます。JSON を 100 としたときのトークン数の目安
```chart
type: bar
title: 同じデータのトークン数（JSON = 100）
unit: ""
data:
  - { label: JSON, value: 100 }
  - { label: TOON, value: 57.4 }
source: { name: toon-format/toon ベンチマーク（42.6% 削減を換算）, url: https://github.com/toon-format/toon }
```
### 読み方
- **出典**：TOON の公式ベンチマーク（244 問・4 モデル）で、精度は TOON 72.2%／JSON 71.4%、トークンは 42.6% 減
- **効きやすいデータ**：同じ形の行が並ぶ配列（表のようなデータ）
- **注意**：削減率はデータの形で変わる（公式は 30〜60% 程度の幅と説明）。コメントは TOON では失われる
---
<!-- slide: steps, layout: grid -->
badge: 使い方は 4 通り
## 好きな入口から、==同じ式==で使える
lead: 覚える式は 1 つ。使う場所だけ選べばよい
```steps
style: cards
items:
  - { icon: "⌨️", title: コマンド, desc: "yaqpy '式' ファイル。シェルスクリプトや CI に" }
  - { icon: "🐍", title: Python ライブラリ, desc: "import yaqpy。evaluate / query / update" }
  - { icon: "🖥️", title: デスクトップ GUI, desc: "yaqpy-gui。画面を見ながら試せる" }
  - { icon: "🌐", title: ブラウザ GUI, desc: "yaqpy-web。同じ画面をブラウザで" }
```
point: 初めてなら ==GUI で試す → 式が決まったらコマンドやスクリプトへ==、が一番やさしい流れ
---
<!-- slide: figure -->
badge: GUI
## 開く → 式を書く → ==結果がすぐ右に出る==
![yaqpy の GUI：左に元の YAML、上に式、右に変換結果（CSV）](https://raw.githubusercontent.com/sgtao/yaqpy/main/assets/images/screenshot-yaqpy-gui.png)
source: [yaqpy GUI のスクリーンショット（YAML → CSV）](https://github.com/sgtao/yaqpy)
---
<!-- slide: feature-showcase -->
left:
  eyebrow: GUI
  heading: コマンドが苦手でも、==画面を見ながら==使える。
  lead: 左が原文、右が結果。プルダウンから項目を選ぶだけで式が入るので、式を暗記しなくても始められます。
right:
  num: "01"
  eyebrow: 画面の見どころ
  heading: 3 つの窓と 1 つの欄
  sub: 元のファイルは「上書きする」と答えない限り変わりません
  items:
    - label: プロパティのプルダウン
      desc: 開いた文書の項目一覧から選ぶと、式が自動で入る
    - label: 式の欄
      desc: Enter で実行。書き間違いは実行前に教えてくれる
    - label: 原文と結果の 2 つの窓
      desc: 形式（yaml / json / xml / csv など）と字下げも切り替え可
---
<!-- slide: feature-showcase, layout: reverse -->
left:
  eyebrow: v0.7.0
  heading: ==AI に式を書かせて==、貼り付けて実行。
  lead: 「AIに相談」タブが、データ例とやりたいことから、AI へのお願い文を組み立てます。式は .yaqpy ファイルに保存でき、コマンドからも使えます。
right:
  num: "02"
  eyebrow: GUI の便利機能
  heading: 使うほど楽になる
  sub: 詳しくは USAGE-GUI.ja.md
  items:
    - label: AIに相談タブ
      desc: yaqpy --guide-prompt と同じ内容が土台のお願い文を作る
    - label: 式の保存・読み込み
      desc: "yaqpy sample.yaqpy data.json のようにコマンドでも使える"
    - label: ログ画面（デスクトップ版）
      desc: 成功した変換を記録。見返して、検索して、再実行できる
---
<!-- slide: diagram-flow -->
badge: AI との相性
## yaqpy は、自分の==使い方を説明できる==
lead: 式の書き方を AI に教える手間を、ツール側が引き受けます
```diagram
type: flow
nodes: ["--print-spec", "--example", "--guide-prompt", "--skill-md"]
labels: ["使える／使えない演算子の一覧", "実行済みの例", "AI に式を書かせるお願い文", "Claude Code のスキル"]
```
point: 演算子の一覧は==実装から自動生成==。説明が実際の挙動とずれにくい
---
<!-- slide: table -->
badge: 式の書き方（超入門）
## まずは ==5 つの記号==だけ
lead: yq / jq を触ったことがあれば、そのまま通用します
| 書き方 | 意味 | 例 |
|---|---|---|
| `.` | 全体 | `yaqpy '.' a.yaml` |
| `.キー` | 中身をたどる | `.server.port` |
| `[ ]` | 配列の要素 | `.items[]`（全部）、`.items[0]`（先頭） |
| `\|` | 結果を次に渡す | `.items[] \| .name` |
| `select( 条件 )` | 絞り込む | `select(.price > 500)` |
> 書き換えは `=`：`.server.port = 9090`。「無いとき」の備えは `//`（例：`.a // "既定値"`）
---
<!-- slide: diagram-flow -->
badge: 上級編｜変換レシピ
## OpenAI・Gemini・Anthropic の<br>==リクエストを相互変換==
lead: API のリクエスト本文を、別ベンダー用に組み替え。落とした項目は必ず報告します
```diagram
type: flow
nodes: ["OpenAI 形式", "yaqpy --recipe", "Gemini 形式"]
labels: ["messages / max_tokens など", "変換＋報告（実際の API は呼ばない）", "contents / generationConfig など"]
```
point: 6 種類を同梱：==openai / gemini / anthropic の全組み合わせ（双方向）==
---
<!-- slide: contrast -->
badge: 変換レシピの誠実さ
## 黙って落とさない。==何を捨てたか==を教える
```contrast
example:
  title: yaqpy --recipe openai-to-gemini examples/openai-request.json（実行結果）
  rows:
    - tag: dropped
      text: ".model — Gemini ではモデル名を URL で指定するため、本文には持ち越さない"
    - tag: dropped
      text: ".stream — Gemini は本文の項目ではなく別のエンドポイントでストリームする"
    - tag: dropped
      text: ".messages[].content[type!=text] — 画像・音声・ファイルは変換対象外（テキストのみ）"
verdict:
  - { label: 標準出力, text: 変換後の本文（他のコマンドに渡しても報告は混ざらない） }
  - { connector: ↓ 標準エラー出力に }
  - { label: 報告, text: dropped / added / NOT HANDLED / target schema を出す, tone: warn }
```
point: 既定ではファイルに書きません。書くのは ==--apply --out-dir を付けたときだけ==
---
<!-- slide: diagram-layer -->
badge: もうひとつの便利機能
## データから ==JSON Schema== を作る
lead: yaqpy --schema data.yaml。Draft 2020-12 の JSON Schema を、JSON でも YAML でも出力（yq にはない拡張）
```diagram
type: layer
nodes: [["データ（YAML / JSON など）"], ["型を推論（integer / string / array / object）"], ["必須項目・入れ子を整理"], ["JSON Schema（Draft 2020-12）"]]
```
point: sample.yaml の port は ==type: integer==、hosts は ==array of string== と推論されます
---
<!-- slide: chart-donut -->
badge: 信頼性
## yq の ==1,047 / 1,051 件==と同じ結果
lead: Go 版 yq のテストシナリオ 1,091 件を互換テストにして検証（結果を比べられるのは 1,051 件）
```chart
type: donut
title: 互換テストの内訳（件）
unit: 件
data:
  - { label: yq と一致, value: 1047 }
  - { label: 不一致, value: 4 }
  - { label: 比較対象外, value: 40 }
source: { name: yaqpy README（Go 版 yq v4.53.6 のシナリオ）, url: https://github.com/sgtao/yaqpy }
```
---
<!-- slide: table -->
badge: 正直な比較
## yq（Go 版）との ==使い分け==
lead: yaqpy は yq の代わりではなく、「Python の世界で使える yq 互換」です
| 観点 | mikefarah/yq（Go） | yaqpy |
|---|---|---|
| 実装 | Go の単一バイナリ | Python 3.13+（標準ライブラリのみ） |
| 配布 | パッケージマネージャ／Docker など | `pip` / `uv`（PyPI） |
| 式 | jq 風の式（多数の演算子） | 同じ式。`load` 系・`eval`・`envsubst`・`system`・`error` は未対応 |
| 画面 | なし（CLI） | デスクトップ／ブラウザの GUI つき |
| 独自の拡張 | — | TOON・自動判定・スキーマ・変換レシピ・自己説明 |
> 未対応の演算子を実行すると「Error: unknown operator ...」で終了します（黙って誤動作はしません）
---
<!-- slide: points -->
badge: 安心して使える
## 安全側の既定＝==勝手に外へ触らない==
lead: ファイル読み込み・環境変数・外部コマンドの扱いは、使う場所ごとに決まっています
- **ライブラリ**：ファイル読み込み・環境変数・外部コマンドの演算子は、すべて無効
- **コマンド（CLI）**：Go 版と同じく、環境変数とファイル読み込みが有効（外部コマンドは無効）
- **ブラウザ GUI**：それらは常に無効。既定ではこの PC からしか開けず、認証は無い
- **GUI の保存**：既定は別名保存。上書きするときは、直前に自動でバックアップ（.bak）を作る
> ほかの PC からブラウザ GUI を使うときは、認証がない点に注意（USAGE-GUI.ja.md の 15 章）
point: ==「うっかり」を減らす==側に倒してあります
---
<!-- slide: points -->
badge: こんな人に
## 次のどれかに当てはまるなら、==試す価値あり==
lead: 特に「値を 1 つ変えるだけ」の作業が多い人に
- **Kubernetes・CI・アプリの設定ファイルを触る人**：YAML の 1 項目を、コメントを残して更新したい
- **Python 環境が主で、Go のバイナリを増やしたくない人**：pip / uv で入り、依存もない
- **YAML・JSON・XML・CSV を行き来する人**：形式変換を 1 つの式の書き方に統一したい
- **LLM にデータを渡す人**：TOON で入力トークンを減らしたい／API リクエストを別ベンダー用に変換したい
- **コマンドが苦手な人**：GUI で式を試してから、慣れたらコマンドへ
---
<!-- slide: steps -->
badge: 今すぐ試す
## ==3 ステップ==で、最初の 1 行が動く
lead: Python 3.13 以上があれば、追加の準備は要りません
```steps
style: cards
items:
  - icon: "📦"
    title: 入れる
    desc: pip install yaqpy（または uv tool install yaqpy）
  - icon: "⌨️"
    title: 動かす
    desc: yaqpy '.server.port' config.yaml
  - icon: "✏️"
    title: 書き換える
    desc: yaqpy -i '.server.port = 9090' config.yaml
    tone: outline
```
point: 入れずに試すなら ==uvx yaqpy '.server.port' config.yaml==（uv が必要）。GUI は pip install "yaqpy[gui]" → yaqpy-gui
---
<!-- slide: diagram-timeline -->
badge: 育っています
## 2026 年 9 月に公開、==毎日のように前進==
lead: 初版から v0.7.0 まで、機能を段階的に追加してきました（各版の日付は CHANGELOG より）
```diagram
type: timeline
start: 09-20
milestones:
  - { label: 初版（YAML/JSON・式で取得/更新/変換）, when: v0.1.0 }
  - { label: XML・CSV・TOML・スキーマ出力, when: v0.2.0 }
  - { label: 演算子の拡充（ほぼ全部が使える）, when: v0.3.0 }
  - { label: 変換レシピ・自己説明, when: v0.4.0 }
  - { label: ブラウザ GUI・PyPI 公開, when: v0.6.0 }
  - { label: AIに相談・ログ画面, when: v0.7.0 }
```
point: 詳しい変更点と既知の制限は ==CHANGELOG.md== に版ごとにまとめてあります
---
<!-- slide: table -->
badge: よくある疑問
## 始める前の ==Q&A==
lead: 迷いやすい点を先に片づけておきます
| 疑問 | 答え |
|---|---|
| コメントは消えませんか？ | YAML → YAML の更新では残ります。JSON や TOON に出力すると、それらにコメントが無いため消えます |
| 元のファイルは書き換わりますか？ | コマンドは `-i` を付けたときだけ。GUI は「上書きする」と答えたときだけ（既定は別名保存） |
| 追加のライブラリは要りますか？ | 要りません（Python 3.13 以上のみ）。GUI を使うときだけ Flet を追加します |
| 日本語の資料は？ | README.ja.md／USAGE.ja.md／USAGE-GUI.ja.md があります（詳細ガイドは日本語） |
| yq を使っていても意味はありますか？ | Python 環境で完結させたい・GUI・TOON・変換レシピが欲しいときに向きます |
---
<!-- slide: summary, layout: compact -->
## まとめ｜30 秒後の最初の一歩
1. **課題**：設定ファイルを 1 か所直すだけで、コメントや体裁が壊れる
2. **解決**：yaqpy は「式」で指した値だけを書き換え、==書式はそのまま==。取り出し・更新・変換を 1 つの書き方で
3. **広がり**：コマンド／ライブラリ／GUI／ブラウザ。TOON・スキーマ・変換レシピ・AI 相談まで
4. **最初の一歩**：`pip install yaqpy` → 手元の YAML で `yaqpy '.キー' ファイル.yaml`
> 試したら、GitHub で感想や不具合を伝えてください：github.com/sgtao/yaqpy（MIT License）
---
<!-- slide: sources -->
## 出典・参考リンク
- [yaqpy README（英語）](https://github.com/sgtao/yaqpy/blob/main/README.md) — 概要・特長・インストール・互換テストの数値
- [yaqpy 使い方ガイド USAGE.ja.md](https://github.com/sgtao/yaqpy/blob/main/USAGE.ja.md) — コマンド・各形式・変換レシピ・スキーマ
- [yaqpy GUI 使い方ガイド USAGE-GUI.ja.md](https://github.com/sgtao/yaqpy/blob/main/USAGE-GUI.ja.md) — 画面の見方・Web 版・ログ
- [yaqpy CHANGELOG](https://github.com/sgtao/yaqpy/blob/main/CHANGELOG.md) — 版ごとの変更（日付はここから）
- [mikefarah/yq](https://github.com/mikefarah/yq) — 手本にした Go 製ツール（約 1.6 万スター、YAML/JSON/XML/CSV/TOML/HCL/properties 対応）
- [toon-format/toon](https://github.com/toon-format/toon) — TOON の仕様・ベンチマーク（72.2% vs 71.4%、42.6% 減）
- [How to Edit YAML In Place with yq Without Truncating the File on Failure](https://oneuptime.com/blog/post/2026-09-05-edit-yaml-in-place-safely-yq/view) — 「>」で元ファイルへ書き戻す危険と安全な更新手順
- [YAML in Python: PyYAML, safe_load, and ruamel.yaml](https://kolavistudio.com/yaml-tools/python) — PyYAML はコメントを落とす／ruamel.yaml は保持する、という整理
