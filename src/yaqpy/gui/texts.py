"""UI 文言。既定は日本語で、英語にも切り替えられる（改修計画 5-4 節 U4）。

``select_language`` を呼ぶと、このモジュールの ``NAME = "..."`` の形の定数を選んだ言語の
値に差し替える。**アプリの起動時に 1 回だけ**呼ぶ想定（設定を読み込んだ直後、画面を組み立てる
前）で、実行中に呼び替えても、すでに作った画面の部品の文字は自動では変わらない（Flet の
制御を作り直す仕組みが無いため。次に起動したときから有効になる）。

呼び出し側は今までどおり ``texts.MSG_NO_DOCUMENT`` のように読む。言語を切り替えても
モジュールの属性名は変わらないので、呼び出し側のコードは変更が要らない。

**この対象は画面の文言（ボタン・ラベル・案内・エラーの見出し）だけ**。式の構文エラーの
「N 文字目」「N 行 M 列」のような、例外の詳細な内容の組み立て（``gui/errors_ja.py`` の
``to_view_model``）は対象外（日本語のまま）。USAGE-GUI.ja.md に明記している。
"""

from __future__ import annotations

APP_TITLE = "yaqpy"

# ボタン・ラベル
BTN_OPEN = "ファイルを開く"
BTN_ADD_FILE = "＋ファイルを追加"
BTN_CLOSE = "閉じる"
BTN_RUN = "実行"
BTN_CANCEL = "中止"
BTN_SAVE = "保存"
BTN_COPY = "コピー"
BTN_OPEN_SETTINGS = "設定を開く"
BTN_ADD_TO_EXPR = "式に追加"
LBL_INPUT_FORMAT = "入力形式"
LBL_OUTPUT_FORMAT = "出力形式"
LBL_INDENT = "インデント"
LBL_PRETTY = "整形 (-P)"
LBL_EXPRESSION = "式"
LBL_PROPERTY = "プロパティ"
LBL_ORIGINAL = "オリジナル"
LBL_CONVERTED = "変換結果"
LBL_LANGUAGE = "表示言語"

# プレースホルダ・案内
PH_EXPRESSION = "例: .items[] | select(.price > 500)"
MSG_NO_DOCUMENT = "ファイルを開くか、テキストを貼り付けてください"
MSG_RUNNING = "実行中…"
MSG_CANCELLING = "中止を要求しました。書き出しの途中は、その処理が終わってから止まります"
MSG_TRUNCATED = "（以下 {n} 行を表示していません。保存すれば全量が得られます）"
MSG_SAVED = "保存しました: {path}"
MSG_SAVED_WITH_BACKUP = "保存しました: {path}（元の内容は {backup} に残しました）"
DLG_OVERWRITE_TITLE = "元のファイルを上書きしますか？"
DLG_OVERWRITE_BODY = (
    "保存先が、いま開いているファイルと同じです。\n"
    "上書きする前に、元の内容を「{path}.bak」として自動でバックアップします。\n\n{path}"
)
DLG_OVERWRITE_OK = "上書きする"
DLG_OVERWRITE_CANCEL = "やめる"
MSG_COPIED = "変換結果をクリップボードにコピーしました"
SET_TITLE = "設定"
SET_SECURITY = "セキュリティ"
SET_SECURITY_NOTE = "既定はすべて不許可です。必要なときだけ許可してください"
SET_ALLOW_ENV = "env / strenv 演算子を許可（環境変数を読めるようになります）"
SET_ALLOW_FILE = "load / loadstr 演算子を許可（他のファイルを読めるようになります）"
SET_SYSTEM_NOTE = "※ system 演算子は GUI では提供しません"
SET_RUN = "実行"
SET_TIMEOUT = "タイムアウト（秒）"
SET_MAX_INPUT = "最大入力（MiB）"
SET_MAX_LINES = "表示行数の上限"
SET_VIEW = "表示"
SET_DARK = "ダークテーマ"
SET_LANGUAGE_NOTE = "変更は次回の起動から有効です"
NAV_MAIN = "📄 メイン"
NAV_SETTINGS = "⚙ 設定"
MSG_DROP_UNSUPPORTED = "この環境ではファイルのドラッグ＆ドロップに対応していません"
MSG_PASTE_HERE = "ここに YAML / JSON を貼り付けてください"
MSG_PASTED = "（貼り付けたテキスト）"
MSG_NO_CANDIDATES = "この文書からはプロパティ候補を作れませんでした"
MSG_TOO_MANY_CANDIDATES = "候補が多いため、絞り込んでください"

# エラー
ERR_BUSY = "実行中です。終わるまでお待ちください"
ERR_NO_DOCUMENT = "先にファイルを開いてください"
ERR_TOO_LARGE = "ファイルが大きすぎます（{size} / 上限 {limit}）"
ERR_NOT_A_FILE = "ファイルを指定してください（フォルダは開けません）"
ERR_NOT_UTF8 = "UTF-8 のテキストとして読めませんでした"
ERR_UNEXPECTED = "想定外のエラーが発生しました"

# エラーの対処ヒント
HINT_EXPRESSION = "式の書き方は USAGE.ja.md を参照してください"
HINT_INPUT_FORMAT = "入力形式の選択が違うかもしれません"
HINT_SECURITY = "設定画面で「{capability} を許可」を有効にすると実行できます"
HINT_TIMEOUT = "設定画面でタイムアウトを延ばせます"
HINT_CANCELLED = "中止しました"
HINT_REPORT = "再現手順を添えて不具合として報告してください"

# 許可の名前（gui/errors_ja.py の HINT_SECURITY に埋め込む。U4）
CAP_ENV = "環境変数（env / strenv）"
CAP_FILE = "ファイル読み込み（load / loadstr）"
CAP_UNKNOWN = "この機能"

INSTALL_HINT = (
    "GUI を使うには flet が必要です。次のどちらかで導入してください:\n"
    '  pip install "flet>=1.0,<2"     （インストール済みの yaqpy に追加）\n'
    "  uv sync --extra gui            （リポジトリを clone した開発環境）\n"
    "GitHub のリリースから GUI つきで入れ直す方法は、README のインストールの節を参照してください:\n"
    "  https://github.com/sgtao/yaqpy#インストール\n"
)

_JA: dict[str, str] = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}

_EN: dict[str, str] = {
    "APP_TITLE": "yaqpy",
    "BTN_OPEN": "Open File",
    "BTN_ADD_FILE": "+ Add File",
    "BTN_CLOSE": "Close",
    "BTN_RUN": "Run",
    "BTN_CANCEL": "Cancel",
    "BTN_SAVE": "Save",
    "BTN_COPY": "Copy",
    "BTN_OPEN_SETTINGS": "Open Settings",
    "BTN_ADD_TO_EXPR": "Add to Expression",
    "LBL_INPUT_FORMAT": "Input Format",
    "LBL_OUTPUT_FORMAT": "Output Format",
    "LBL_INDENT": "Indent",
    "LBL_PRETTY": "Pretty-print (-P)",
    "LBL_EXPRESSION": "Expression",
    "LBL_PROPERTY": "Property",
    "LBL_ORIGINAL": "Original",
    "LBL_CONVERTED": "Result",
    "LBL_LANGUAGE": "Display language",
    "PH_EXPRESSION": "e.g. .items[] | select(.price > 500)",
    "MSG_NO_DOCUMENT": "Open a file, or paste text here",
    "MSG_RUNNING": "Running…",
    "MSG_CANCELLING": ("Cancel requested. If writing the output is in progress, it will stop "
                       "once that finishes"),
    "MSG_TRUNCATED": "({n} more lines not shown. Save to get the full result)",
    "MSG_SAVED": "Saved: {path}",
    "MSG_SAVED_WITH_BACKUP": "Saved: {path} (the original content was kept at {backup})",
    "DLG_OVERWRITE_TITLE": "Overwrite the original file?",
    "DLG_OVERWRITE_BODY": (
        "The save location is the same as the file you have open.\n"
        'Before overwriting, the original content will be backed up automatically as '
        '"{path}.bak".\n\n{path}'
    ),
    "DLG_OVERWRITE_OK": "Overwrite",
    "DLG_OVERWRITE_CANCEL": "Cancel",
    "MSG_COPIED": "Copied the result to the clipboard",
    "SET_TITLE": "Settings",
    "SET_SECURITY": "Security",
    "SET_SECURITY_NOTE": "Everything is disallowed by default. Enable only what you actually need",
    "SET_ALLOW_ENV": "Allow env / strenv operators (lets expressions read environment variables)",
    "SET_ALLOW_FILE": "Allow load / loadstr operators (lets expressions read other files)",
    "SET_SYSTEM_NOTE": "Note: the system operator is not available in the GUI",
    "SET_RUN": "Run",
    "SET_TIMEOUT": "Timeout (seconds)",
    "SET_MAX_INPUT": "Max input (MiB)",
    "SET_MAX_LINES": "Max lines shown",
    "SET_VIEW": "Display",
    "SET_DARK": "Dark theme",
    "SET_LANGUAGE_NOTE": "Takes effect the next time you start the app",
    "NAV_MAIN": "📄 Main",
    "NAV_SETTINGS": "⚙ Settings",
    "MSG_DROP_UNSUPPORTED": "Drag-and-drop is not supported in this environment",
    "MSG_PASTE_HERE": "Paste YAML / JSON here",
    "MSG_PASTED": "(pasted text)",
    "MSG_NO_CANDIDATES": "No property suggestions could be made from this document",
    "MSG_TOO_MANY_CANDIDATES": "Too many suggestions — type to narrow them down",
    "ERR_BUSY": "Still running. Please wait for it to finish",
    "ERR_NO_DOCUMENT": "Open a file first",
    "ERR_TOO_LARGE": "The file is too large ({size} / limit {limit})",
    "ERR_NOT_A_FILE": "Please choose a file (folders cannot be opened)",
    "ERR_NOT_UTF8": "Could not read this as UTF-8 text",
    "ERR_UNEXPECTED": "An unexpected error occurred",
    "HINT_EXPRESSION": "See USAGE.ja.md for how to write expressions",
    "HINT_INPUT_FORMAT": "The selected input format might be wrong",
    "HINT_SECURITY": 'Enable "Allow {capability}" in Settings to run this',
    "HINT_TIMEOUT": "You can extend the timeout in Settings",
    "HINT_CANCELLED": "Cancelled",
    "HINT_REPORT": "Please report this as a bug, with steps to reproduce it",
    "CAP_ENV": "environment variables (env / strenv)",
    "CAP_FILE": "file reading (load / loadstr)",
    "CAP_UNKNOWN": "this feature",
    "INSTALL_HINT": (
        "The GUI needs flet. Install it one of these ways:\n"
        '  pip install "flet>=1.0,<2"     (add it to an installed yaqpy)\n'
        "  uv sync --extra gui            (a development checkout of the repository)\n"
        "To reinstall with the GUI included from a GitHub release, see the install section "
        "of the README (Japanese only):\n"
        "  https://github.com/sgtao/yaqpy#インストール\n"
    ),
}

assert _EN.keys() == _JA.keys(), "texts.py: the English table is missing or has extra keys"

LANGUAGES = ("ja", "en")
DEFAULT_LANGUAGE = "ja"


def select_language(language: str) -> None:
    """UI 文言をまとめて差し替える。起動時に 1 回だけ呼ぶ（U4）。"""
    globals().update(_EN if language == "en" else _JA)
