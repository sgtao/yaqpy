"""Java properties output (design doc 9-2; input is phase 2)."""

from __future__ import annotations

from typing import TextIO

from yaqpy.core.model.leading import DOC_SEPARATOR_MARKER
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.options import Options


def _comment_text(node: Node) -> str:
    return node.head_comment.replace("#", "", 1) + node.line_comment.replace("#", "", 1)


def _escape_value(value: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\f":
            out.append("\\f")
        elif ch == " " and i == 0:
            out.append("\\ ")
        elif ord(ch) < 0x20 or ord(ch) > 0x7E:
            if ord(ch) > 0xFFFF:
                out.append(ch)
            else:
                out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def _escape_key(key: str) -> str:
    return _escape_value(key).replace(" ", "\\ ").replace("=", "\\=").replace(":", "\\:")


class PropertiesEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = True) -> None:
        self.options = options or Options()
        self.separator = self.options.props.key_value_separator
        self.array_brackets = self.options.props.use_array_brackets
        self.unwrap_scalar = unwrap_scalar

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None

    def print_leading_content(self, out: TextIO, content: str) -> None:
        for line in content.splitlines(keepends=True):
            if DOC_SEPARATOR_MARKER in line:
                continue
            out.write(line)
        if content and not content.endswith("\n"):
            out.write("\n")

    def encode(self, out: TextIO, node: Node) -> None:
        if node.kind is Kind.SCALAR:
            out.write(node.value + "\n")
            return
        lines: list[str] = []
        self._encode(lines, node, "", None)
        out.write("\n".join(lines) + ("\n" if lines else ""))

    def _append_path(self, path: str, key: str | int) -> str:
        if path == "":
            return str(key)
        if isinstance(key, int) and self.array_brackets:
            return f"{path}[{key}]"
        return f"{path}.{key}"

    def _encode(self, lines: list[str], node: Node, path: str, key_node: Node | None) -> None:
        comments = ""
        if key_node is not None:
            comments = _comment_text(key_node)
        comments += _comment_text(node)
        node = node.resolve_alias()
        if node.kind is Kind.SCALAR:
            if comments.strip():
                for line in comments.strip().split("\n"):
                    lines.append("# " + line.strip())
            if node.tag == "!!null":
                return
            lines.append(f"{_escape_key(path)}{self.separator}{_escape_value(node.value)}")
        elif node.kind is Kind.SEQUENCE:
            for i, child in enumerate(node.content):
                self._encode(lines, child, self._append_path(path, i), None)
        elif node.kind is Kind.MAPPING:
            for key, value in node.map_items():
                self._encode(lines, value, self._append_path(path, key.value), key)
        else:
            raise FormatError(f"unsupported node {node.tag}", format="props")
