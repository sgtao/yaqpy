"""Java properties input and output (design doc 9-2; the input follows yq with magiconair/properties)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TextIO

from yaqpy.core.model.leading import DOC_SEPARATOR_MARKER
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.formats.base import DecodeBudget
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
                if lines:
                    lines.append("")           # a comment block is set apart (magiconair's WriteComment)
                for line in comments.strip().split("\n"):
                    lines.append("# " + line.strip())
            if node.tag == "!!null":
                return
            value = node.value
            if not self.unwrap_scalar and " " in value:
                value = _go_quote(value)      # -r=false: values with a space are written quoted
            lines.append(f"{_escape_key(path)}{self.separator}{_escape_value(value)}")
        elif node.kind is Kind.SEQUENCE:
            for i, child in enumerate(node.content):
                self._encode(lines, child, self._append_path(path, i), None)
        elif node.kind is Kind.MAPPING:
            for key, value in node.map_items():
                self._encode(lines, value, self._append_path(path, key.value), key)
        else:
            raise FormatError(f"unsupported node {node.tag}", format="props")


# ============================================================================ quoting (-r=false)

_QUOTE_ESCAPES = {"\a": "\\a", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t",
                  "\v": "\\v", '"': '\\"', "\\": "\\\\"}


def _go_quote(value: str) -> str:
    """Go's ``%q``: a double-quoted string with escapes for control and unprintable characters."""
    out = ['"']
    for ch in value:
        escaped = _QUOTE_ESCAPES.get(ch)
        if escaped is not None:
            out.append(escaped)
        elif ch.isprintable():
            out.append(ch)
        elif ord(ch) < 0x100:
            out.append(f"\\x{ord(ch):02x}")
        elif ord(ch) < 0x10000:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(f"\\U{ord(ch):08x}")
    out.append('"')
    return "".join(out)


# ============================================================================ reading

MAX_ARRAY_INDEX = 100_000
"""Largest array index a key may use (``a.99999999 = x`` would otherwise allocate that many nulls)."""

MAX_PATH_DEPTH = 200
"""Deepest key path (number of dot-separated parts) that is accepted."""

_BLANKS = " \t\f"
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_INT_SEGMENT = re.compile(r"[+-]?[0-9]+")
_SIMPLE_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def _unescape(text: str) -> str:
    """Escapes of a properties file: ``\\t \\n \\r \\f``, ``\\uXXXX``; ``\\x`` is just ``x``."""
    if "\\" not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break                           # a lone backslash at the very end is dropped
        c = text[i]
        i += 1
        if c == "u":
            digits = text[i:i + 4]
            if len(digits) != 4 or any(d not in "0123456789abcdefABCDEF" for d in digits):
                raise FormatError("properties: invalid unicode literal", format="props")
            out.append(chr(int(digits, 16)))
            i += 4
        else:
            out.append(_SIMPLE_ESCAPES.get(c, c))
    return "".join(out)


def _odd_backslashes(line: str) -> bool:
    count = len(line) - len(line.rstrip("\\"))
    return count % 2 == 1


def _split_key_value(line: str) -> tuple[str, str]:
    """The key ends at the first unescaped ``=``, ``:`` or blank; the value follows the separator."""
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c in "=:" or c in _BLANKS:
            break
        i += 1
    key = line[:min(i, n)]
    while i < n and line[i] in _BLANKS:
        i += 1
    if i < n and line[i] in "=:":
        i += 1
        while i < n and line[i] in _BLANKS:
            i += 1
    return _unescape(key), _unescape(line[i:])


def parse_properties(text: str,
                     budget: DecodeBudget | None = None) -> list[tuple[str, str, list[str]]]:
    """``(key, value, comments)`` for every property, in the order the keys first appear.

    Comment lines (``#`` or ``!``) belong to the next property. A later definition of the same key
    replaces the value. Lines may continue with a trailing backslash.
    """
    entries: dict[str, tuple[str, list[str]]] = {}
    comments: list[str] = []
    lines = _LINE_BREAK.split(text)
    i = 0
    while i < len(lines):
        if budget is not None:
            budget.tick()
        line = lines[i].lstrip(_BLANKS)
        i += 1
        if line == "":
            continue
        if line[0] in "#!":
            comments.append(line[1:].lstrip(_BLANKS))
            continue
        while _odd_backslashes(line):
            if i >= len(lines):
                line = line[:-1]
                break
            line = line[:-1] + lines[i].lstrip(_BLANKS)
            i += 1
        key, value = _split_key_value(line)
        previous = entries.get(key)
        entries[key] = (value, comments if comments else (previous[1] if previous else []))
        comments = []
    return [(key, value, remarks) for key, (value, remarks) in entries.items()]


def _bracket_segment(segment: str) -> list[str | int] | None:
    """``name[0][1]`` -> ``["name", 0, 1]``; None when the segment is not of that form."""
    path: list[str | int] = []
    start = segment.index("[")
    if start > 0:
        path.append(segment[:start])
    rest = segment[start:]
    while rest:
        if not rest.startswith("["):
            return None
        end = rest.find("]")
        if end < 0:
            return None
        inner = rest[1:end]
        if not _INT_SEGMENT.fullmatch(inner) or not -(2 ** 31) <= int(inner) < 2 ** 31:
            return None
        path.append(int(inner))
        rest = rest[end + 1:]
    return path


def parse_key(key: str, *, array_brackets: bool) -> list[str | int]:
    """The key as a path: ``a.b.0`` -> ``["a", "b", 0]`` (with ``a.b[0]`` when brackets are on)."""
    path: list[str | int] = []
    for segment in key.split("."):
        if array_brackets and "[" in segment:
            bracketed = _bracket_segment(segment)
            if bracketed is not None:
                path.extend(bracketed)
                continue
        if _INT_SEGMENT.fullmatch(segment) and 0 <= int(segment) < 2 ** 31:
            path.append(int(segment))
        else:
            path.append(segment)
    return path


def _str_node(value: str) -> Node:
    return Node(Kind.SCALAR, tag="!!str", value=value)


def _link_pair(parent: Node, key: Node, value: Node) -> None:
    key.parent = parent
    key.is_map_key = True
    value.parent = parent
    value.key = key
    parent.content.extend((key, value))


def _new_container(next_segment: str | int) -> Node:
    return Node.sequence() if isinstance(next_segment, int) else Node.mapping()


def _refuse(path: list[str | int], held_at: int, reason: str) -> FormatError:
    full = ".".join(str(p) for p in path)
    where = ".".join(str(p) for p in path[:held_at + 1])
    return FormatError(f"properties: cannot set '{full}': '{where}' {reason}", format="props")


def _assign(root: Node, path: list[str | int], value: Node, comment: str) -> None:
    """Set ``path`` to ``value``, creating maps and lists on the way (Go's ``DeeplyAssign``).

    An integer part indexes a list (padded with nulls); a name part indexes a map. ``comment`` is
    put above the key (in a map) or above the item (in a list).
    """
    node = root
    for depth, segment in enumerate(path):
        last = depth == len(path) - 1
        if node.kind is Kind.MAPPING:
            name = str(segment)
            existing = node.get_map_value(name)
            if existing is None:
                key = _str_node(name)
                key.head_comment = comment if last else ""
                child = value if last else _new_container(path[depth + 1])
                _link_pair(node, key, child)
            else:
                index = node.content.index(existing)
                key = node.content[index - 1]
                if last:
                    if comment:
                        key.head_comment = comment
                    value.parent, value.key = node, key
                    node.content[index] = value
                    child = value
                else:
                    child = existing
                    if child.kind not in (Kind.MAPPING, Kind.SEQUENCE):
                        raise _refuse(path, depth, "already has a value")
        elif node.kind is Kind.SEQUENCE:
            if not isinstance(segment, int):
                raise _refuse(path, depth - 1, f"is a list, so '{segment}' is not a valid index")
            if segment > MAX_ARRAY_INDEX:
                raise FormatError(f"properties: array index {segment} is too large "
                                  f"(the limit is {MAX_ARRAY_INDEX})", format="props")
            while len(node.content) <= segment:
                pad = Node(Kind.SCALAR, tag="!!null", value="null")
                pad.parent = node
                pad.key = Node.integer(len(node.content))
                pad.key.parent = node
                pad.key.is_map_key = True
                node.content.append(pad)
            existing = node.content[segment]
            if last:
                value.parent, value.key = node, existing.key
                if comment:
                    value.head_comment = comment
                node.content[segment] = value
                child = value
            elif existing.kind in (Kind.MAPPING, Kind.SEQUENCE):
                child = existing
            elif existing.tag == "!!null":
                child = _new_container(path[depth + 1])
                child.parent, child.key = node, existing.key
                node.content[segment] = child
            else:
                raise _refuse(path, depth, "already has a value")
        else:
            raise _refuse(path, max(depth - 1, 0), "is not a map or a list")
        node = child


class PropertiesDecoder:
    """Java ``.properties`` -> nested maps and lists (values stay strings).

    ``a.b.c = x`` becomes ``a: {b: {c: x}}``; a numeric part (``pets.0``, or ``pets[0]`` with
    ``--properties-array-brackets``) makes a list. The comment lines above a property become the
    head comment of its key. ``${...}`` is not expanded.
    """

    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.array_brackets = self.options.props.use_array_brackets

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True,
                         budget: DecodeBudget | None = None) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="props", filename=filename)
        if text == "":
            return
        root = Node.mapping()
        try:
            for key, value, comments in parse_properties(text, budget):
                path = parse_key(key, array_brackets=self.array_brackets)
                if len(path) > MAX_PATH_DEPTH:
                    raise FormatError(f"properties: the key '{key[:40]}...' is nested more than "
                                      f"{MAX_PATH_DEPTH} levels deep", format="props")
                comment = "# " + "\n".join(comments) if comments else ""
                _assign(root, path, _str_node(value), comment)
        except FormatError as e:
            if filename and not e.message.startswith("bad file"):
                raise FormatError(f"bad file '{filename}': {e.message}", format="props",
                                  filename=filename) from None
            raise
        root.document_index = 0
        root.filename = filename
        root.file_index = file_index
        yield root
