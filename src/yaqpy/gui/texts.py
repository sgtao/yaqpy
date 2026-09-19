"""UI 文言（日本語）。将来の多言語化に備えてここに集める。"""

from __future__ import annotations

APP_TITLE = "yaqpy"

# ボタン・ラベル
BTN_OPEN = "ファイルを開く"
BTN_CLOSE = "閉じる"
BTN_RUN = "実行"
BTN_CANCEL = "中止"
BTN_SAVE = "保存"
BTN_COPY = "コピー"
BTN_ADD_TO_EXPR = "式に追加"
LBL_INPUT_FORMAT = "入力形式"
LBL_OUTPUT_FORMAT = "出力形式"
LBL_INDENT = "インデント"
LBL_PRETTY = "整形 (-P)"
LBL_EXPRESSION = "式"
LBL_PROPERTY = "プロパティ"
LBL_ORIGINAL = "オリジナル"
LBL_CONVERTED = "変換結果"

# プレースホルダ・案内
PH_EXPRESSION = "例: .items[] | select(.price > 500)"
MSG_NO_DOCUMENT = "ファイルを開くか、テキストを貼り付けてください"
MSG_RUNNING = "実行中…"
MSG_TRUNCATED = "（以下 {n} 行を表示していません。保存すれば全量が得られます）"
MSG_SAVED = "保存しました: {path}"
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

INSTALL_HINT = (
    "GUI を使うには flet が必要です。次のどちらかで導入してください:\n"
    '  pip install "yaqpy[gui]"\n'
    "  uv sync --extra gui\n"
)
