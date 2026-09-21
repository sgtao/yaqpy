"""Decoder / Encoder protocols (design doc 9-1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, TextIO

from yaqpy.core.model.node import Node


class Decoder(Protocol):
    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True) -> Iterator[Node]: ...


class Encoder(Protocol):
    def can_handle_aliases(self) -> bool: ...
    def print_document_separator(self, out: TextIO) -> None: ...
    def print_leading_content(self, out: TextIO, content: str) -> None: ...
    def encode(self, out: TextIO, node: Node) -> None: ...


def node_depth(root: Node, limit: int) -> int:
    """Nesting depth of a node tree (stops early once ``limit`` is exceeded)."""
    deepest = 0
    stack = [(root, 1)]
    while stack:
        node, level = stack.pop()
        deepest = max(deepest, level)
        if deepest > limit:
            return deepest
        for child in node.content:
            stack.append((child, level + 1))
    return deepest
