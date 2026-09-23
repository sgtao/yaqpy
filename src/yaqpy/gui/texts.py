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
BTN_ADD_FILE = "＋ファイルを追加"
BTN_CLOSE = "閉じる"
BTN_MORE_FILES = "＋ファイル {n}件"
BTN_OPEN_FILE = "ファイルを開く"
TIP_EXPR_PASTE = "クリップボードの内容を式欄に貼り付け（式を置き換えます）"
TIP_EXPR_COPY = "式をコピー"
TIP_EXPR_CLEAR = "式をクリア"
MSG_EXPR_COPIED = "式をクリップボードにコピーしました"
MSG_LOG_WRITE_FAILED = "実行ログを保存できませんでした：{reason}"
TIP_EXPR_LOAD = "式を読み込む（.yaqpy）"
TIP_EXPR_SAVE = "式を保存（.yaqpy）"
MSG_EXPR_LOADED = "式を読み込みました: {name}"
MSG_EXPR_SAVED = "式を保存しました: {path}"
ERR_EXPR_FILE_TOO_LARGE = "式のファイルが大きすぎます（{size} バイト / 上限 {limit} バイト）"
ERR_EXPR_FILE_NOT_UTF8 = "UTF-8 のテキストとして読めませんでした（式のファイルではないようです）"
MENU_CLOSE_FILE = "閉じる: {name}"
BTN_RUN = "実行"
BTN_CANCEL = "中止"
BTN_SAVE = "保存"
BTN_COPY = "コピー"
BTN_OPEN_SETTINGS = "設定を開く"
BTN_ADD_PIPE = "+ パイプを追加"
BTN_QUIT = "終了"
LBL_INPUT_FORMAT = "入力形式"
LBL_OUTPUT_FORMAT = "出力形式"
LBL_AUTO_SAME_AS_INPUT = "auto（入力と同じ）"
LBL_INDENT = "インデント"
LBL_EXPRESSION = "式"
LBL_PROPERTY = "プロパティ"
LBL_ORIGINAL = "オリジナル"
LBL_CONVERTED = "変換結果"
LBL_LANGUAGE = "表示言語"
LBL_EDITED = "追加編集"

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
DLG_QUIT_TITLE = "アプリを閉じますか？"
DLG_QUIT_OK = "閉じる"
DLG_QUIT_CANCEL = "やめる"
MSG_COPIED = "変換結果をクリップボードにコピーしました"
SET_TITLE = "設定"
SET_SECURITY = "セキュリティ"
SET_SECURITY_NOTE = "既定はすべて不許可です。必要なときだけ許可してください"
SET_SECURITY_WHY = (
    "env は環境変数を、load はファイルを読む機能です。load の方が読める範囲が広いため、"
    "別々に許可できるようにしています"
)
SET_ALLOW_ENV = "env / strenv 演算子を許可（環境変数を読めるようになります）"
SET_ALLOW_FILE = (
    "load / loadstr 演算子を許可（他のファイルを読めるようになります）"
    "（現在この演算子は未実装のため、切り替えても動作に影響しません）"
)
SET_SYSTEM_NOTE = "※ system 演算子は GUI では提供しません"
SET_RUN = "実行"
SET_TIMEOUT = "タイムアウト（秒）"
SET_MAX_INPUT = "最大入力（MiB）"
SET_MAX_LINES = "表示行数の上限"
SET_VIEW = "表示"
SET_LOG = "実行ログ"
SET_LOG_ENABLED = "実行ログを記録する"
SET_LOG_DIR = "保存先"
SET_LOG_DIR_HINT = "空欄なら既定の保存先：{path}"
SET_LOG_MAX_FILES = "保存する件数の上限"
SET_LOG_MAX_ENTRY = "1件あたりの本文の上限（MiB）"
SET_LOG_NOTE = (
    "［実行］ボタンで変換に成功したときだけ、1 回につき 1 ファイルを記録します（ログ画面で見られます）。"
    "ログには入力データと変換結果が平文で保存されます。機密情報を扱うときは記録をオフにしてください。"
    "env を許可している場合、環境変数の値が結果に含まれることがあります。"
    "保存先を変えても、これまでのログは移動しません"
)
BTN_BROWSE = "参照…"
LBL_LOG_SEARCH = "絞り込み（日時・形式・式・ファイル名）"
TIP_LOG_REFRESH = "一覧を更新"
TIP_LOG_OPEN_FOLDER = "保存先を開く"
TIP_LOG_DELETE_ALL = "すべて削除"
BTN_LOG_RERUN = "再実行"
BTN_LOG_SAVE_EXPR = "式を .yaqpy に保存"
BTN_LOG_DELETE = "削除"
BTN_DIALOG_CANCEL = "やめる"
BTN_DELETE_OK = "削除する"
BTN_REPLACE_RERUN = "置き換えて再実行"
LBL_LOG_INPUT = "入力："
LBL_LOG_EXPRESSION = "式："
MSG_LOG_EMPTY = "ログはまだありません。［実行］で変換に成功すると、ここに記録されます"
MSG_LOG_NO_MATCH = "絞り込みに合うログはありません"
MSG_LOG_SELECT = "左の一覧からログを選んでください"
MSG_LOG_STATUS = "全 {total} 件（うち {shown} 件を表示） ／ 保存先：{path}"
MSG_LOG_CANNOT_RERUN = "このログは再実行できません（本文を省略した・古い形式・壊れている、など）"
MSG_LOG_RESTORE_FAILED = "ログの入力を元の形式に戻せませんでした：{reason}"
MSG_LOG_READ_FAILED = "ログを読めませんでした：{reason}"
MSG_LOG_BROKEN = "このログは読み戻せませんでした（全文だけ表示します）：{reason}"
MSG_LOG_DELETED = "削除しました"
MSG_LOG_DELETED_ALL = "{n} 件を削除しました"
MSG_LOG_FOLDER_FAILED = "保存先を開けませんでした：{reason}"
MSG_LOG_RERUN_STARTED = "ログから再実行しました（新しい文書として追加しています）"
DLG_LOG_DELETE_TITLE = "このログを削除しますか？"
DLG_LOG_DELETE_BODY = "元に戻せません。\n\n{name}"
DLG_LOG_DELETE_ALL_TITLE = "すべてのログを削除しますか？"
DLG_LOG_DELETE_ALL_BODY = "{n} 件のログをすべて削除します。元に戻せません。"
DLG_LOG_REPLACE_TITLE = "開いている文書を置き換えて再実行しますか？"
DLG_LOG_REPLACE_BODY = (
    "このログは、複数の文書をまとめて評価したときの記録です。"
    "開いている文書を閉じて、ログの入力に置き換えて再実行します。"
)
BTN_RESET_DEFAULT = "既定に戻す"
MSG_FOLDER_PICK_FAILED = "フォルダを選べませんでした。保存先のパスを直接入力してください"
SET_DARK = "ダークテーマ"
SET_LANGUAGE_NOTE = "変更は次回の起動から有効です"
NAV_MAIN = "📄 メイン"
NAV_SETTINGS = "⚙ 設定"
NAV_ASK_AI = "🤖 AIに相談"
NAV_LOG = "📜 ログ"
MSG_DROP_UNSUPPORTED = "この環境ではファイルのドラッグ＆ドロップに対応していません"
MSG_PASTE_HERE = "ここに YAML / JSON を貼り付けてください"
MSG_PASTED = "（貼り付けたテキスト）"
MSG_NO_CANDIDATES = "この文書からはプロパティ候補を作れませんでした"
MSG_TOO_MANY_CANDIDATES = "候補が多いため、絞り込んでください"
MSG_COPIED_SHORT = "コピーしました！"

# 「AIに相談」画面（--guide-prompt の GUI 版。v0.7.0）
ASK_AI_TITLE = "AI に相談"
ASK_AI_HINT = (
    "左に、データの例とやりたい変換を書いて［＋プロンプトに反映］を押すと、右の相談文の"
    "「## 依頼」に入ります。右の全文をコピーして、ChatGPT や Claude などの AI に貼り付けてください"
    "（右の欄は自由に編集できます）。"
)
LBL_ASK_AI_INPUT = "あなたの入力（データ例・やりたい変換）"
LBL_ASK_AI_PROMPT = "AIへの相談文（コピーしてAIに貼り付け）"
PH_ASK_AI_INPUT = "例: この JSON から、price が 500 を超える商品の name だけを取り出したい"
BTN_PASTE = "貼り付け"
BTN_CLEAR = "クリア"
BTN_APPLY_TO_PROMPT = "＋プロンプトに反映"
BTN_RESET_PROMPT = "初期状態に戻す"
MSG_PROMPT_LOADING = "相談文を作っています…"
MSG_APPLY_EMPTY = "左の欄に入力してから、［＋プロンプトに反映］を押してください"
MSG_PASTE_FAILED = (
    "クリップボードから貼り付けられませんでした（ブラウザや OS が許可していない可能性があります）。"
    "欄をクリックして Ctrl + V で貼り付けてください"
)
MSG_COPY_FAILED = (
    "クリップボードにコピーできませんでした（ブラウザや OS が許可していない可能性があります）。"
    "欄の文字を選択してコピーしてください"
)

# Web 版（yaqpy-web。v0.6.0）
BTN_DOWNLOAD = "ダウンロード"
MSG_DOWNLOADED = "ダウンロードを開始しました: {name}"
MSG_UPLOADING = "アップロード中…"
MSG_WEB_HINT = "ファイルはこのブラウザからサーバーへ送られ、変換結果はダウンロードで受け取ります"
ERR_UPLOAD_FAILED = "アップロードできませんでした（{name}）"
ERR_SERVER_BUSY = "サーバーが混み合っています。少し待ってからもう一度実行してください"
HINT_SECURITY_WEB = "Web 版では {capability} は使えません（サーバー側の情報を読ませないため）"
SET_WEB_SECURITY_NOTE = (
    "Web 版では env / strenv・load / loadstr・system の演算子は常に無効です"
    "（ブラウザからサーバー側の環境変数やファイルを読ませないため）"
)
SET_WEB_LIMITS_NOTE = "Web 版の上限（サーバーの起動時に決まります）：最大入力 {mib} MiB・タイムアウト {seconds} 秒"
SET_WEB_LANGUAGE_NOTE = "Web 版の表示言語は、サーバーの起動時（--lang）に決まります"

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
    "GUI を使うには flet が必要です。次のどれかで導入してください:\n"
    '  pip install "yaqpy[gui]"          （PyPI から GUI つきで入れ直す）\n'
    '  uv tool install "yaqpy[gui]"      （uv のツールとして入れている場合）\n'
    '  pip install "flet>=1.0,<2"        （インストール済みの yaqpy に flet だけを追加）\n'
    "  uv sync --extra gui               （リポジトリを clone した開発環境）\n"
    "GitHub のリリースから入れる方法などは、README のインストールの節を参照してください:\n"
    "  https://github.com/sgtao/yaqpy/blob/main/README.ja.md#インストール\n"
)

WEB_INSTALL_HINT = (
    "Web 版を使うには flet-web が必要です。次のどれかで導入してください:\n"
    '  pip install "yaqpy[web]"          （PyPI から Web 版つきで入れ直す）\n'
    '  uv tool install "yaqpy[web]"      （uv のツールとして入れている場合）\n'
    '  pip install "flet[web]>=1.0,<2"   （インストール済みの yaqpy に flet-web だけを追加）\n'
    "  uv sync --extra web               （リポジトリを clone した開発環境）\n"
)
WEB_STARTED = "yaqpy の Web 版を起動しました: {url}\n（止めるには、この端末で Ctrl+C）\n"
WEB_START_FAILED = (
    "Web 版を起動できませんでした（{host}:{port}）。ポートが使用中なら、--port で別の番号を"
    "指定してください\n"
)
WEB_EXPOSED_WARNING = (
    "警告: --host {host} は、この PC 以外からも接続できる待ち受けです。\n"
    "  yaqpy の Web 版には認証がありません。同じネットワークの誰でも画面を開けます。\n"
    "  公開するなら、認証つきのリバースプロキシの後ろに置いてください。\n"
    "  （env / load などサーバー側の情報を読む演算子は、Web 版では常に無効です）\n"
)

_JA: dict[str, str] = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}

_EN: dict[str, str] = {
    "APP_TITLE": "yaqpy",
    "BTN_ADD_FILE": "+ Add File",
    "BTN_CLOSE": "Close",
    "BTN_MORE_FILES": "+ {n} more",
    "BTN_OPEN_FILE": "Open File",
    "TIP_EXPR_PASTE": "Paste the clipboard into the expression box (replaces the expression)",
    "TIP_EXPR_COPY": "Copy the expression",
    "TIP_EXPR_CLEAR": "Clear the expression",
    "MSG_EXPR_COPIED": "Copied the expression to the clipboard",
    "MSG_LOG_WRITE_FAILED": "Could not save the run log: {reason}",
    "TIP_EXPR_LOAD": "Load an expression (.yaqpy)",
    "TIP_EXPR_SAVE": "Save the expression (.yaqpy)",
    "MSG_EXPR_LOADED": "Loaded the expression: {name}",
    "MSG_EXPR_SAVED": "Saved the expression: {path}",
    "ERR_EXPR_FILE_TOO_LARGE": "The expression file is too large ({size} bytes / limit {limit} bytes)",
    "ERR_EXPR_FILE_NOT_UTF8": "Could not read this as UTF-8 text (it does not look like an expression file)",
    "MENU_CLOSE_FILE": "Close: {name}",
    "BTN_RUN": "Run",
    "BTN_CANCEL": "Cancel",
    "BTN_SAVE": "Save",
    "BTN_COPY": "Copy",
    "BTN_OPEN_SETTINGS": "Open Settings",
    "BTN_ADD_PIPE": "+ Add Pipe",
    "BTN_QUIT": "Quit",
    "LBL_INPUT_FORMAT": "Input Format",
    "LBL_OUTPUT_FORMAT": "Output Format",
    "LBL_AUTO_SAME_AS_INPUT": "auto (same as input)",
    "LBL_INDENT": "Indent",
    "LBL_EXPRESSION": "Expression",
    "LBL_PROPERTY": "Property",
    "LBL_ORIGINAL": "Original",
    "LBL_CONVERTED": "Result",
    "LBL_LANGUAGE": "Display language",
    "LBL_EDITED": "Edited",
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
    "DLG_QUIT_TITLE": "Quit the app?",
    "DLG_QUIT_OK": "Quit",
    "DLG_QUIT_CANCEL": "Cancel",
    "MSG_COPIED": "Copied the result to the clipboard",
    "SET_TITLE": "Settings",
    "SET_SECURITY": "Security",
    "SET_SECURITY_NOTE": "Everything is disallowed by default. Enable only what you actually need",
    "SET_SECURITY_WHY": (
        "env reads environment variables and load reads files. load can reach much more, "
        "so the two can be allowed separately"
    ),
    "SET_ALLOW_ENV": "Allow env / strenv operators (lets expressions read environment variables)",
    "SET_ALLOW_FILE": (
        "Allow load / loadstr operators (lets expressions read other files) "
        "(these operators are not implemented yet, so this switch has no effect for now)"
    ),
    "SET_SYSTEM_NOTE": "Note: the system operator is not available in the GUI",
    "SET_RUN": "Run",
    "SET_TIMEOUT": "Timeout (seconds)",
    "SET_MAX_INPUT": "Max input (MiB)",
    "SET_MAX_LINES": "Max lines shown",
    "SET_VIEW": "Display",
    "SET_LOG": "Run log",
    "SET_LOG_ENABLED": "Record the run log",
    "SET_LOG_DIR": "Folder",
    "SET_LOG_DIR_HINT": "Leave empty for the default folder: {path}",
    "SET_LOG_MAX_FILES": "Max number of logs to keep",
    "SET_LOG_MAX_ENTRY": "Max body size per log (MiB)",
    "SET_LOG_NOTE": (
        "Only when a conversion succeeds with the [Run] button, one file per run is recorded "
        "(you can browse them on the Log tab). Logs keep your input data and results as plain text; "
        "turn recording off when you handle confidential data. If env is allowed, environment "
        "variable values may appear in the results. Changing the folder does not move existing logs"
    ),
    "BTN_BROWSE": "Browse…",
    "NAV_LOG": "📜 Log",
    "LBL_LOG_SEARCH": "Filter (time, format, expression, file name)",
    "TIP_LOG_REFRESH": "Refresh the list",
    "TIP_LOG_OPEN_FOLDER": "Open the log folder",
    "TIP_LOG_DELETE_ALL": "Delete all",
    "BTN_LOG_RERUN": "Run again",
    "BTN_LOG_SAVE_EXPR": "Save expression as .yaqpy",
    "BTN_LOG_DELETE": "Delete",
    "BTN_DIALOG_CANCEL": "Cancel",
    "BTN_DELETE_OK": "Delete",
    "BTN_REPLACE_RERUN": "Replace and run again",
    "LBL_LOG_INPUT": "Input: ",
    "LBL_LOG_EXPRESSION": "Expression: ",
    "MSG_LOG_EMPTY": "No logs yet. When a conversion succeeds with [Run], it is recorded here",
    "MSG_LOG_NO_MATCH": "No log matches the filter",
    "MSG_LOG_SELECT": "Pick a log from the list on the left",
    "MSG_LOG_STATUS": "{total} logs ({shown} shown) / folder: {path}",
    "MSG_LOG_CANNOT_RERUN": ("This log cannot be run again (its body was omitted, it is an "
                             "unknown version, or it is broken)"),
    "MSG_LOG_RESTORE_FAILED": "Could not turn the logged input back into its format: {reason}",
    "MSG_LOG_READ_FAILED": "Could not read the log: {reason}",
    "MSG_LOG_BROKEN": "This log could not be read back (showing the full text only): {reason}",
    "MSG_LOG_DELETED": "Deleted",
    "MSG_LOG_DELETED_ALL": "Deleted {n} logs",
    "MSG_LOG_FOLDER_FAILED": "Could not open the folder: {reason}",
    "MSG_LOG_RERUN_STARTED": "Ran it again from the log (added as a new document)",
    "DLG_LOG_DELETE_TITLE": "Delete this log?",
    "DLG_LOG_DELETE_BODY": "This cannot be undone.\n\n{name}",
    "DLG_LOG_DELETE_ALL_TITLE": "Delete all logs?",
    "DLG_LOG_DELETE_ALL_BODY": "All {n} logs will be deleted. This cannot be undone.",
    "DLG_LOG_REPLACE_TITLE": "Replace the open documents and run again?",
    "DLG_LOG_REPLACE_BODY": (
        "This log was recorded from several documents evaluated together. "
        "The open documents will be closed and replaced by the logged inputs."
    ),
    "BTN_RESET_DEFAULT": "Reset",
    "MSG_FOLDER_PICK_FAILED": "Could not pick a folder. Type the folder path instead",
    "SET_DARK": "Dark theme",
    "SET_LANGUAGE_NOTE": "Takes effect the next time you start the app",
    "NAV_MAIN": "📄 Main",
    "NAV_SETTINGS": "⚙ Settings",
    "NAV_ASK_AI": "🤖 Ask AI",
    "MSG_DROP_UNSUPPORTED": "Drag-and-drop is not supported in this environment",
    "MSG_PASTE_HERE": "Paste YAML / JSON here",
    "MSG_PASTED": "(pasted text)",
    "MSG_NO_CANDIDATES": "No property suggestions could be made from this document",
    "MSG_TOO_MANY_CANDIDATES": "Too many suggestions — type to narrow them down",
    "MSG_COPIED_SHORT": "Copied!",
    "ASK_AI_TITLE": "Ask AI",
    "ASK_AI_HINT": (
        "Write your sample data and what you want to do on the left, then press [+ Add to prompt]: "
        'it goes into the "## 依頼" ("Request") section of the prompt on the right. Copy the whole '
        "prompt and paste it into ChatGPT, Claude, or another AI (the right box is freely editable)."
    ),
    "LBL_ASK_AI_INPUT": "Your input (sample data and what you want to do)",
    "LBL_ASK_AI_PROMPT": "Prompt for the AI (copy it and paste it into the AI)",
    "PH_ASK_AI_INPUT": "e.g. From this JSON, I want only the names of items whose price is over 500",
    "BTN_PASTE": "Paste",
    "BTN_CLEAR": "Clear",
    "BTN_APPLY_TO_PROMPT": "+ Add to prompt",
    "BTN_RESET_PROMPT": "Reset",
    "MSG_PROMPT_LOADING": "Building the prompt…",
    "MSG_APPLY_EMPTY": "Type something in the left box, then press [+ Add to prompt]",
    "MSG_PASTE_FAILED": ("Could not paste from the clipboard (the browser or OS may not allow it). "
                         "Click the box and press Ctrl + V instead"),
    "MSG_COPY_FAILED": ("Could not copy to the clipboard (the browser or OS may not allow it). "
                        "Select the text in the box and copy it instead"),
    "BTN_DOWNLOAD": "Download",
    "MSG_DOWNLOADED": "Download started: {name}",
    "MSG_UPLOADING": "Uploading…",
    "MSG_WEB_HINT": ("Files are sent from this browser to the server; you get the result back "
                     "as a download"),
    "ERR_UPLOAD_FAILED": "Could not upload ({name})",
    "ERR_SERVER_BUSY": "The server is busy. Wait a moment and run it again",
    "HINT_SECURITY_WEB": ("{capability} is not available in the web version (so that the "
                          "server's own data cannot be read)"),
    "SET_WEB_SECURITY_NOTE": (
        "In the web version the env / strenv, load / loadstr and system operators are always "
        "off (so that a browser cannot read the server's environment variables or files)"
    ),
    "SET_WEB_LIMITS_NOTE": ("Web version limits (set when the server starts): max input {mib} MiB, "
                            "timeout {seconds} s"),
    "SET_WEB_LANGUAGE_NOTE": "In the web version the display language is set when the server starts (--lang)",
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
        '  pip install "yaqpy[gui]"          (reinstall from PyPI with the GUI)\n'
        '  uv tool install "yaqpy[gui]"      (if you installed yaqpy as a uv tool)\n'
        '  pip install "flet>=1.0,<2"        (add only flet to an installed yaqpy)\n'
        "  uv sync --extra gui               (a development checkout of the repository)\n"
        "For other ways, such as installing from a GitHub release, see the README:\n"
        "  https://github.com/sgtao/yaqpy#installation\n"
    ),
    "WEB_INSTALL_HINT": (
        "The web version needs flet-web. Install it one of these ways:\n"
        '  pip install "yaqpy[web]"          (reinstall from PyPI with the web version)\n'
        '  uv tool install "yaqpy[web]"      (if you installed yaqpy as a uv tool)\n'
        '  pip install "flet[web]>=1.0,<2"   (add only flet-web to an installed yaqpy)\n'
        "  uv sync --extra web               (a development checkout of the repository)\n"
    ),
    "WEB_STARTED": "yaqpy web version is running: {url}\n(press Ctrl+C in this terminal to stop it)\n",
    "WEB_START_FAILED": ("Could not start the web version on {host}:{port}. If the port is in use, "
                         "choose another one with --port\n"),
    "WEB_EXPOSED_WARNING": (
        "Warning: --host {host} accepts connections from other machines, not just this PC.\n"
        "  The yaqpy web version has no authentication; anyone on the network can open it.\n"
        "  To publish it, put it behind a reverse proxy that requires authentication.\n"
        "  (Operators that read the server's own data, such as env / load, are always off.)\n"
    ),
}

assert _EN.keys() == _JA.keys(), "texts.py: the English table is missing or has extra keys"

LANGUAGES = ("ja", "en")
DEFAULT_LANGUAGE = "ja"


def select_language(language: str) -> None:
    """UI 文言をまとめて差し替える。起動時に 1 回だけ呼ぶ（U4）。"""
    globals().update(_EN if language == "en" else _JA)
