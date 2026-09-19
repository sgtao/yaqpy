"""GUI の業務ロジック。Flet を import しないので単体テストできる。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass

from yaqpy.app.dto import EvalMode, EvaluateRequest, EvaluateResult, InputSource
from yaqpy.app.ports import FileSystemPort
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService
from yaqpy.core.engine.limits import StepBudget
from yaqpy.gui import intake, texts
from yaqpy.gui.errors_ja import ErrorViewModel, to_view_model
from yaqpy.gui.paths import DEFAULT_MAX_DEPTH, DEFAULT_MAX_ITEMS, PathCandidate, collect_paths
from yaqpy.gui.state import DocumentState, GuiState, build_options, truncate_for_display


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


class MainPresenter:
    """View（Flet）から呼ばれる唯一の窓口。"""

    def __init__(self, *, service: YqService, fs: FileSystemPort, state: GuiState,
                 size_of: Callable[[str], int] | None = None) -> None:
        self._service = service
        self._fs = fs
        self.state = state
        self._size_of = size_of or os.path.getsize
        self._budget: StepBudget | None = None
        self._last_run: RunViewModel | None = None
        self._candidates: list[PathCandidate] = []

    # ------------------------------------------------------------------ 開く

    async def open_path(self, path: str) -> OpenViewModel:
        try:
            item = await asyncio.to_thread(
                intake.from_path, self._fs, path,
                max_bytes=self.state.settings.max_input_bytes,
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
        self.state.document = DocumentState()
        self.state.query.expression = "."
        self._last_run = None
        self._candidates = []

    def _accept(self, item: intake.IntakeItem) -> OpenViewModel:
        self.state.document = DocumentState(path=item.path, name=item.name,
                                            original_text=item.text, byte_size=item.byte_size)
        self.state.query.expression = "."          # 新しい文書は恒等式から始める
        self._last_run = None
        self._candidates = []
        return OpenViewModel(name=item.name, path=item.path, original_text=item.text,
                             byte_size=item.byte_size)

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

        validation = self.validate(self.state.query.expression)
        if not validation.valid:
            return RunViewModel(error=ErrorViewModel("expression_syntax", validation.message,
                                                     hint=texts.HINT_EXPRESSION,
                                                     position=validation.position))

        request = self._build_request()
        budget = self._service.new_budget(request.options)
        self._budget = budget
        self.state.running = True
        try:
            result = await asyncio.to_thread(self._evaluate_sync, request, budget)
        except Exception as e:                      # noqa: BLE001 - 画面を落とさない
            return RunViewModel(error=to_view_model(e))
        finally:
            self.state.running = False
            self._budget = None
        vm = self._success(result)
        self._last_run = vm
        return vm

    def cancel(self) -> None:
        budget = self._budget
        if budget is not None:
            budget.cancel()

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

    def apply_candidate(self, expression: str, *, append: bool = False) -> str:
        """候補を式欄へ反映する。append=True ならパイプで連結する。

        すでに式がその候補そのもの、またはその候補で終わっているときは連結しない
        （候補を選ぶと式欄が置き換わるため、直後の「追加」で ``A | A`` になるのを防ぐ）。
        """
        current = self.state.query.expression.strip()
        if append and current and current != ".":
            if current == expression or current.endswith(f"| {expression}"):
                return current
            merged = f"{current} | {expression}"
        else:
            merged = expression
        self.state.query.expression = merged
        return merged

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

    def _build_request(self) -> EvaluateRequest:
        d, q = self.state.document, self.state.query
        return EvaluateRequest(
            expression=q.expression or ".",
            inputs=(InputSource(d.source_name, d.original_text),),
            mode=EvalMode.STREAM,
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
