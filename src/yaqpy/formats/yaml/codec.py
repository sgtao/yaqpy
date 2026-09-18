"""YamlDecoder / YamlEncoder: glue between text and the parser/emitter."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TextIO

from yaqpy.core.model.leading import DOC_SEPARATOR_MARKER, render_leading_content
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.formats.yaml.emitter import emit_document
from yaqpy.formats.yaml.parser import parse_documents
from yaqpy.options import Options

_COMMENT_LINE = re.compile(r"^\s*#")
_DIRECTIVE_LINE = re.compile(r"^\s*%YAML")
_SEPARATOR_LINE = re.compile(r"^\s*---\s*$")
_SEPARATOR_PREFIX = re.compile(r"^\s*---\s+")


def preprocess_leading_content(text: str) -> tuple[str, str]:
    """Go's ``processReadStream``: split off comments/blank lines/directives/``---``
    that appear before the first content line. Returns (leading, remainder)."""
    leading: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        nl = text.find("\n", pos)
        if nl < 0:
            line, newline, nxt = text[pos:], "", n
        else:
            line, newline, nxt = text[pos:nl], "\n", nl + 1
        if line.endswith("\r"):
            line = line[:-1]
            newline = "\r\n" if newline else ""
        trimmed = line.strip()
        if _SEPARATOR_LINE.match(trimmed):
            leading.append(DOC_SEPARATOR_MARKER + newline)
            pos = nxt
            continue
        m = _SEPARATOR_PREFIX.match(line)
        if m:
            remainder = line[m.end():]
            leading.append(DOC_SEPARATOR_MARKER + (newline or "\n"))
            return "".join(leading), remainder + newline + text[nxt:]
        if _COMMENT_LINE.match(line) or _DIRECTIVE_LINE.match(line) or trimmed == "":
            leading.append(line + newline)
            pos = nxt
            continue
        return "".join(leading), text[pos:]
    return "".join(leading), ""


class YamlDecoder:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.anchors: dict[str, Node] = {}

    def decode_snippet(self, text: str) -> Node:
        """Decode a single value (used by ``env()`` and tag guessing)."""
        docs = list(self.decode_documents(text, process_leading=False))
        if not docs:
            return Node.null(value="")
        return docs[0]

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="yaml", filename=filename)
        leading = ""
        body = text
        if process_leading and self.options.yaml.leading_content_preprocessing:
            leading, body = preprocess_leading_content(text)
        line_offset = leading.count("\n")
        try:
            documents = parse_documents(body, filename=filename, line_offset=line_offset,
                                        max_depth=self.options.limits.max_depth,
                                        anchors=self.anchors)
        except RecursionError:
            raise FormatError("document nesting too deep", format="yaml", filename=filename) from None
        if not documents:
            if leading != "" or (not process_leading and text.strip() != "" and _only_comments(text)):
                node = Node.null(value="")
                node.leading_content = leading if leading else text
                node.filename = filename
                node.file_index = file_index
                node.document_index = 0
                yield node
            return
        for index, doc in enumerate(documents):
            doc.document_index = index
            doc.filename = filename
            doc.file_index = file_index
            if index == 0 and leading:
                doc.leading_content = leading
            yield doc


def _only_comments(text: str) -> bool:
    return all(line.strip() == "" or line.lstrip().startswith("#") for line in text.split("\n"))


class YamlEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = True) -> None:
        self.options = options or Options()
        self.unwrap_scalar = unwrap_scalar
        self.indent = self.options.indent
        self.print_doc_separators = self.options.yaml.print_doc_separators
        self.compact_seq = self.options.yaml.compact_sequence_indent

    def can_handle_aliases(self) -> bool:
        return True

    def print_document_separator(self, out: TextIO) -> None:
        if self.print_doc_separators:
            out.write("---\n")

    def print_leading_content(self, out: TextIO, content: str) -> None:
        out.write(render_leading_content(content, print_doc_separators=self.print_doc_separators))

    def encode(self, out: TextIO, node: Node) -> None:
        line_ending = "\r\n" if "\r\n" in node.leading_content else "\n"
        if node.kind is Kind.SCALAR and self.unwrap_scalar:
            value = node.value
            if node.leading_content == "" or value != "":
                value += line_ending
            out.write(value)
            return
        text = emit_document(node, indent=self.indent, compact_sequence_indent=self.compact_seq)
        if line_ending == "\r\n":
            text = text.replace("\n", "\r\n")
        out.write(text)

    def encode_to_string(self, node: Node) -> str:
        import io

        buf = io.StringIO()
        self.encode(buf, node)
        return buf.getvalue()
