"""GUI の状態と、そこから Options を組み立てる関数（Flet 非依存）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from yaqpy.options import JsonOptions, Limits, Options, SecurityPolicy, ToonOptions, YamlOptions

AUTO = "auto"


@dataclass(slots=True)
class DocumentState:
    """いま開いている文書。path が None なら貼り付け由来。"""

    path: str | None = None
    name: str = ""                # 形式の自動判定に使う表示名（ファイル名）
    original_text: str = ""
    byte_size: int = 0
    edited: bool = False          # 読み込み後に画面上で書き換えたか（追加編集。追加要望）

    @property
    def is_loaded(self) -> bool:
        return bool(self.original_text)

    @property
    def source_name(self) -> str:
        """EvaluateRequest に渡す入力名。拡張子から形式が判定される。"""
        return self.path or self.name or "<text>"


@dataclass(slots=True)
class QueryState:
    """式と出力の設定。"""

    expression: str = "."
    input_format: str = AUTO
    output_format: str = AUTO
    indent: int = 2
    pretty_print: bool = False


@dataclass(slots=True)
class SettingsState:
    """設定画面の値。

    ``allow_env`` / ``allow_file`` を除く「安全な設定」は Phase U1 で永続化する
    （``gui/_prefs.py``。危険な許可は毎回既定に戻す。5-4 節 U1）。
    """

    allow_env: bool = False
    allow_file: bool = False
    timeout_seconds: float = 10.0
    max_input_mib: int = 50
    max_display_lines: int = 5000
    dark_theme: bool = False
    language: str = "ja"             # "ja" / "en"（U4）。次の起動から有効（gui/texts.py）

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mib * 1024 * 1024


def _positive_float(raw: object, fallback: float) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _positive_int(raw: object, fallback: int) -> int:
    return int(_positive_float(raw, float(fallback)))


_LANGUAGES = ("ja", "en")


def settings_to_dict(settings: SettingsState) -> dict[str, object]:
    """永続化する「安全な設定」だけを取り出す（``allow_env`` / ``allow_file`` は含めない）。"""
    return {
        "timeout_seconds": settings.timeout_seconds,
        "max_input_mib": settings.max_input_mib,
        "max_display_lines": settings.max_display_lines,
        "dark_theme": settings.dark_theme,
        "language": settings.language,
    }


def settings_from_dict(data: dict[str, object]) -> SettingsState:
    """読み込み時に壊れた値（型違い・欠損）が来ても既定値で受ける。"""
    defaults = SettingsState()
    language = data.get("language")
    if language not in _LANGUAGES:
        language = defaults.language
    return SettingsState(
        timeout_seconds=_positive_float(data.get("timeout_seconds"), defaults.timeout_seconds),
        max_input_mib=_positive_int(data.get("max_input_mib"), defaults.max_input_mib),
        max_display_lines=_positive_int(data.get("max_display_lines"), defaults.max_display_lines),
        dark_theme=bool(data.get("dark_theme", defaults.dark_theme)),
        language=language,
    )


@dataclass(frozen=True, slots=True)
class WebLimits:
    """Web 版（v0.6.0）でサーバーが強制する上限。ブラウザ側の設定値はこれを超えられない。

    設定画面の値（``SettingsState``）はブラウザに保存されるので、利用者が書き換えられる。
    上限はサーバーの起動引数で決まり、``GuiState`` の実効値（``max_input_bytes`` など）と
    ``build_options`` で、どちらか小さい方が効く。
    """

    max_input_bytes: int
    timeout_seconds: float


@dataclass(slots=True)
class GuiState:
    """画面をまたいで共有する唯一の状態。

    ``documents`` は開いている文書の一覧（U3。開いた順）。単一ファイルの操作（開く・貼り付け・
    閉じる）は、これまでどおり 1 件だけの一覧として扱う。``document`` はいま選ばれている 1 件
    （``active_index``）を指す読み取り専用のショートカットで、代入はできない
    （``documents``／``active_index`` を操作すること）。
    """

    documents: list[DocumentState] = field(default_factory=list)
    active_index: int = 0
    eval_all: bool = False           # 2 件以上を「まとめて評価」する（CLI の eval-all 相当。U3）
    query: QueryState = field(default_factory=QueryState)
    settings: SettingsState = field(default_factory=SettingsState)
    running: bool = False
    web: WebLimits | None = None     # Web 版のセッションなら上限が入る（デスクトップは None）

    @property
    def is_web(self) -> bool:
        return self.web is not None

    @property
    def max_input_bytes(self) -> int:
        """実際に効く入力サイズの上限（設定値と、Web 版ならサーバーの上限の小さい方）。"""
        limit = self.settings.max_input_bytes
        return min(limit, self.web.max_input_bytes) if self.web else limit

    @property
    def timeout_seconds(self) -> float:
        limit = self.settings.timeout_seconds
        return min(limit, self.web.timeout_seconds) if self.web else limit

    @property
    def document(self) -> DocumentState:
        if 0 <= self.active_index < len(self.documents):
            return self.documents[self.active_index]
        return DocumentState()

    @property
    def has_multiple_documents(self) -> bool:
        return len(self.documents) > 1


def clamp_settings_to_web_limits(state: GuiState) -> None:
    """Web 版のセッション開始時に、ブラウザに保存された設定をサーバーの上限まで下げる。

    効く値は ``build_options`` でいつも小さい方になるが、設定画面に上限より大きい数字
    （デスクトップの既定の 50 MiB など）が出たままだと、効いている値と食い違って見えるため。
    """
    web = state.web
    if web is None:
        return
    s = state.settings
    s.max_input_mib = max(1, min(s.max_input_mib, web.max_input_bytes // (1024 * 1024)))
    s.timeout_seconds = min(s.timeout_seconds, web.timeout_seconds)


def build_options(state: GuiState) -> Options:
    """GuiState から、その 1 回の評価に使う不変の Options を作る。

    Options は frozen なので使い回さず、実行のたびに作り直す。

    Web 版では ``env`` / ``load`` を設定に関係なく**強制的に無効**にする（計画書 5-5 節の 2。
    ブラウザを開いた誰かに、サーバー側の環境変数・ファイルを読ませないため）。
    """
    q, s = state.query, state.settings
    indent = max(q.indent, 0)
    web = state.is_web
    return Options(
        input_format=q.input_format or AUTO,
        output_format=q.output_format or AUTO,
        indent=indent,
        pretty_print=q.pretty_print,
        yaml=YamlOptions(indent=indent),
        json=JsonOptions(indent=indent),
        toon=ToonOptions(indent=indent if indent >= 1 else 2),
        security=SecurityPolicy(
            allow_env=s.allow_env and not web,
            allow_file=s.allow_file and not web,
            allow_system=False,      # GUI からは決して許可しない（設計書 10 章）
        ),
        limits=Limits(
            max_input_bytes=state.max_input_bytes,
            timeout_seconds=state.timeout_seconds,
        ),
    )


def truncate_for_display(text: str, max_lines: int) -> tuple[str, int]:
    """表示用に先頭 max_lines 行へ丸める。戻り値は (表示文字列, 省略した行数)。

    保存には**必ず元の text** を使うこと（設計書のリスク R8）。
    """
    if max_lines <= 0:
        return text, 0
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, 0
    return "".join(lines[:max_lines]), len(lines) - max_lines
