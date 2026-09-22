"""Decoder / Encoder protocols (design doc 9-1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, TextIO

from yaqpy.core.model.node import Node


class DecodeBudget(Protocol):
    """``StepBudget`` の最小の形（``formats`` は ``core.engine`` を import してはいけない。

    アーキテクチャ検査（``tests/unit/test_architecture.py``）どおり、構造的部分型で受ける。
    """

    def tick(self) -> None: ...


class Decoder(Protocol):
    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True,
                         budget: DecodeBudget | None = None) -> Iterator[Node]: ...


class Encoder(Protocol):
    def can_handle_aliases(self) -> bool: ...
    def print_document_separator(self, out: TextIO) -> None: ...
    def print_leading_content(self, out: TextIO, content: str) -> None: ...
    def encode(self, out: TextIO, node: Node) -> None: ...
