"""Composition Root。pages がアプリ層を直接 import しないための唯一の結節点。"""

from __future__ import annotations

from yaqpy.app.local import LocalEnvironment, LocalFileSystem
from yaqpy.app.ports import SandboxFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter, RunGatePort
from yaqpy.gui.state import AUTO, GuiState

_service: YqService | None = None
_web_service: YqService | None = None


def make_service() -> YqService:
    """YqService はステートレスなので 1 個を使い回す。"""
    global _service
    if _service is None:
        _service = YqService(LocalFileSystem(), LocalEnvironment())
    return _service


def make_web_service() -> YqService:
    """Web 版のサービス。**サーバー側のファイル・環境変数に構造的に届かない**（v0.6.0）。

    ``build_options`` が ``env`` / ``load`` を強制的に無効にするのに加えて、ファイルは
    ``SandboxFileSystem``（すべて拒否）、環境変数は空の ``StaticEnvironment`` にする。
    許可の判定に万一の抜けがあっても、読めるものが無い（計画書 5-5 節の 2、リスク R10）。
    """
    global _web_service
    if _web_service is None:
        _web_service = YqService(SandboxFileSystem(), StaticEnvironment({}))
    return _web_service


def make_presenter(state: GuiState, *, run_gate: RunGatePort | None = None) -> MainPresenter:
    if state.is_web:
        return MainPresenter(service=make_web_service(), fs=SandboxFileSystem(), state=state,
                             run_gate=run_gate)
    return MainPresenter(service=make_service(), fs=LocalFileSystem(), state=state)


def input_format_choices() -> list[str]:
    """読める形式（デコーダのある形式）。形式レジストリから自動で決まる。"""
    return [AUTO, *make_service().list_formats().input_formats]


def output_format_choices() -> list[str]:
    return [AUTO, *make_service().list_formats().output_formats]


def open_extensions() -> list[str]:
    """「開く」ダイアログに出す拡張子。読める形式の登録から導く（GUI 側に対応表を持たない）。"""
    return make_service().formats.input_extensions()


def extension_for(format_name: str) -> str:
    """出力形式 → 既定の拡張子（GUI 側に対応表を持たない）。"""
    spec = make_service().formats.get(format_name)
    return spec.extensions[0].lstrip(".") if spec.extensions else format_name
