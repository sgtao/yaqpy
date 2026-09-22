"""UI 文言（日本語）。将来の多言語化に備えてここに集める。"""

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
LBL_EVAL_ALL = "まとめて評価 (eval-all)"

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
HINT_EVAL_ALL = (
    "開いているすべての文書を 1 回の評価にまとめます（fi や filename でファイルを区別できます。"
    "CLI の eval-all と同じ）"
)

INSTALL_HINT = (
    "GUI を使うには flet が必要です。次のどちらかで導入してください:\n"
    '  pip install "flet>=1.0,<2"     （インストール済みの yaqpy に追加）\n'
    "  uv sync --extra gui            （リポジトリを clone した開発環境）\n"
    "GitHub のリリースから GUI つきで入れ直す方法は、README のインストールの節を参照してください:\n"
    "  https://github.com/sgtao/yaqpy#インストール\n"
)
