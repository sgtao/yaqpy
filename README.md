# yaqpy

YAML / JSON をコマンドや Python から、**式で取り出し・更新・変換**するための軽量ツールです。
- 人気の CLI ツール [mikefarah/yq](https://github.com/mikefarah/yq)（Go 版 v4.53.6）の式言語を模倣
- **Python の標準ライブラリだけ**で再実装してます

```console
$ yaqpy '.server.port' config.yaml
8080
$ yaqpy -i '.server.port = 9090' config.yaml     # コメントや並び順はそのまま
```

## 概要

- **書式を壊さない**：コメント、キーの並び順、アンカー（`&` / `*`）、数値やクォートの元の書き方（`0x1F`、`1.50`、`'yes'`）を保持したまま更新できます
- **依存ライブラリなし**：実行に必要なのは Python 3.13 以上だけです（GUI を使うときだけ任意で Flet を追加）
- **3 通りの使い方**：コマンド（`yaqpy`）／ Python ライブラリ（`import yaqpy`）／ デスクトップ GUI（`yaqpy-gui`）
- **対応フォーマット**：

  | 形式 | 入力 | 出力 |
  |---|:-:|:-:|
  | YAML | ○ | ○ |
  | JSON | ○ | ○ |
  | XML | ○ | ○ |
  | CSV / TSV | ○ | ○ |
  | TOML（読むときコメントは保持しない。`-i` は既定で拒否） | ○ | ○ |
  | properties | ○ | ○ |
  | TOON（LLM に渡すためトークン数を減らす形式。Go 版にない拡張） | ○ | ○ |

- **入力形式の自動判定**（Go 版にない拡張）：拡張子で決まらないとき（標準入力、拡張子なし・未知の拡張子のファイル、貼り付けたテキスト）は、中身を見て `json` `xml` `toml` `props` `csv` `tsv` を見分けます（見分けられなければ、これまでどおり YAML）。拡張子が分かるときの挙動は変わりません。ライブラリでは `yaqpy.detect_format(text)`
- **スキーマの出力**（Go 版にない拡張）：`yaqpy --schema data.yaml` で、データを表す JSON Schema（Draft 2020-12）を JSON でも YAML でも出せます
- **変換レシピ**（Go 版にない拡張）：`yaqpy --recipe openai-to-gemini request.json` で、OpenAI・Gemini・Anthropic の**リクエストボディを相互に変換**します。落とした項目・補った項目・変換先のスキーマに合わない箇所を**報告**します（既定では標準出力へ結果を出すだけ。ファイルに書くのは `--apply --out-dir` のときだけ。実際の API は呼びません）。[使い方](USAGE.ja.md#変換レシピapi-のリクエストを別の-api-用にするgo-版にはない拡張)
- **yaqpy が自分を説明する**：`--print-spec`（使える・使えない演算子の一覧）`--example`（実行済みの例）`--guide-prompt`（AI に式を書かせるお願い文）`--skill-md`（Claude Code のスキル）。演算子の一覧は実装から自動生成です

- **Go 版 yq との互換性**：Go 版のテストシナリオ 1,091 件を互換テストにしています（結果を比べられる 1,051 件のうち 1,047 件が一致）。文字列・配列・`@base64` などの encode/decode・日時・`-s`（分割出力）を含め、**`load` 系・`eval`・`envsubst`・`system`・`error` を除く演算子が使えます**（これらは実行すると `Error: unknown operator ...` で終了します）。一覧は [Go 版 yq との違い](USAGE.ja.md#go-版-yq-との違い) を参照してください
- **安全側の既定**：ライブラリとして使うときは、ファイル読み込み・環境変数・外部コマンドの演算子が**すべて無効**です。CLI は Go 版と同じく、環境変数とファイル読み込みが有効です（外部コマンドは無効）

## インストール

Python 3.13 以上が必要です。yaqpy は PyPI には公開していないので、**GitHub のリリース**から入れます。

1. [Releases](https://github.com/sgtao/yaqpy/releases) で、入れたい版を選びます（最新版が一番上です）
2. 次のコマンドの **`0.4.0`（と `v0.4.0`）を、選んだ版の番号に読み替えて**実行します

```bash
# ビルド済みの wheel から入れる（Git は不要）
pip install https://github.com/sgtao/yaqpy/releases/download/v0.4.0/yaqpy-0.4.0-py3-none-any.whl

# GUI も使う場合（Flet が追加されます）
pip install "yaqpy[gui] @ https://github.com/sgtao/yaqpy/releases/download/v0.4.0/yaqpy-0.4.0-py3-none-any.whl"

# コマンドとして入れる場合（uv）
uv tool install "yaqpy[gui] @ https://github.com/sgtao/yaqpy/releases/download/v0.4.0/yaqpy-0.4.0-py3-none-any.whl"
```

Git がある場合は、タグを指定して入れることもできます。

```bash
pip install "yaqpy[gui] @ git+https://github.com/sgtao/yaqpy@v0.4.0"
```

新しい版に更新するときは、新しい版の番号で同じコマンドを実行します。ソースを見たい・改造したい場合は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

## クイックスタート

次の `config.yaml` を例にします。

```yaml
# server settings
server:
  port: 8080 # dev
  hosts: [a, b]
items:
  - {name: pen, price: 120}
  - {name: book, price: 980}
```

**コマンド**

```bash
yaqpy '.server.port' config.yaml                              # 取得 → 8080
yaqpy '.items[] | select(.price > 500) | .name' config.yaml   # 絞り込み → book
yaqpy -i '.server.port = 9090' config.yaml                    # 更新（コメント・並び順はそのまま）
yaqpy -o json '.server' config.yaml                           # 形式変換（yaml / json / xml / csv / tsv / toml / props / toon）
```

**Python ライブラリ**

```python
import yaqpy

yaqpy.evaluate(".server.port", "server:\n  port: 8080\n")        # '8080\n'
yaqpy.query(".items[] | select(.price > 500)", {"items": [{"price": 1}, {"price": 900}]})   # [{'price': 900}]
yaqpy.update(".server.port = 9090", {"server": {"port": 8080}})  # {'server': {'port': 9090}}
```

**GUI**

```bash
yaqpy-gui                # または: yaqpy --gui
```

## ドキュメント

| 内容 | ファイル |
|---|---|
| コマンド・各形式（XML・CSV・TOML・properties・TOON）・スキーマの出力・ライブラリの使い方、対応演算子、Go 版 yq との違い | [USAGE.ja.md](USAGE.ja.md) |
| GUI の使い方（画面の見方、式の書き方、保存・設定・エラー） | [USAGE-GUI.ja.md](USAGE-GUI.ja.md) |
| 開発者向け（セットアップ、設計、テスト、リポジトリ構成） | [DEVELOPMENT.md](DEVELOPMENT.md) |
| 版ごとの変更（できること、既知の制限） | [CHANGELOG.md](CHANGELOG.md) |

## License

[MIT License](LICENSE)

Go 版 yq（MIT）の設計・テストシナリオを参考にしています（[NOTICE](NOTICE)）。

---

🤖 Built with [Claude Code](https://claude.com/claude-code)
