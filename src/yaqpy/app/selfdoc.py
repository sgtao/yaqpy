"""The command describing itself: ``--print-spec``, ``--example``, ``--guide-prompt``, ``--skill-md``.

Nothing is typed twice. The operator lists come from the registries (what has a handler is
implemented, the rest is not), the formats from the format registry, the recipes from the recipe
catalog, and the examples are run on the real engine each time they are shown. A test compares the
"not implemented" list with what really answers ``unknown operator``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from yaqpy.app.examples import EXAMPLES, Example, run_example
from yaqpy.app.service import YqService
from yaqpy.core.lang.lex_rules import DEFAULT_RULES
from yaqpy.core.lang.tokens import TokenKind
from yaqpy.core.operators import OperatorRegistry, builtin_registry
from yaqpy.recipes import builtin_recipes

# Operators that yaqpy adds to the Go yq (they are not in its documentation or its tests).
EXTENSION_TYPES = frozenset({"SCHEMA", "PRUNE_NULL", "PRUNE_EMPTY"})

_WORD_PATTERN = re.compile(r"^@?[A-Za-z0-9_?]+$")
_REGEX_SYNTAX = re.compile(r"[\()\[\]{}*+.^$]")     # anything but a plain word, an optional letter and |
# Operators whose rule is written with arguments (``env(NAME)``), so it has no plain word to expand.
_ARGUMENT_RULES = {"EnvOp": "env", "StrEnvOp": "strenv"}


@dataclass(frozen=True, slots=True)
class OperatorInfo:
    type: str
    names: tuple[str, ...]          # the first is the one to write; the rest are aliases
    implemented: bool

    @property
    def name(self) -> str:
        return self.names[0]

    @property
    def extension(self) -> bool:
        return self.type in EXTENSION_TYPES


def _spellings(pattern: str) -> list[str]:
    """The words a plain lexer pattern accepts: ``to_?number|tonum`` -> ``tonumber``, ``to_number``, ...

    Only a pattern made of plain words is expanded (``@yaml`` too); one that needs arguments or
    other regular-expression syntax (a rule for ``to_json(2)``, for ``envsubst(ne)``) is left out.
    """
    if _REGEX_SYNTAX.search(pattern):
        return []
    words: list[str] = []
    for alternative in pattern.split("|"):
        if not _WORD_PATTERN.match(alternative):
            continue
        variants = [""]
        i = 0
        while i < len(alternative):
            char = alternative[i]
            if i + 1 < len(alternative) and alternative[i + 1] == "?":
                variants = [v + s for v in variants for s in ("", char)]
                i += 2
            else:
                variants = [v + char for v in variants]
                i += 1
        words.extend(v for v in variants if v)
    return words


def _preferred(word: str) -> tuple[bool, bool, str]:
    """snake_case first, then lower case, then the rest (``sort_keys`` before ``sortKeys``)."""
    return ("_" not in word and word != word.lower(), word != word.lower(), word)


def _spelling_key(word: str) -> str:
    return word.lower().replace("_", "")


def operator_table(registry: OperatorRegistry | None = None) -> list[OperatorInfo]:
    """Every operator that can be written as a word, from the lexer's rule table, with whether it works.

    One entry per operator name. ``to_number``, ``tonumber`` and ``toNumber`` are one entry (the
    spellings the lexer accepts for it); ``to_json`` and ``to_xml`` are two, although one handler
    serves both.
    """
    registry = registry or builtin_registry()
    found: dict[tuple[str, str], set[str]] = {}
    for rule in DEFAULT_RULES:
        words = _spellings(rule.pattern)
        if rule.name in _ARGUMENT_RULES:
            words = [_ARGUMENT_RULES[rule.name]]
        for word in words:
            try:
                token = rule.action(word, registry.get)      # type: ignore[misc]
            except Exception:   # noqa: BLE001 - a rule that is not an operator is simply skipped
                continue
            operation = token.operation
            if token.kind is not TokenKind.OPERATION or operation is None:
                continue
            if operation.spec.type == "VALUE":
                continue                                    # true, false, null ...
            found.setdefault((operation.spec.type, _spelling_key(word)), set()).add(word)
    table = [OperatorInfo(kind, tuple(sorted(words, key=_preferred)), registry.has_handler(kind))
             for (kind, _), words in found.items()]
    return sorted(table, key=lambda info: info.name.lower().lstrip("@"))


# ----------------------------------------------------------------------------- rules to keep

RULES: tuple[tuple[str, str], ...] = (
    ("jq にあって yaqpy にない書き方は使わない",
     "`if … then … else … end`、`try … catch`、`walk`、`paths`、`limit`、関数の `add`、`reduce`（→ `ireduce`）、"
     "`ltrimstr`、`splits`、`getpath`、`input`、`debug` は `unexpected character` になります。"
     "条件分岐は「代入」か `select` で書き、合計は `.[] as $i ireduce (0; . + $i)` で求めます。"),
    ("`select` の後ろに定数やオブジェクトを続けない",
     "`(.role | select(. == \"assistant\") | \"model\") // .role` は、条件が偽でも \"model\" を返します（Go 版 yq と同じ挙動）。"
     "条件付きの書き換えは代入で書きます：`(.contents[] | select(.role == \"assistant\") | .role) = \"model\"`。"
     "`select` は、パイプの最後に置くか、代入の左辺に置きます。"),
    ("代入の右辺では、存在しないキーは null ではなく「結果なし」になる",
     "`.tools = [.items[] | {\"n\": .name, \"d\": .description}]` は、`description` のない要素がまるごと消えます。"
     "任意のキーは `pick([\"description\"])` で足す（`pick([\"name\"]) + pick([\"description\"])`）か、"
     "代入の右辺の外で組み立てます。"),
    ("代入の右辺の中に、別の代入を入れない",
     "右辺は読み取り専用で評価されるので、その中の `=` `|=` は何も変えません。"),
    ("未実装の演算子を使わない",
     "下の「使えない演算子」を使うと `unknown operator` になります。ファイル・環境変数・外部コマンドを使う演算子（`load` `eval` "
     "`envsubst` `system`）は、意図して未実装です。"),
    ("`prune_null` `prune_empty` は、当てた範囲すべてに効く",
     "JSON Schema の `\"default\": null` のような「データとしての null」も消えます。結果全体ではなく、"
     "`.generationConfig | prune_null` のように範囲を絞るか、そもそも null を作らない書き方にします。"),
    ("答えは必ず実行して確かめる",
     "式を書いたら、実際の入力で `yaqpy '式' 入力ファイル` を実行し、結果を見せます。動作を推測で説明しません。"),
)

FORMAT_NOTES = {
    "yaml": "コメント・キーの順・アンカーを保ちます。既定の形式です。",
    "json": "",
    "props": "出力のみ（入力は `-p props`）。",
    "toon": "LLM 向けの省トークン形式（`--toon` は `-o toon` と同じ）。",
    "xml": "属性は `+@` 、本文は `+content`（`--xml-*` で変更）。外部実体は展開しません。",
    "csv": "1 行目が見出し。`--csv-separator` `--csv-auto-parse`。",
    "tsv": "`--tsv-auto-parse`。",
    "toml": "書き出しではコメントが残りません。`-i` は `--toml-allow-lossy` を付けたときだけ。",
}


# ----------------------------------------------------------------------------- helpers

def _version() -> str:
    from yaqpy import __version__

    return __version__


def _names(infos: list[OperatorInfo]) -> str:
    return " ".join(f"`{info.name}`" for info in infos)


def _operator_sections(table: list[OperatorInfo]) -> list[str]:
    implemented = [i for i in table if i.implemented and not i.extension]
    extensions = [i for i in table if i.implemented and i.extension]
    missing = [i for i in table if not i.implemented]
    lines = [f"### 使える演算子（{len(implemented)} 個。Go 版 yq と同じ名前）", "", _names(implemented), "",
             "多くの名前は、書き方の揺れを許します（`to_number` `tonumber` `toNumber`、`sort_keys` `sortKeys`）。"
             "ここには、いちばん読みやすい書き方を載せています。", "",
             f"### yaqpy 独自の演算子（{len(extensions)} 個。Go 版にはありません）", "", _names(extensions), "",
             f"### 使えない演算子（{len(missing)} 個。書くと `unknown operator` になります）", "",
             _names(missing) if missing else "（なし）", ""]
    return lines


def _format_lines(service: YqService) -> list[str]:
    formats = service.formats
    inputs, outputs = formats.input_formats(), formats.output_formats()
    lines = ["| 形式 | 入力 | 出力 | 補足 |", "|---|:-:|:-:|---|"]
    for name in dict.fromkeys(inputs + outputs):
        lines.append(f"| `{name}` | {'○' if name in inputs else '×'} | {'○' if name in outputs else '×'} "
                     f"| {FORMAT_NOTES.get(name, '')} |")
    return lines


def _recipe_lines() -> list[str]:
    recipes = builtin_recipes()
    if not recipes:
        return ["（同梱のレシピはありません）"]
    lines = ["| 名前 | 内容 |", "|---|---|"]
    lines += [f"| `{r.name}` | {r.title} |" for r in recipes.values()]
    return lines


def _example_block(service: YqService, example: Example, heading: str = "####") -> list[str]:
    output, notes = run_example(service, example)
    lines = [f"{heading} {example.title}", "", "入力（" + example.input_name + "）：", "", "```" + example.input_format,
             example.input.rstrip("\n"), "```", "", "コマンド：", "", "```bash", example.command, "```", "",
             "結果：", "", "```" + (example.output_format if example.output_format != "yaml" else "yaml"),
             output.rstrip("\n"), "```"]
    if notes:
        lines += ["", "標準エラー出力に出る報告（変換で落とした項目など）：", "", "```text"]
        lines += [f"  {note}" for note in notes]
        lines += ["```"]
    return lines + [""]


def _rules_lines() -> list[str]:
    lines: list[str] = []
    for number, (title, body) in enumerate(RULES, start=1):
        lines += [f"{number}. **{title}**  ", f"   {body}"]
    return lines


# ----------------------------------------------------------------------------- the four outputs

SYNTAX_TABLE = r"""| 書き方 | 意味 |
|---|---|
| `.a.b` `.a[0]` `.a[]` `.[]` `..` | 値の取り出し／配列の全要素／再帰的にすべて |
| `.a[1:3]` | 配列の切り出し |
| `A \| B` `A, B` | 前の結果を次へ渡す／2 つの結果を並べる |
| `== != < <= > >=` `and` `or` `not` | 比較と論理 |
| `A // B` | A が null か存在しないとき B |
| `. as $x \| …` | 変数（`$x`）に入れる |
| `.a = 1` `.a \|= . + 1` `.a += 1` | 代入・更新。`(.items[] \| select(.p > 1) \| .name) = "x"` のように「対象を選んで」書き換える |
| `{"a": .b}` `[.c[] \| .d]` | オブジェクト・配列を作る |
| `"…\(.a)…"` | 文字列補間（`--string-interpolation=false` で無効） |
| `# 説明` | コメント（式のファイルの中で使える） |"""

COMMAND_FORMS = """```bash
yaqpy '式' ファイル...                 # 読み取り（標準入力からも読めます）
yaqpy -i '式' ファイル                 # ファイルをその場で更新
yaqpy -o json -I 0 '式' ファイル       # 出力形式（-o）とインデント（-I）
yaqpy eval-all '式' a.yaml b.yaml      # 複数のファイル・文書をまとめて 1 つの入力として扱う
yaqpy --from-file 式.yaqpy ファイル    # 式をファイルから読む
```"""


def render_spec(service: YqService, table: list[OperatorInfo] | None = None) -> str:
    table = table or operator_table(service.operators)
    lines = [f"# yaqpy 式の仕様（yaqpy {_version()}）", "",
             "yaqpy は mikefarah/yq（Go 版 v4）の式を、Python の標準ライブラリだけで実装したものです。"
             "この文書のうち、演算子・形式・レシピの一覧は、実装の登録表から自動生成しています。", "",
             "## 1. コマンドの形", "", COMMAND_FORMS, "", "## 2. 式の記法", "", SYNTAX_TABLE, "",
             "## 3. 演算子", ""]
    lines += _operator_sections(table)
    lines += ["## 4. 入出力の形式", "", *_format_lines(service), "",
              "形式は拡張子から判定します（`-p` で入力、`-o` で出力を指定）。", "",
              "## 5. yaqpy 独自の機能（Go 版にはありません）", "",
              "- `schema`：データの形を JSON Schema（Draft 2020-12）で出す。`yaqpy -o json schema データ`。"
              "`--schema-strict` `--schema-enum-max N` `--schema-per-doc`",
              "- `prune_null` `prune_empty`（`--prune-null` `--prune-empty`）：変換結果の null や空の入れ物を取り除く",
              "- `--recipe 名前|ファイル`：名前を付けた変換（下の「レシピ」）。`--list-recipes` `--recipe-test` "
              "`--report` `--apply --out-dir`",
              "- `--print-spec` `--example` `--guide-prompt` `--skill-md`：この説明を出す", "",
              "## 6. レシピ（API のリクエストボディの変換）", "", *_recipe_lines(), "",
              "使い方：`yaqpy --recipe openai-to-gemini request.json`。変換結果は標準出力へ、落とした項目・補った項目・"
              "変換先のスキーマに合わない箇所は標準エラー出力へ出ます。`--report` で詳細、`--apply --out-dir DIR` で"
              "複数ファイルをまとめて変換（元のファイルは書き換えません）。レシピは、ファイル・環境変数・外部コマンドに触れません。"
              "自分のレシピは `--recipe ./my.yaqpy`（式のファイル。同じ場所の `my.recipe.yaml` が説明・目標スキーマ・テスト）。", "",
              "## 7. 式を書くときの決まり（やってはいけないこと）", "", *_rules_lines(), ""]
    return "\n".join(lines)


def render_examples(service: YqService) -> str:
    lines = [f"# yaqpy の使用例（yaqpy {_version()}）", "",
             "各例の「結果」は、この出力を作るときに実際に実行したものです。", ""]
    for example in EXAMPLES:
        lines += _example_block(service, example, "##")
    return "\n".join(lines)


def _prompt_operator_line(table: list[OperatorInfo]) -> str:
    usable = [i.name for i in table if i.implemented]
    missing = [i.name for i in table if not i.implemented]
    return ("使える演算子：" + " ".join(usable) + "\n使えない演算子（使うと unknown operator）：" + " ".join(missing))


def render_guide_prompt(service: YqService) -> str:
    table = operator_table(service.operators)
    lines = ["# yaqpy の式を書いてください", "",
             "あなたは、コマンド `yaqpy`（mikefarah/yq v4 互換）の式を書くアシスタントです。"
             "YAML・JSON・XML・CSV・TOML などのデータを、読み取り・更新・変換する式を、下の決まりに従って書いてください。", "",
             "## コマンドの形", "", COMMAND_FORMS, "", "## 式の記法", "", SYNTAX_TABLE, "", "## 演算子", "",
             "```text", _prompt_operator_line(table), "```", "",
             "## やってはいけないこと", "", *_rules_lines(), "", "## 例", ""]
    for example in EXAMPLES[:8]:
        lines += _example_block(service, example)
    lines += ["## 答え方", "",
              "1. 式を 1 つのコードブロックで示す（複数行のときは `--from-file` 用に、`#` のコメントを付けてよい）",
              "2. そのまま実行できるコマンドを示す（入力ファイル名は、私が伝えたものを使う）",
              "3. 私の入力例で実行した結果を示す。**実際に実行して確かめた結果だけ**を書く",
              "4. 一致しないときは、式・入力・実際の出力・期待した出力の 4 つを並べて直す",
              "5. うまく書けないときは、使えない機能だとはっきり書く（近い書き方で誤魔化さない）", "",
              "## 依頼", "", "（ここに、入力データの例と、やりたい変換を書いてください）", ""]
    return "\n".join(lines)


SKILL_DESCRIPTION = (
    "YAML・JSON・XML・CSV・TOML・properties の読み取り・更新・変換を、yaqpy（Python 版 yq 互換）で行う。"
    "「yq で」「YAML の値を書き換えて」「JSON を YAML に変換して」「設定ファイルからこの項目を取り出して」"
    "「データの形（JSON Schema）を出して」「OpenAI のリクエストを Gemini（Anthropic）用に変換して」"
    "「yaqpy の式を書いて」などで使う。")


def render_skill_md(service: YqService) -> str:
    table = operator_table(service.operators)
    lines = ["---", "name: yaqpy", f"description: {SKILL_DESCRIPTION}", "---", "",
             "# yaqpy で構造化データを扱う", "",
             f"`yaqpy`（バージョン {_version()}）は、YAML・JSON・XML・CSV・TSV・TOML・properties を、mikefarah/yq と同じ式で"
             "読み取り・更新・変換するコマンドです。Python の標準ライブラリだけで動きます。", "",
             "## いつ使うか", "",
             "- 設定ファイル・API の入出力（YAML/JSON/XML/CSV/TOML）から値を取り出す、更新する、形式を変える",
             "- データの形（JSON Schema）を知りたい、スキーマとの食い違いを見たい",
             "- OpenAI・Gemini・Anthropic のリクエストボディを、別の API 用に変換する",
             "- 式の書き方に迷ったとき（この文書に決まりと例があります）", "",
             "## 使う前に", "",
             "```bash", "yaqpy --version        # 入っているか確かめる", "yaqpy --print-spec     # 最新の演算子・形式・レシピの一覧",
             "yaqpy --example        # 実行済みの使用例", "```", "",
             "入っていなければ、利用者に導入を頼みます（勝手に入れません）。", "",
             "## 基本の使い方", "", COMMAND_FORMS, "", "## 式の記法", "", SYNTAX_TABLE, "",
             "## 形式", "", *_format_lines(service), "",
             "## 式を書くときの決まり（やってはいけないこと）", "", *_rules_lines(), "",
             "## データの形を知る（schema）", "",
             "```bash", "yaqpy -o json schema データ.yaml       # JSON Schema (Draft 2020-12) を出す", "```", "",
             "`--schema-strict`（余分なキーを禁止）、`--schema-enum-max N`（繰り返し出る文字列を enum に）、"
             "`--schema-per-doc`（文書ごとに 1 つ）。`.items[] | schema` のように、式の途中にも挟めます。", "",
             "## API のリクエストを変換する（レシピ）", "", *_recipe_lines(), "",
             "```bash",
             "yaqpy --list-recipes",
             "yaqpy --recipe openai-to-gemini request.json               # 結果は標準出力、報告は標準エラー出力",
             "yaqpy --recipe openai-to-gemini --report request.json      # 落とした項目・差分・スキーマ照合の全体",
             "yaqpy --recipe openai-to-gemini --apply --out-dir out a.json b.json   # まとめて変換（元は書き換えない）",
             "yaqpy --recipe openai-to-gemini --recipe-test              # レシピ自身のテスト", "```", "",
             "- 変換するのは、テキストのメッセージ・サンプリング設定・関数ツール・tool_choice です。画像・ツール呼び出しの履歴などは"
             "落とし、**落としたものは必ず報告されます**。報告を読んで、利用者に伝えます。",
             "- モデル名は変換しません（`model` が変換先で必須なら、目標スキーマとの照合が「不足」と知らせます）。"
             "Anthropic へは `max_tokens` が必須なので、入力になければ 4096 を補い、補ったことを報告します。",
             "- 実際の API は呼びません。最後の確認は利用者が行います。",
             "- 自分のレシピ：`--recipe ./my.yaqpy`（式のファイル）。同じ場所の `my.recipe.yaml` に、説明・`carries`（読む項目）・"
             "`drops`（落とす項目と理由）・`adds`・`target_schema`・`tests` を書けます。", "",
             "## 安全上の注意", "",
             "- レシピは、ファイル・環境変数・外部コマンドに触れません（同梱のものも、自作のものも同じ）。",
             "- `-i`（その場で更新）は、必ず更新前に内容を確かめてから使います。TOML は書き出しでコメントが消えるので、"
             "`--toml-allow-lossy` が必要です。",
             "- 秘密（鍵・トークン）を含むデータは、画面や記録に出さない範囲で扱います。", "",
             "## 確かめ方", "",
             "式を書いたら、必ず実際の入力で実行して結果を確かめます。動作を推測で説明せず、実行した結果を見せます。"
             "一致しないときは、式・入力・実際の出力・期待した出力の 4 つを並べて直します。", "",
             "## 使用例（実行済み）", ""]
    for example in EXAMPLES:
        lines += _example_block(service, example)
    lines += ["## 演算子の一覧", "", *_operator_sections(table)]
    return "\n".join(lines)
