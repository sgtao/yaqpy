"""ログ画面の業務ロジック（Flet 非依存。v0.7.0）。

一覧（ファイル名から）・絞り込み（ファイル名の項目はすぐ、式と入力ファイル名はファイルの先頭部分を
読んで）・詳細の読み込み・削除・再実行用のデータの作成・式の保存・保存先を開く、を受け持つ。
画面（``pages/log_page.py``）は、これを呼んで見せるだけ。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yaqpy.app.ports import FileSystemPort
from yaqpy.gui import expression_file, run_log, texts
from yaqpy.gui.state import truncate_for_display
from yaqpy.options import Options


@dataclass(frozen=True, slots=True)
class LogRow:
    """一覧の 1 行。"""

    file: run_log.LogFile
    title: str                # 2026-09-23 14:05:12
    subtitle: str             # json → yaml  (1.2 KB)


@dataclass(frozen=True, slots=True)
class LogDetail:
    """一覧で選んだ 1 件の中身。読めなかったときは ``error`` に理由が入り、全文だけ見せる。"""

    path: str
    text: str = ""
    display_text: str = ""            # 表示用に丸めたもの（保存や再実行には ``text`` を使う）
    truncated_lines: int = 0
    parsed: run_log.ParsedLog | None = None
    error: str = ""

    @property
    def expression(self) -> str:
        return self.parsed.expression if self.parsed is not None and self.parsed.ok else ""

    @property
    def can_rerun(self) -> bool:
        return self.parsed is not None and self.parsed.rerunnable

    @property
    def can_save_expression(self) -> bool:
        return self.parsed is not None and self.parsed.ok

    @property
    def input_summary(self) -> str:
        """「sample.json（json → yaml）」の形。複数の入力は「a.json, b.json（json → yaml）」。"""
        parsed = self.parsed
        if parsed is None or not parsed.ok:
            return ""
        names = ", ".join(i.name for i in parsed.inputs) or "-"
        summary = parsed.summary
        in_fmt = (summary.get("input") or {}).get("format", "")
        out_fmt = (summary.get("output") or {}).get("format", "")
        return f"{names}（{in_fmt} → {out_fmt}）"


@dataclass(frozen=True, slots=True)
class RerunPayload:
    """再実行のために、Main 画面へ戻すもの（決定 L・M）。"""

    expression: str
    inputs: tuple[tuple[str, str], ...]      # (文書名, 元の形式に戻したテキスト)
    input_format: str                         # 実際に使った形式（auto に戻さない）
    output_format: str                        # 画面で選んでいた値（auto なら auto）
    indent: int
    eval_all: bool

    @property
    def needs_replace_confirmation(self) -> bool:
        """決定 Z：``eval_all`` で記録した 2 件以上のログは、開いている文書を置き換えて再実行する。"""
        return self.eval_all


class LogPresenter:
    def __init__(self, *, fs: FileSystemPort, log_dir: Callable[[], str],
                 options: Callable[[], Options], max_display_lines: Callable[[], int],
                 launcher: Callable[[str], None] | None = None) -> None:
        self._fs = fs
        self._log_dir = log_dir
        self._options = options
        self._max_display_lines = max_display_lines
        self._launcher = launcher or _open_in_file_manager
        self._files: list[run_log.LogFile] = []
        self._heads: dict[tuple[str, int], run_log.LogHead] = {}    # (パス, 更新日時) → 先頭の情報

    # ------------------------------------------------------------------ 一覧

    @property
    def directory(self) -> str:
        return self._log_dir()

    def refresh(self) -> list[LogRow]:
        """保存先を走査して一覧を作り直す（ファイル名と ``os.stat`` だけ。中身は開かない）。"""
        self._files = run_log.list_log_files(self.directory)
        return [self._row(f) for f in self._files]

    @property
    def total(self) -> int:
        return len(self._files)

    def _row(self, file: run_log.LogFile) -> LogRow:
        return LogRow(file=file, title=file.timestamp_text,
                      subtitle=f"{file.input_format} → {file.output_format}  ({_human(file.size)})")

    # ------------------------------------------------------------------ 絞り込み（決定 N）

    def filter(self, query: str) -> list[LogRow]:
        """空白で区切った語のすべてが、大文字小文字を区別せず部分一致する行だけを返す。

        ファイル名から分かる項目（日時・入力形式・出力形式）はすぐに絞り込める。式と入力ファイル名は、
        ファイルの先頭を読み込み済み（``load_heads`` 済み）のものだけが対象になる。
        """
        terms = [t for t in query.lower().split() if t]
        rows = [self._row(f) for f in self._files]
        if not terms:
            return rows
        return [row for row in rows if self._matches(row.file, terms)]

    def _matches(self, file: run_log.LogFile, terms: list[str]) -> bool:
        haystack = " ".join([
            file.timestamp_text, file.input_format, file.output_format,
            f"{file.input_format}-to-{file.output_format}", f"{file.input_format} → "
            f"{file.output_format}", os.path.basename(file.path)]).lower()
        head = self._heads.get(self._head_key(file))
        if head is not None:
            haystack += " " + head.expression.lower() + " " + " ".join(head.input_names).lower()
        return all(term in haystack for term in terms)

    def pending_heads(self) -> list[run_log.LogFile]:
        """まだ先頭を読んでいない（式・入力ファイル名で絞り込めない）ファイル。"""
        return [f for f in self._files if self._head_key(f) not in self._heads]

    async def load_heads(self) -> int:
        """先頭を読んでいないファイルの先頭を、別スレッドで読んでメモリに置く。戻り値は読んだ件数。"""
        pending = self.pending_heads()
        if not pending:
            return 0

        def read_all() -> dict[tuple[str, int], run_log.LogHead]:
            return {self._head_key(f): run_log.read_head(f.path) for f in pending}

        self._heads.update(await asyncio.to_thread(read_all))
        return len(pending)

    def _head_key(self, file: run_log.LogFile) -> tuple[str, int]:
        try:
            mtime = os.stat(file.path).st_mtime_ns
        except OSError:
            mtime = 0
        return (file.path, mtime)

    # ------------------------------------------------------------------ 詳細

    async def read_detail(self, path: str) -> LogDetail:
        """選んだログを読む（別スレッド）。読み戻せなくても全文は見せる。"""
        try:
            text = await asyncio.to_thread(_read_text, path)
        except OSError as e:
            return LogDetail(path=path, error=str(e))
        parsed = await asyncio.to_thread(run_log.parse_log_text, text)
        shown, omitted = truncate_for_display(text, self._max_display_lines())
        return LogDetail(path=path, text=text, display_text=shown, truncated_lines=omitted,
                         parsed=parsed, error="" if parsed.ok else parsed.error)

    # ------------------------------------------------------------------ 削除

    def delete(self, path: str) -> bool:
        return run_log.delete_log(path)

    def delete_all(self) -> int:
        return run_log.delete_all_logs(self.directory)

    # ------------------------------------------------------------------ 再実行（決定 L・M・Z）

    async def build_rerun(self, detail: LogDetail) -> RerunPayload | str:
        """ログの入力を元の形式へ戻して、Main 画面へ戻すデータにする。失敗したら理由の文字列。"""
        parsed = detail.parsed
        if parsed is None or not parsed.rerunnable:
            return texts.MSG_LOG_CANNOT_RERUN
        options = self._options()
        try:
            restored = await asyncio.to_thread(
                lambda: tuple((i.name or texts.MSG_PASTED, run_log.restore_input_text(i, options))
                              for i in parsed.inputs))
        except Exception as e:                      # noqa: BLE001 - 画面には理由を出す
            return texts.MSG_LOG_RESTORE_FAILED.format(reason=str(e) or type(e).__name__)
        summary = parsed.summary
        input_info = summary.get("input") or {}
        output_info = summary.get("output") or {}
        indent = output_info.get("indent")
        return RerunPayload(
            expression=parsed.expression,
            inputs=restored,
            input_format=str(input_info.get("format") or "auto"),
            output_format=str(output_info.get("selected") or "auto"),
            indent=indent if isinstance(indent, int) and indent >= 0 else 2,
            eval_all=bool(summary.get("eval_all")) and len(restored) >= 2)

    # ------------------------------------------------------------------ 式を .yaqpy に保存（決定 N）

    def default_expression_name(self, detail: LogDetail) -> str:
        """既定のファイル名：ログの入力ファイル名の拡張子を除いたもの＋``.yaqpy``（貼り付け由来は
        ``expression.yaqpy``）。"""
        parsed = detail.parsed
        name = parsed.inputs[0].name if parsed is not None and parsed.inputs else ""
        if name == texts.MSG_PASTED:
            name = ""
        return expression_file.default_expression_file_name(name)

    async def save_expression(self, detail: LogDetail, path: str) -> str:
        """ログの式を ``.yaqpy`` に書く。戻り値は書いたパス（``.yaqpy`` を補う）。"""
        target = expression_file.ensure_extension(path)
        body = expression_file.encode_expression(detail.expression)
        await asyncio.to_thread(self._fs.atomic_write, target, body)
        return target

    # ------------------------------------------------------------------ 保存先を開く

    def open_folder(self) -> str:
        """保存先を OS のファイルマネージャーで開く（無ければ作る）。戻り値は開いたパス。"""
        directory = self.directory
        Path(directory).mkdir(parents=True, exist_ok=True)
        self._launcher(directory)
        return directory


def _read_text(path: str) -> str:
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def _human(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _open_in_file_manager(directory: str) -> None:
    """Windows は ``os.startfile``、macOS は ``open``、それ以外は ``xdg-open``。
    macOS・Linux は実機未確認（U4 と同じ扱い）。"""
    if sys.platform == "win32":
        os.startfile(directory)                     # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", directory])       # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", directory])   # noqa: S603, S607
