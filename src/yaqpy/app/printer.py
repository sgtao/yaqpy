"""ResultPrinter and OutputSinks (design doc 11-4; Go's ``printer.go``)."""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from typing import Any, TextIO

from yaqpy.app.ports import FileSystemPort
from yaqpy.core.engine import Context, Navigator
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


_HAS_EXTENSION = re.compile(r"\.[a-zA-Z0-9]+\Z")
# Go's default is .yml for every format except these
_SPLIT_EXTENSIONS = {"yaml": "yml", "props": "properties"}


class _SplitFile(MemorySink):
    """The text of one result; ``close`` writes it to its file."""

    def __init__(self, fs: FileSystemPort, path: str) -> None:
        super().__init__()
        self.fs = fs
        self.path = path

    def close(self) -> None:
        self.fs.write_file(self.path, self.buffer.getvalue())


class SplitWriter:
    """Go's ``multiPrintWriter`` (``-s``): every printed result goes to a file of its own.

    The file name is the value of ``expression`` evaluated against the result, with ``$index``
    counting the results. Directories are created. A name without an extension gets one that
    fits the output format. A name with a ``..`` part is refused: the name comes from the data,
    and a document must not be able to write outside the tree the expression names.
    """

    def __init__(self, fs: FileSystemPort, navigator: Navigator, expression: Any,
                 output_format: str) -> None:
        self.fs = fs
        self.navigator = navigator
        self.expression = expression
        self.extension = _SPLIT_EXTENSIONS.get(output_format, output_format)
        self.index = 0

    def open(self, node: Node) -> _SplitFile:
        context = Context((node,), {"index": (Node.integer(self.index),)})
        result = self.navigator.evaluate(context, self.expression.root)
        name = result.nodes[0].value if result.nodes else ""
        if "\0" in name or ".." in re.split(r"[\\/]", name):
            raise FormatError(f"refusing to write to [{name}]: split file names must not contain '..'")
        if not _HAS_EXTENSION.search(name):
            name = f"{name}.{self.extension}"
        self.index += 1
        return _SplitFile(self.fs, name)


class ResultPrinter:
    def __init__(self, encoder: Any, sink: Any, *, nul_separated: bool = False,
                 max_depth: int = 1000, fix_merge: bool = False,
                 split: SplitWriter | None = None) -> None:
        self.encoder = encoder
        self.sink = sink
        self.split = split
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
            sink = self.sink if self.split is None else self.split.open(node)
            starts_with_separator = node.leading_content.startswith(DOC_SEPARATOR_MARKER)
            if (self.previous_doc != node.document() or self.previous_file != node.get_file_index()) \
                    and not starts_with_separator:
                buf = io.StringIO()
                self.encoder.print_document_separator(buf)
                sink.write(buf.getvalue())
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
            sink.write(text)
            if self.split is not None:
                sink.close()
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
