"""ResultPrinter and OutputSinks (design doc 11-4; Go's ``printer.go``)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any, TextIO

from yaqpy.core.model.leading import DOC_SEPARATOR_MARKER
from yaqpy.core.model.node import Node
from yaqpy.core.operators.anchors import explode_node
from yaqpy.errors import FormatError


class StreamSink:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream

    def write(self, text: str) -> None:
        self.stream.write(text)

    def finish(self) -> str | None:
        self.stream.flush()
        return None


class MemorySink:
    def __init__(self) -> None:
        self.buffer = io.StringIO()

    def write(self, text: str) -> None:
        self.buffer.write(text)

    def finish(self) -> str | None:
        return self.buffer.getvalue()


class InPlaceSink(MemorySink):
    """Buffers output; the service writes it to ``path`` atomically on success."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path


class ResultPrinter:
    def __init__(self, encoder: Any, sink: Any, *, nul_separated: bool = False,
                 max_depth: int = 1000, fix_merge: bool = False) -> None:
        self.encoder = encoder
        self.sink = sink
        self.nul_separated = nul_separated
        self.max_depth = max_depth
        self.fix_merge = fix_merge
        self.first_time = True
        self.previous_doc = 0
        self.previous_file = 0
        self.printed_anything = False

    def print_results(self, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        if not self.encoder.can_handle_aliases():
            for node in nodes:
                explode_node(node, fix_merge=self.fix_merge, max_depth=self.max_depth)
        if self.first_time:
            self.previous_doc = nodes[0].document()
            self.previous_file = nodes[0].get_file_index()
            self.first_time = False
        for node in nodes:
            starts_with_separator = node.leading_content.startswith(DOC_SEPARATOR_MARKER)
            if (self.previous_doc != node.document() or self.previous_file != node.get_file_index()) \
                    and not starts_with_separator:
                buf = io.StringIO()
                self.encoder.print_document_separator(buf)
                self.sink.write(buf.getvalue())
            buf = io.StringIO()
            self.encoder.print_leading_content(buf, node.leading_content)
            self._print_node(node, buf)
            text = buf.getvalue()
            if self.nul_separated:
                text = _remove_last_eol(text)
                if "\0" in text:
                    raise FormatError(
                        "can't serialise value because it contains NUL char and you are using "
                        "NUL separated output")
                text += "\0"
            self.sink.write(text)
            self.previous_doc = node.document()
            self.previous_file = node.get_file_index()

    def _print_node(self, node: Node, out: TextIO) -> None:
        if node.tag != "!!null" and (node.tag != "!!bool" or node.value != "false"):
            self.printed_anything = True
        self.encoder.encode(out, node)


def _remove_last_eol(text: str) -> str:
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith(("\n", "\r")):
        return text[:-1]
    return text
