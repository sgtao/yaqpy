"""GUI の業務ロジック。Flet を import しないので単体テストできる。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from yaqpy.app.dto import EvalMode, EvaluateRequest, EvaluateResult, InputSource
from yaqpy.app.ports import FileSystemPort
from yaqpy.app.printer import MemorySink
from yaqpy.app.selfdoc import render_guide_prompt
from yaqpy.app.service import YqService
from yaqpy.core.engine.limits import StepBudget
from yaqpy.errors import UnknownFormatError
from yaqpy.gui import expression_file, intake, run_log, texts
from yaqpy.gui.errors_ja import ErrorViewModel, to_view_model
from yaqpy.gui.log_presenter import RerunPayload
from yaqpy.gui.paths import DEFAULT_MAX_DEPTH, DEFAULT_MAX_ITEMS, PathCandidate, collect_paths
from yaqpy.gui.state import AUTO, DocumentState, GuiState, build_options, truncate_for_display

BACKUP_SUFFIX = ".bak"
"""上書き保存の直前に、元の内容をここに退避する（U2）。同名のバックアップは毎回上書きする。"""


@dataclass(frozen=True, slots=True)
class OpenViewModel:
    name: str = ""
    path: str | None = None
    original_text: str = ""
    byte_size: int = 0
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class ValidationViewModel:
    valid: bool = True
    message: str = ""
    position: int = -1


@dataclass(frozen=True, slots=True)
class RunViewModel:
    display_text: str = ""       # 画面に出す（丸めた）文字列
    full_text: str = ""          # 保存に使う全量。display_text と混同しないこと
    truncated_lines: int = 0
    input_format: str = ""
    output_format: str = ""
    document_count: int = 0
    elapsed_ms: float = 0.0
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class CandidatesViewModel:
    candidates: tuple[PathCandidate, ...] = ()
    truncated: bool = False          # 上限に達して打ち切った
    note: str = ""                   # 候補を作れなかった理由（画面に出す）

    @property
    def is_empty(self) -> bool:
        return not self.candidates


@dataclass(frozen=True, slots=True)
class SaveViewModel:
    path: str = ""
    byte_size: int = 0
    needs_overwrite_confirmation: bool = False   # 元ファイルと同じパスを指された
    backup_path: str = ""            # 上書き保存で作ったバックアップ（別名保存なら空。U2）
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.needs_overwrite_confirmation


@dataclass(frozen=True, slots=True)
class ExpressionFileViewModel:
    """式のファイル（``.yaqpy``）を読んだ結果。v0.7.0。"""

    name: str = ""
    expression: str = ""
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class DownloadViewModel:
    """Web 版の保存（ブラウザのダウンロード）に渡すもの。v0.6.0。"""

    file_name: str = ""
    data: bytes = b""
    error: ErrorViewModel | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class RecordSource:
    """実行ログに記録するために、**実行した時点**の要求と入力を控えたもの（v0.7.0）。

    記録は結果を画面に出した後に別タスクで走るので、その間に状態（式・文書）が変わっても、
    ボタンを押した回の内容を記録できるよう、``run()`` が要求の組み立てと同時に控える。
    """

    request: EvaluateRequest
    inputs: tuple[run_log.LogInput, ...]


@dataclass(frozen=True, slots=True)
class RecordViewModel:
    """実行ログの記録の結果。``recorded`` が偽なら、理由が ``skipped``（記録しなかった）か
    ``error``（書き込みに失敗した）に入る。"""

    recorded: bool = False
    path: str = ""
    skipped: str = ""            # "web" / "disabled" / "failed_run" / "duplicate"
    error: str = ""


class RunGatePort(Protocol):
    """サーバー全体の同時実行数の関門（``yaqpy.gui.web_config.RunGate``）。"""

    def try_enter(self) -> bool: ...
    def leave(self) -> None: ...


class MainPresenter:
    """View（Flet）から呼ばれる唯一の窓口。"""

    def __init__(self, *, service: YqService, fs: FileSystemPort, state: GuiState,
                 size_of: Callable[[str], int] | None = None,
                 run_gate: RunGatePort | None = None) -> None:
        self._service = service
        self._fs = fs
        self.state = state
        self._size_of = size_of or os.path.getsize
        self._run_gate = run_gate            # Web 版だけ（全セッションで共有。v0.6.0）
        self._budget: StepBudget | None = None
        self._last_run: RunViewModel | None = None
        self._last_source: RecordSource | None = None
        self._last_log_key: str | None = None      # 最後に記録した内容のキー（重複除外。再起動で消える）
        self._candidates: list[PathCandidate] = []

    # ------------------------------------------------------------------ 開く

    async def open_path(self, path: str) -> OpenViewModel:
        try:
            item = await asyncio.to_thread(
                intake.from_path, self._fs, path,
                max_bytes=self.state.max_input_bytes,
                size_of=self._size_of,
                origin=intake.DIALOG,
            )
        except intake.IntakeError as e:
            return OpenViewModel(error=ErrorViewModel("intake", str(e)))
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return OpenViewModel(error=to_view_model(e))
        return self._accept(item)

    async def open_dropped(self, path: str) -> OpenViewModel:
        vm = await self.open_path(path)
        return vm

    def open_text(self, text: str, *, name: str = "") -> OpenViewModel:
        return self._accept(intake.from_text(text, name=name))

    def close_document(self) -> None:
        """開いているものをすべて閉じて、最初の状態に戻す。"""
        self.state.documents = []
        self.state.active_index = 0
        self.state.eval_all = False
        self.state.query.expression = "."
        self._last_run = None
        self._candidates = []

    def _accept(self, item: intake.IntakeItem) -> OpenViewModel:
        # 何も開いていない状態から開くときは、式欄の式を残す（先に「式を読み込む」で用意した式が
        # 消えないように。閉じたときは close_document が「.」に戻している）。開いている文書を
        # 置き換えるときだけ、新しい文書として恒等式から始める。
        was_unloaded = not self.state.documents
        self.state.documents = [DocumentState(path=item.path, name=item.name,
                                              original_text=item.text, byte_size=item.byte_size)]
        self.state.active_index = 0
        self.state.eval_all = False
        if not was_unloaded:
            self.state.query.expression = "."
        self._last_run = None
        self._candidates = []
        return OpenViewModel(name=item.name, path=item.path, original_text=item.text,
                             byte_size=item.byte_size)

    # ------------------------------------------------------------------ 複数ファイル（U3）

    async def add_path(self, path: str) -> OpenViewModel:
        """いま開いているものを閉じずに、もう 1 件をファイル一覧に加える。

        式はそのままにする（同じ式を複数の文書に当てて見比べる／``eval_all`` でまとめて評価する、
        という使い方を想定している）。
        """
        try:
            item = await asyncio.to_thread(
                intake.from_path, self._fs, path,
                max_bytes=self.state.max_input_bytes,
                size_of=self._size_of,
                origin=intake.DIALOG,
            )
        except intake.IntakeError as e:
            return OpenViewModel(error=ErrorViewModel("intake", str(e)))
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return OpenViewModel(error=to_view_model(e))
        return self._append(item)

    def _append(self, item: intake.IntakeItem) -> OpenViewModel:
        self.state.documents.append(DocumentState(path=item.path, name=item.name,
                                                   original_text=item.text,
                                                   byte_size=item.byte_size))
        self.state.active_index = len(self.state.documents) - 1
        self._last_run = None
        self._candidates = []
        return OpenViewModel(name=item.name, path=item.path, original_text=item.text,
                             byte_size=item.byte_size)

    # ------------------------------------------------------------------ Web 版のアップロード（v0.6.0）

    async def open_upload(self, name: str, data: bytes) -> OpenViewModel:
        """ブラウザから届いた中身を、最初の文書として開く（``open_path`` の Web 版）。

        サーバー側のパスは持たない（``path=None``）。上書き保存の対象にもならない。
        """
        item, error = await self._intake_upload(name, data)
        return error or self._accept(item)

    async def add_upload(self, name: str, data: bytes) -> OpenViewModel:
        """ブラウザから届いた中身を、開いている一覧に加える（``add_path`` の Web 版）。"""
        item, error = await self._intake_upload(name, data)
        return error or self._append(item)

    def check_upload_size(self, size: int) -> ErrorViewModel | None:
        """アップロードの**前に**大きさで断る（中身をサーバーへ送らせない）。"""
        try:
            intake.ensure_size(size, max_bytes=self.state.max_input_bytes)
        except intake.IntakeError as e:
            return ErrorViewModel("intake", str(e))
        return None

    async def _intake_upload(self, name: str,
                             data: bytes) -> tuple[intake.IntakeItem, OpenViewModel | None]:
        try:
            item = await asyncio.to_thread(intake.from_bytes, name, data,
                                           max_bytes=self.state.max_input_bytes)
        except intake.IntakeError as e:
            return intake.from_text(""), OpenViewModel(error=ErrorViewModel("intake", str(e)))
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return intake.from_text(""), OpenViewModel(error=to_view_model(e))
        return item, None

    def select_document(self, index: int) -> None:
        """一覧の 1 件を「いま表示している文書」にする（式は変えない）。"""
        if 0 <= index < len(self.state.documents):
            self.state.active_index = index
            self._last_run = None
            self._candidates = []

    def close_document_at(self, index: int) -> None:
        """一覧の 1 件だけを閉じる。最後の 1 件ならすべて閉じたのと同じになる。"""
        documents = self.state.documents
        if not (0 <= index < len(documents)):
            return
        del documents[index]
        if not documents:
            self.close_document()
            return
        if index < self.state.active_index:
            self.state.active_index -= 1
        self.state.active_index = min(self.state.active_index, len(documents) - 1)
        if len(documents) < 2:
            self.state.eval_all = False            # まとめて評価は 2 件以上のときだけ意味がある
        self._last_run = None
        self._candidates = []

    def edit_active_document(self, text: str) -> bool:
        """いま表示している文書の原文を画面上で書き換える（追加編集。改修計画とは別の追加要望）。

        変わっていなければ何もしない（デバウンス経由で不要な再実行を避ける）。開いたファイル
        そのもの（ディスク上の内容）は触らない：保存で上書きするときは、その時点のディスクの
        中身をあらためて読んでバックアップする（``_backup_before_overwrite``）ので、ここで
        ``original_text`` を書き換えても G4 の安全策は影響を受けない。
        """
        if not self.state.documents:
            return False
        doc = self.state.document
        if doc.original_text == text:
            return False
        self.state.documents[self.state.active_index] = replace(
            doc, original_text=text, byte_size=len(text.encode("utf-8")), edited=True)
        self._last_run = None
        self._candidates = []
        return True

    # ------------------------------------------------------------------ 式の検証

    def validate(self, expression: str) -> ValidationViewModel:
        if not expression.strip():
            return ValidationViewModel()           # 空は「.」と同じ扱いで有効
        info = self._service.validate_expression(expression)
        if info.valid:
            return ValidationViewModel()
        vm = to_view_model_from_info(info)
        return ValidationViewModel(valid=False, message=vm.message, position=vm.position)

    # ------------------------------------------------------------------ 実行

    async def run(self) -> RunViewModel:
        if self.state.running:
            return RunViewModel(error=ErrorViewModel("busy", texts.ERR_BUSY))
        if not self.state.document.is_loaded:
            return RunViewModel(error=ErrorViewModel("no_document", texts.ERR_NO_DOCUMENT))

        # 失敗した実行のあとに、古い成功結果が「保存できる結果」として残らないようにする
        # （表示と保存がずれない：不変条件 S2）。成功したときだけ、下で入れ直す。
        self._last_run = None
        self._last_source = None
        validation = self.validate(self.state.query.expression)
        if not validation.valid:
            return RunViewModel(error=ErrorViewModel("expression_syntax", validation.message,
                                                     hint=texts.HINT_EXPRESSION,
                                                     position=validation.position))

        request = self._build_request()
        source = RecordSource(request=request, inputs=self._log_inputs())
        gate = self._run_gate
        if gate is not None and not gate.try_enter():
            return RunViewModel(error=ErrorViewModel("busy", texts.ERR_SERVER_BUSY))
        budget = self._service.new_budget(request.options)
        self._budget = budget
        self.state.running = True
        try:
            result = await asyncio.to_thread(self._evaluate_sync, request, budget)
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return RunViewModel(error=self._for_this_mode(to_view_model(e)))
        finally:
            self.state.running = False
            self._budget = None
            if gate is not None:
                gate.leave()
        vm = self._success(result)
        self._last_run = vm
        self._last_source = source
        return vm

    def _for_this_mode(self, error: ErrorViewModel) -> ErrorViewModel:
        """Web 版では「設定で許可すれば実行できます」と案内しない（許可の手段が無いため）。"""
        if self.state.is_web and error.is_security:
            name = texts.CAP_ENV if error.capability == "env" else (
                texts.CAP_FILE if error.capability == "file" else texts.CAP_UNKNOWN)
            return replace(error, hint=texts.HINT_SECURITY_WEB.format(capability=name))
        return error

    def cancel(self) -> None:
        budget = self._budget
        if budget is not None:
            budget.cancel()

    @property
    def last_source(self) -> RecordSource | None:
        """最後に成功した ``run()`` の要求と入力（実行ログ用。``last_run`` と同じ回のもの）。"""
        return self._last_source

    @property
    def last_run(self) -> RunViewModel | None:
        """最後に成功した実行結果（保存で使う。G3）。"""
        return self._last_run

    # ------------------------------------------------------------------ 候補（G2）

    async def build_candidates(self) -> CandidatesViewModel:
        """いま開いている文書からパス候補を作る。open → run の後に 1 回だけ呼ぶ。

        入力形式は直前の実行結果（EvaluateResult.input_format）から採る。
        こうすると拡張子からの判定ロジックを GUI 側に複製しなくて済む。
        """
        self._candidates = []
        run = self._last_run
        if run is None or not self.state.document.is_loaded:
            return CandidatesViewModel(note=texts.MSG_NO_CANDIDATES)
        try:
            found = await asyncio.to_thread(self._collect_sync, run.input_format,
                                            self.state.document.original_text)
        except Exception:                        # noqa: BLE001 - 候補が無くても本体は使える
            return CandidatesViewModel(note=texts.MSG_NO_CANDIDATES)
        self._candidates = found
        if not found:
            return CandidatesViewModel(note=texts.MSG_NO_CANDIDATES)
        return CandidatesViewModel(candidates=tuple(found),
                                   truncated=len(found) >= DEFAULT_MAX_ITEMS)

    def filter_candidates(self, query: str = "", *, limit: int = 200) -> list[PathCandidate]:
        """絞り込みボックスの文字で候補を部分一致フィルタする（大文字小文字は無視）。"""
        text = query.strip().lower()
        items = self._candidates
        if text:
            items = [c for c in items if text in c.expression.lower()]
        return items[:limit]

    def apply_candidate(self, expression: str) -> str:
        """候補を式欄へ反映する（式欄を候補で置き換える）。"""
        self.state.query.expression = expression
        return expression

    def append_pipe(self) -> str:
        """式の末尾に `` | `` を足す（「+ パイプを追加」。v0.7.0）。戻り値は新しい式。

        Flet 1.0 の TextField にはカーソル位置を取る API が無いので、挿入位置はいつも末尾。
        式が空のとき、またはすでにパイプで終わっているときは何もしない。
        """
        current = self.state.query.expression
        stripped = current.rstrip()
        if not stripped or stripped.endswith("|"):
            return current
        self.state.query.expression = f"{stripped} | "
        return self.state.query.expression

    def adopted_formats(self) -> tuple[str, str]:
        """いま採用される（入力形式, 出力形式）。プルダウンが auto でも指定でも実際の形式名を返す。

        Service と同じ規則：入力 auto はファイル名の拡張子で判定し、拡張子が決まらなければ
        （貼り付け、または拡張子なし・未知の拡張子のファイル）内容を見る（yaqpy 独自の拡張。
        FormatRegistry.guess）。出力 auto は入力と同じ。実行結果に頼らないので、開いた直後や
        エラーのときも使える。文書がなければ ("", "")。
        """
        document, query = self.state.document, self.state.query
        if not document.is_loaded:
            return "", ""
        formats = self._service.formats
        input_name = query.input_format
        if input_name in ("", AUTO):
            input_name = formats.guess(document.source_name, document.original_text).name
        output_name = query.output_format
        if output_name in ("", AUTO):
            output_name = input_name
        return self._canonical(input_name), self._canonical(output_name)

    def _canonical(self, name: str) -> str:
        try:
            return self._service.formats.get(name).name
        except UnknownFormatError:
            return name

    # ------------------------------------------------------------------ ログからの再実行（v0.7.0）

    def apply_rerun(self, payload: RerunPayload, *, replace: bool = False) -> ErrorViewModel | None:
        """ログの内容を、**新しい文書として追加**して、式・形式・インデントを復元する（決定 M）。

        ``replace=True`` のときだけ、開いている文書をすべて閉じて置き換える（決定 Z：
        ``eval_all`` で記録したログは、ログに無い文書を巻き込まないため）。
        実行はしない（画面が実行する。記録もしない：決定 S）。失敗したら、状態を変えずに理由を返す。
        """
        for name, text in payload.inputs:
            try:
                intake.ensure_size(len(text.encode("utf-8")), max_bytes=self.state.max_input_bytes)
            except intake.IntakeError as e:
                return ErrorViewModel("intake", f"{name}: {e}")
        if replace:
            self.close_document()
        for name, text in payload.inputs:
            item = intake.from_text(text, name=name)
            if not self.state.documents:
                self._accept(item)
            else:
                self._append(item)
        q = self.state.query
        q.expression = payload.expression
        q.input_format = payload.input_format
        q.output_format = payload.output_format
        q.indent = payload.indent
        self.state.eval_all = bool(payload.eval_all) and self.state.has_multiple_documents
        return None

    # ------------------------------------------------------------------ 式のファイル（.yaqpy。v0.7.0）

    async def load_expression_file(self, path: str) -> ExpressionFileViewModel:
        """``.yaqpy`` / ``.yq`` を読んで式欄の式にする。実行はしない（検証は画面側）。

        式に誤りがあっても読み込む（赤枠で知らせる）。現在の式は確認なしで置き換える。
        """
        name = os.path.basename(path)
        try:
            if not self._fs.exists_file(path):
                return ExpressionFileViewModel(
                    name=name, error=ErrorViewModel("intake", texts.ERR_NOT_A_FILE))
            try:
                size = self._size_of(path)
            except OSError:
                size = 0
            expression_file.ensure_size(size)
            text = await asyncio.to_thread(self._fs.read_text, path)
            expression_file.ensure_size(len(text.encode("utf-8")))
            expression = expression_file.decode_expression(text)
        except expression_file.ExpressionFileError as e:
            return ExpressionFileViewModel(name=name, error=ErrorViewModel("expression_file", str(e)))
        except UnicodeDecodeError:
            return ExpressionFileViewModel(
                name=name, error=ErrorViewModel("expression_file", texts.ERR_EXPR_FILE_NOT_UTF8))
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return ExpressionFileViewModel(name=name, error=to_view_model(e))
        self.state.query.expression = expression
        return ExpressionFileViewModel(name=name, expression=expression)

    def check_expression_upload_size(self, size: int) -> ErrorViewModel | None:
        """Web 版：式のファイルをアップロードする**前に**、大きさで断る。"""
        try:
            expression_file.ensure_size(size)
        except expression_file.ExpressionFileError as e:
            return ErrorViewModel("expression_file", str(e))
        return None

    def load_expression_bytes(self, name: str, data: bytes) -> ExpressionFileViewModel:
        """Web 版：アップロードされた中身を式欄の式にする（``load_expression_file`` の Web 版）。"""
        try:
            expression_file.ensure_size(len(data))
            expression = expression_file.decode_expression(data)
        except expression_file.ExpressionFileError as e:
            return ExpressionFileViewModel(name=name, error=ErrorViewModel("expression_file", str(e)))
        self.state.query.expression = expression
        return ExpressionFileViewModel(name=name, expression=expression)

    def default_expression_file_name(self) -> str:
        """式の保存ダイアログの初期ファイル名（``sample.yaqpy``。貼り付け・文書なしなら ``expression.yaqpy``）。"""
        return expression_file.default_expression_file_name(self.state.document.name)

    async def save_expression_file(self, path: str) -> SaveViewModel:
        """式欄の式を ``.yaqpy`` に保存する。既存ファイルの上書き確認は OS のダイアログに任せる。"""
        path = expression_file.ensure_extension(path)
        text = expression_file.encode_expression(self.state.query.expression)
        try:
            await asyncio.to_thread(self._fs.atomic_write, path, text)
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return SaveViewModel(path=path, error=to_view_model(e))
        return SaveViewModel(path=path, byte_size=len(text.encode("utf-8")))

    def expression_download(self) -> DownloadViewModel:
        """Web 版：式のダウンロード（ファイル名とバイト列）。サーバーのディスクには書かない。"""
        text = expression_file.encode_expression(self.state.query.expression)
        return DownloadViewModel(file_name=self.default_expression_file_name(),
                                 data=text.encode("utf-8"))

    # ------------------------------------------------------------------ AI への相談文（追加要望）

    async def guide_prompt(self) -> str:
        """CLI の ``--guide-prompt`` と同じ内容（式の記法・演算子一覧・やってはいけないこと・例）を返す。

        文書の有無に関わらず使える。例の実行を含むのでスレッドへ逃がす。
        """
        return await asyncio.to_thread(render_guide_prompt, self._service)

    # ------------------------------------------------------------------ 保存（G3）

    def default_save_name(self) -> str:
        """保存ダイアログの初期ファイル名。拡張子は FormatSpec から採る。"""
        run = self._last_run
        format_name = (run.output_format if run else "") or self.state.query.output_format
        if format_name in ("", "auto"):
            format_name = "yaml"
        spec = self._service.formats.get(format_name)
        extension = spec.extensions[0] if spec.extensions else f".{spec.name}"
        name = self.state.document.name
        stem = os.path.splitext(name)[0] if name else ""
        return f"{stem or 'output'}{extension}"

    async def save(self, path: str, *, confirmed: bool = False) -> SaveViewModel:
        """変換結果の**全量**を保存する。

        既定は別名保存。**開いている元ファイルと同じパス**を指されたときだけ、確認
        （``confirmed=True``）のうえで上書きを許す。上書きの直前に、元の内容を
        ``{path}.bak`` として必ずバックアップする（G4 の緩和。U2）。バックアップが
        作れなければ、元のファイルを壊さないために**上書きしない**。
        """
        run = self._last_run
        if run is None:                       # 表示が古い／まだ実行していない
            run = await self.run()
            if not run.ok:
                return SaveViewModel(path=path, error=run.error)
        overwriting = self._is_source_path(path)
        if not confirmed and overwriting:
            return SaveViewModel(path=path, needs_overwrite_confirmation=True)
        backup_path = ""
        if confirmed and overwriting:
            backup_path, error = await self._backup_before_overwrite(path)
            if error is not None:
                return SaveViewModel(path=path, error=error)
        text = run.full_text                  # ← display_text を使わないこと（S1）
        try:
            await asyncio.to_thread(self._fs.atomic_write, path, text)
        except Exception as e:                # noqa: BLE001 - 画面を落とさない
            return SaveViewModel(path=path, error=to_view_model(e))
        return SaveViewModel(path=path, byte_size=len(text.encode("utf-8")), backup_path=backup_path)

    async def prepare_download(self) -> DownloadViewModel:
        """Web 版の保存：変換結果の**全量**を UTF-8 のバイト列にして、ファイル名と一緒に返す。

        サーバーのディスクには何も書かない（ブラウザがダウンロードとして受け取る）。
        表示が古ければ実行し直してから渡す（``save`` と同じ。表示と保存をずらさない）。
        """
        run = self._last_run
        if run is None:
            run = await self.run()
            if not run.ok:
                return DownloadViewModel(error=run.error)
        return DownloadViewModel(file_name=self.default_save_name(),
                                 data=run.full_text.encode("utf-8"))   # ← display_text ではない（S1）

    async def _backup_before_overwrite(self, path: str) -> tuple[str, ErrorViewModel | None]:
        """``path`` の**今の中身**を ``{path}.bak`` に退避する。戻り値は (バックアップ先, エラー)。

        元のファイルがもう無ければ（レース）、退避するものが無いので何もしない。
        """
        try:
            original = await asyncio.to_thread(self._fs.read_text, path)
        except FileNotFoundError:
            return "", None
        except Exception as e:                # noqa: BLE001 - 上書きの中止として画面に出す
            return "", to_view_model(e)
        backup_path = f"{path}{BACKUP_SUFFIX}"
        try:
            await asyncio.to_thread(self._fs.atomic_write, backup_path, original)
        except Exception as e:                # noqa: BLE001 - 上書きの中止として画面に出す
            return "", to_view_model(e)
        return backup_path, None

    def _is_source_path(self, path: str) -> bool:
        """保存先が、**開いているどれかの**文書と同じか（大文字小文字・相対表記を吸収する）。

        アクティブな 1 件だけでなく一覧全体を見る：複数ファイル（U3）を開いているとき、
        アクティブでない方のパスへうっかり保存しても、G4 の確認・バックアップを素通りしない。
        """
        try:
            target = os.path.normcase(os.path.realpath(path))
        except OSError:
            target = None
        for doc in self.state.documents:
            source = doc.path
            if not source:
                continue
            if target is not None:
                try:
                    if os.path.normcase(os.path.realpath(source)) == target:
                        return True
                    continue
                except OSError:
                    pass
            if source == path:
                return True
        return False

    def _collect_sync(self, input_format: str, text: str) -> list[PathCandidate]:
        """別スレッドで動く。デコードだけして評価器は通さない。"""
        options = build_options(self.state)
        decoder = self._service.formats.decoder_for(input_format, options)
        documents = list(decoder.decode_documents(text))
        return collect_paths(documents, max_depth=DEFAULT_MAX_DEPTH,
                             max_items=DEFAULT_MAX_ITEMS)

    # ------------------------------------------------------------------ 内部

    def _evaluate_sync(self, request: EvaluateRequest, budget: StepBudget) -> EvaluateResult:
        """別スレッドで動く同期部分。ここだけが重い。"""
        return self._service.evaluate(request, MemorySink(), budget=budget)

    def _log_inputs(self) -> tuple[run_log.LogInput, ...]:
        """この回の評価に渡す文書を、ログに記録する形にする（``_build_request`` と同じ選び方）。"""
        if self.state.eval_all and self.state.has_multiple_documents:
            documents = self.state.documents
        else:
            documents = [self.state.document]
        return tuple(run_log.LogInput(name=d.name or texts.MSG_PASTED, text=d.original_text,
                                      path=d.path, edited=d.edited) for d in documents)

    # ------------------------------------------------------------------ 実行ログ（v0.7.0）

    def log_dir(self) -> str:
        """実行ログの保存先（設定が空なら OS ごとの既定）。"""
        return self.state.settings.log_dir or run_log.default_log_dir()

    async def record_run(self, source: RecordSource, vm: RunViewModel) -> RecordViewModel:
        """成功した実行を、実行ログに 1 ファイル書く。**「実行」ボタンで始まった回だけ**呼ぶこと
        （自動の再実行は呼び出し側が呼ばない）。

        記録しないとき：Web 版・設定でオフ・失敗した実行・直前に記録した内容と同じ。
        書き込みに失敗しても例外にせず、``error`` で返す（実行結果には影響させない）。
        """
        if self.state.is_web:
            return RecordViewModel(skipped="web")
        settings = self.state.settings
        if not settings.log_enabled:
            return RecordViewModel(skipped="disabled")
        if not vm.ok:
            return RecordViewModel(skipped="failed_run")
        entry = self._log_entry(source, vm)
        key = run_log.dedupe_key(entry)
        if key == self._last_log_key:
            return RecordViewModel(skipped="duplicate")
        root = self.log_dir()
        try:
            path = await asyncio.to_thread(self._write_log_sync, root, entry,
                                           settings.log_max_entry_mib * 1024 * 1024,
                                           settings.log_max_files)
        except Exception as e:                      # noqa: BLE001 - 記録の失敗で画面を止めない
            return RecordViewModel(error=str(e) or type(e).__name__)
        self._last_log_key = key                    # 書き込みに成功したときだけ更新する
        return RecordViewModel(recorded=True, path=path)

    def _log_entry(self, source: RecordSource, vm: RunViewModel) -> run_log.LogEntry:
        request = source.request
        security = request.options.security
        return run_log.LogEntry(
            timestamp=datetime.now().astimezone(), expression=request.expression,
            inputs=source.inputs, input_format=vm.input_format,
            input_selected=request.input_format or AUTO, output_format=vm.output_format,
            output_selected=request.output_format or AUTO, output_text=vm.full_text,
            indent=request.options.indent, eval_all=request.mode is EvalMode.ALL,
            document_count=vm.document_count, elapsed_ms=vm.elapsed_ms,
            allow_env=security.allow_env, allow_file=security.allow_file,
            options=request.options)

    def _write_log_sync(self, root: str, entry: run_log.LogEntry, max_entry_bytes: int,
                        max_files: int) -> str:
        """別スレッドで動く。組み立て・書き込み・件数の整理。"""
        built = run_log.build_log(entry, max_entry_bytes=max_entry_bytes)
        path = run_log.write_log(root, entry, built, self._fs.write_file)
        run_log.prune_logs(root, max_files)
        return path

    def _build_request(self) -> EvaluateRequest:
        q = self.state.query
        if self.state.eval_all and self.state.has_multiple_documents:
            # CLI の eval-all 相当：開いているすべての文書を 1 回の評価にまとめて渡す
            # （fi / filename で文書ごとに参照できる）。
            inputs = tuple(InputSource(d.source_name, d.original_text)
                          for d in self.state.documents)
            mode = EvalMode.ALL
        else:
            d = self.state.document
            inputs = (InputSource(d.source_name, d.original_text),)
            mode = EvalMode.STREAM
        return EvaluateRequest(
            expression=q.expression or ".",
            inputs=inputs,
            mode=mode,
            options=build_options(self.state),
            input_format=q.input_format,       # "auto" なら service が拡張子で判定する
            output_format=q.output_format,
        )

    def _success(self, result: EvaluateResult) -> RunViewModel:
        full = result.output or ""
        shown, omitted = truncate_for_display(full, self.state.settings.max_display_lines)
        return RunViewModel(
            display_text=shown,
            full_text=full,
            truncated_lines=omitted,
            input_format=result.input_format,
            output_format=result.output_format,
            document_count=result.document_count,
            elapsed_ms=result.elapsed_seconds * 1000.0,
        )


def to_view_model_from_info(info: object) -> ErrorViewModel:
    """ExpressionInfo（例外ではない）を ErrorViewModel に合わせる。"""
    message = getattr(info, "message", "")
    position = getattr(info, "position", -1)
    where = f"式の {position + 1} 文字目でエラー" if position >= 0 else "式のエラー"
    return ErrorViewModel("expression_syntax", f"{where}：{message}",
                          hint=texts.HINT_EXPRESSION, position=position)
