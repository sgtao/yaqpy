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
    """設定画面の値。v1 では永続化しない（セッション内のみ）。"""

    allow_env: bool = False
    allow_file: bool = False
    timeout_seconds: float = 10.0
    max_input_mib: int = 50
    max_display_lines: int = 5000
    dark_theme: bool = False

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mib * 1024 * 1024


@dataclass(slots=True)
class GuiState:
    """画面をまたいで共有する唯一の状態。"""

    document: DocumentState = field(default_factory=DocumentState)
    query: QueryState = field(default_factory=QueryState)
    settings: SettingsState = field(default_factory=SettingsState)
    running: bool = False


def build_options(state: GuiState) -> Options:
    """GuiState から、その 1 回の評価に使う不変の Options を作る。

    Options は frozen なので使い回さず、実行のたびに作り直す。
    """
    q, s = state.query, state.settings
    indent = max(q.indent, 0)
    return Options(
        input_format=q.input_format or AUTO,
        output_format=q.output_format or AUTO,
        indent=indent,
        pretty_print=q.pretty_print,
        yaml=YamlOptions(indent=indent),
        json=JsonOptions(indent=indent),
        toon=ToonOptions(indent=indent if indent >= 1 else 2),
        security=SecurityPolicy(
            allow_env=s.allow_env,
            allow_file=s.allow_file,
            allow_system=False,      # GUI からは決して許可しない（設計書 10 章）
        ),
        limits=Limits(
            max_input_bytes=s.max_input_bytes,
            timeout_seconds=s.timeout_seconds,
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
