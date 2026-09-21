"""TOML decoder / encoder (yq-compatible conversion; a TOML 1.0 parser of our own).

Why not ``tomllib``: it hands back Python values, so ``0xDEADBEEF`` becomes a decimal number,
an inline table cannot be told from a ``[table]`` and an empty table from an empty inline one.
The Go yq keeps all of that (the raw text of every number and date, and whether a table was
written inline or as a section), and it is what makes ``yaqpy '.a = 1' pyproject.toml`` come out
looking like the input. So this module parses TOML itself and builds ``Node`` trees:

* strings are ``!!str``; integers, floats, booleans and dates keep their **original text**
  (``0xFF``, ``1_000``, ``6.626e-34``, ``1979-05-27T07:32:00-08:00``) with the tag ``!!int``,
  ``!!float``, ``!!bool`` or ``!!timestamp``;
* ``[table]`` and ``[[array.of.tables]]`` entries are maps marked ``encode_hint="block"``,
  ``{ inline = "tables" }`` are maps marked ``"inline"``; the encoder writes them back that way;
* **comments are not kept** (a later step of the plan): they are skipped while reading, so the
  CLI refuses ``-i`` on a TOML file unless ``--toml-allow-lossy`` is given.

The writer follows the Go encoder: plain values first, then ``[tables]`` and ``[[arrays of
tables]]``; a value is a table section unless it carries the ``inline`` hint.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TextIO

from yaqpy.core.model.depth import node_depth
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.options import Options

MAX_DEPTH = 200
"""Deepest nesting of arrays, inline tables and table headers (the conversion recurses)."""

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_DATETIME = re.compile(
    r"(?:\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?"
    r"|\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_INTEGER = re.compile(
    r"[+-]?(?:0|[1-9](?:_?[0-9])*)|0x[0-9A-Fa-f](?:_?[0-9A-Fa-f])*|0o[0-7](?:_?[0-7])*"
    r"|0b[01](?:_?[01])*")
_FLOAT = re.compile(
    r"[+-]?(?:0|[1-9](?:_?[0-9])*)(?:\.[0-9](?:_?[0-9])*)?(?:[eE][+-]?[0-9](?:_?[0-9])*)?"
    r"|[+-]?(?:inf|nan)")
_DELIMITERS = " \t\r\n,]}#"
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


# ============================================================================ decoder

class _Parser:
    """A recursive-descent parser for TOML 1.0 that builds ``Node`` trees (comments are skipped)."""

    def __init__(self, text: str) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.root = Node.mapping()
        self.current = self.root
        # how a table came to exist: "table" (a header), "implicit" (a header of a child),
        # "dotted" (dotted keys), "inline", or "aot" for an array of tables
        self.kinds: dict[int, str] = {id(self.root): "table"}

    # ------------------------------------------------------------------ helpers

    def error(self, message: str, at: int | None = None) -> FormatError:
        pos = self.i if at is None else at
        line = self.s.count("\n", 0, pos) + 1
        column = pos - (self.s.rfind("\n", 0, pos) + 1) + 1
        return FormatError(f"{message} (line {line}, column {column})", format="toml", line=line,
                           column=column)

    def _peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    def _skip_blanks(self) -> None:
        """Spaces and tabs."""
        s, n = self.s, self.n
        while self.i < n and s[self.i] in " \t":
            self.i += 1

    def _skip_comment(self) -> None:
        if self._peek() == "#":
            end = self.s.find("\n", self.i)
            self.i = self.n if end < 0 else end

    def _skip_space_lines_comments(self) -> None:
        """Blanks, newlines and comments (between expressions and inside arrays)."""
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in " \t\n":
                self.i += 1
            elif c == "\r" and s.startswith("\r\n", self.i):
                self.i += 2
            elif c == "#":
                self._skip_comment()
            else:
                break

    def _end_of_expression(self) -> None:
        self._skip_blanks()
        self._skip_comment()
        if self.i >= self.n:
            return
        if self.s.startswith("\r\n", self.i):
            self.i += 2
        elif self.s[self.i] == "\n":
            self.i += 1
        else:
            raise self.error("expected a new line after the value")

    # ------------------------------------------------------------------ keys

    def _key(self) -> list[str]:
        parts: list[str] = []
        while True:
            self._skip_blanks()
            c = self._peek()
            if c == '"':
                self.i += 1
                parts.append(self._basic_string(multiline=False))
            elif c == "'":
                self.i += 1
                parts.append(self._literal_string(multiline=False))
            else:
                m = _BARE_KEY.match(self.s, self.i)
                if m is None:
                    raise self.error("invalid or missing key")
                parts.append(m.group())
                self.i = m.end()
            self._skip_blanks()
            if self._peek() == ".":
                self.i += 1
                continue
            return parts

    # ------------------------------------------------------------------ strings

    def _basic_string(self, *, multiline: bool) -> str:
        """After the opening quote(s). Escapes are decoded."""
        s = self.s
        out: list[str] = []
        start = self.i - (3 if multiline else 1)         # the opening quote(s), for error messages
        if multiline:
            if s.startswith("\r\n", self.i):
                self.i += 2
            elif s.startswith("\n", self.i):
                self.i += 1
        while True:
            if self.i >= self.n:
                raise self.error("unterminated multi-line basic string" if multiline
                                 else "unterminated basic string", start)
            c = s[self.i]
            if c == '"':
                if not multiline:
                    self.i += 1
                    return "".join(out)
                if s.startswith('"""', self.i):
                    quotes = 3
                    while s.startswith('"', self.i + quotes) and quotes < 5:
                        quotes += 1
                    out.append('"' * (quotes - 3))
                    self.i += quotes
                    return "".join(out)
                out.append(c)
                self.i += 1
            elif c == "\\":
                self.i += 1
                out.append(self._escape(multiline))
            elif c == "\n" or (c == "\r" and s.startswith("\r\n", self.i)):
                if not multiline:
                    raise self.error("unterminated basic string", start)
                out.append("\n")
                self.i += 2 if c == "\r" else 1
            elif c < " " and c != "\t" or c == "\x7f":
                raise self.error("control characters are not allowed in a string")
            else:
                out.append(c)
                self.i += 1

    def _escape(self, multiline: bool) -> str:
        s = self.s
        if self.i >= self.n:
            raise self.error("unterminated basic string")
        c = s[self.i]
        if c in _ESCAPES:
            self.i += 1
            return _ESCAPES[c]
        if c in "uU":
            width = 4 if c == "u" else 8
            digits = s[self.i + 1:self.i + 1 + width]
            if len(digits) != width or any(d not in "0123456789abcdefABCDEF" for d in digits):
                raise self.error("invalid unicode escape")
            code = int(digits, 16)
            if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
                raise self.error("invalid unicode scalar value in escape")
            self.i += 1 + width
            return chr(code)
        if multiline and c in " \t\r\n":
            # a backslash at the end of a line trims the line break and the blanks after it
            j = self.i
            while j < self.n and s[j] in " \t":
                j += 1
            if j < self.n and (s[j] == "\n" or s.startswith("\r\n", j)):
                while j < self.n and s[j] in " \t\r\n":
                    j += 1
                self.i = j
                return ""
        raise self.error(f"invalid escape sequence \\{c}")

    def _literal_string(self, *, multiline: bool) -> str:
        s = self.s
        start = self.i - (3 if multiline else 1)
        if multiline:
            if s.startswith("\r\n", self.i):
                self.i += 2
            elif s.startswith("\n", self.i):
                self.i += 1
            end = s.find("'''", self.i)
            if end < 0:
                raise self.error("unterminated multi-line literal string", start)
            extra = 0
            while extra < 2 and s.startswith("'", end + 3 + extra):
                extra += 1                    # up to two quotes before the closing ''' belong to the text
            end += extra
            text = s[self.i:end]
            self.i = end + 3
        else:
            end = self.i
            while end < self.n and s[end] not in "'\n":
                end += 1
            if end >= self.n or s[end] != "'":
                raise self.error("unterminated literal string", start)
            text = s[self.i:end]
            self.i = end + 1
        if "\r\n" in text:
            text = text.replace("\r\n", "\n")
        for ch in text:
            if ch < " " and ch not in "\t\n" or ch == "\x7f":
                raise self.error("control characters are not allowed in a string")
        return text

    # ------------------------------------------------------------------ values

    def _value(self, depth: int) -> Node:
        if depth >= MAX_DEPTH:
            raise self.error(f"nesting is deeper than {MAX_DEPTH} levels")
        s = self.s
        c = self._peek()
        if c == '"':
            if s.startswith('"""', self.i):
                self.i += 3
                return _string(self._basic_string(multiline=True))
            self.i += 1
            return _string(self._basic_string(multiline=False))
        if c == "'":
            if s.startswith("'''", self.i):
                self.i += 3
                return _string(self._literal_string(multiline=True))
            self.i += 1
            return _string(self._literal_string(multiline=False))
        if c == "[":
            return self._array(depth)
        if c == "{":
            return self._inline_table(depth)
        if c == "":
            raise self.error("expected a value")
        return self._scalar()

    def _scalar(self) -> Node:
        s = self.s
        start = self.i
        for word in ("true", "false"):
            if s.startswith(word, start) and (start + len(word) >= self.n
                                              or s[start + len(word)] in _DELIMITERS):
                self.i += len(word)
                return Node(Kind.SCALAR, tag="!!bool", value=word)
        m = _DATETIME.match(s, start)
        if m is not None and (m.end() >= self.n or s[m.end()] in _DELIMITERS):
            self.i = m.end()
            text = m.group()
            tag = "!!timestamp" if text[4:5] == "-" else "!!str"       # a bare time is no timestamp
            return Node(Kind.SCALAR, tag=tag, value=text)
        end = start
        while end < self.n and s[end] not in _DELIMITERS:
            end += 1
        token = s[start:end]
        if token == "":
            raise self.error("expected a value")
        if _INTEGER.fullmatch(token):
            self.i = end
            return Node(Kind.SCALAR, tag="!!int", value=token)
        if _FLOAT.fullmatch(token):
            self.i = end
            return Node(Kind.SCALAR, tag="!!float", value=token)
        raise self.error(f"invalid value {token[:30]!r}")

    def _array(self, depth: int) -> Node:
        self.i += 1
        seq = Node.sequence()
        while True:
            self._skip_space_lines_comments()
            if self._peek() == "]":
                self.i += 1
                return seq
            _append_item(seq, self._value(depth + 1))
            self._skip_space_lines_comments()
            c = self._peek()
            if c == ",":
                self.i += 1
            elif c == "]":
                self.i += 1
                return seq
            else:
                raise self.error("expected ',' or ']' in an array")

    def _inline_table(self, depth: int) -> Node:
        self.i += 1
        table = Node.mapping()
        table.encode_hint = "inline"
        self.kinds[id(table)] = "inline"
        self._skip_blanks()
        if self._peek() == "}":
            self.i += 1
            return table
        while True:
            self._keyval(table, depth + 1)
            self._skip_blanks()
            c = self._peek()
            if c == ",":
                self.i += 1
                self._skip_blanks()
            elif c == "}":
                self.i += 1
                return table
            elif c in ("\n", "\r"):
                raise self.error("a new line is not allowed in an inline table")
            else:
                raise self.error("expected ',' or '}' in an inline table")

    # ------------------------------------------------------------------ key/value and tables

    def _keyval(self, table: Node, depth: int) -> None:
        keys = self._key()
        self._skip_blanks()
        if self._peek() != "=":
            raise self.error("expected '=' after the key")
        self.i += 1
        self._skip_blanks()
        value = self._value(depth)
        node = table
        for part in keys[:-1]:
            node = self._dotted_child(node, part)
        if node.get_map_value(keys[-1]) is not None:
            raise self.error(f"the key '{'.'.join(keys)}' is defined more than once")
        _append_pair(node, _string(keys[-1]), value)

    def _dotted_child(self, node: Node, part: str) -> Node:
        child = node.get_map_value(part)
        if child is None:
            child = Node.mapping()
            self.kinds[id(child)] = "dotted"
            _append_pair(node, _string(part), child)
            return child
        if child.kind is Kind.MAPPING and self.kinds.get(id(child)) == "dotted":
            return child
        raise self.error(f"the key '{part}' is already defined and cannot be extended")

    def _walk(self, parts: list[str]) -> Node:
        """The table that holds ``parts[-1]``; missing tables on the way are created implicitly."""
        if len(parts) > MAX_DEPTH:
            raise self.error(f"a table path is deeper than {MAX_DEPTH} levels")
        node = self.root
        for part in parts[:-1]:
            child = node.get_map_value(part)
            if child is None:
                child = Node.mapping()
                self.kinds[id(child)] = "implicit"
                _append_pair(node, _string(part), child)
            elif child.kind is Kind.SEQUENCE and self.kinds.get(id(child)) == "aot":
                child = child.content[-1]
            elif child.kind is not Kind.MAPPING or self.kinds.get(id(child)) == "inline":
                raise self.error(f"the key '{part}' is already defined and cannot be extended")
            node = child
        return node

    def _table_header(self) -> None:
        self.i += 1
        parts = self._key()
        if self._peek() != "]":
            raise self.error("expected ']' to close the table header")
        self.i += 1
        parent = self._walk(parts)
        name = parts[-1]
        existing = parent.get_map_value(name)
        if existing is None:
            table = Node.mapping()
            _append_pair(parent, _string(name), table)
        elif existing.kind is Kind.MAPPING and self.kinds.get(id(existing)) == "implicit":
            table = existing
        else:
            raise self.error(f"the table '{'.'.join(parts)}' is defined more than once")
        table.encode_hint = "block"
        self.kinds[id(table)] = "table"
        self.current = table

    def _array_table_header(self) -> None:
        self.i += 2
        parts = self._key()
        if not self.s.startswith("]]", self.i):
            raise self.error("expected ']]' to close the array of tables header")
        self.i += 2
        parent = self._walk(parts)
        name = parts[-1]
        existing = parent.get_map_value(name)
        if existing is None:
            seq = Node.sequence()
            self.kinds[id(seq)] = "aot"
            _append_pair(parent, _string(name), seq)
        elif existing.kind is Kind.SEQUENCE and self.kinds.get(id(existing)) == "aot":
            seq = existing
        else:
            raise self.error(f"'{'.'.join(parts)}' is already defined and is not an array of tables")
        table = Node.mapping()
        table.encode_hint = "block"
        self.kinds[id(table)] = "table"
        _append_item(seq, table)
        self.current = table

    def parse(self) -> Node:
        while True:
            self._skip_space_lines_comments()
            if self.i >= self.n:
                return self.root
            if self.s.startswith("[[", self.i):
                self._array_table_header()
            elif self.s[self.i] == "[":
                self._table_header()
            else:
                self._keyval(self.current, 0)
            self._end_of_expression()


def _string(value: str) -> Node:
    return Node(Kind.SCALAR, tag="!!str", value=value)


def _append_pair(parent: Node, key: Node, value: Node) -> None:
    key.parent = parent
    key.is_map_key = True
    value.parent = parent
    value.key = key
    parent.content.append(key)
    parent.content.append(value)


def _append_item(parent: Node, child: Node) -> None:
    key = Node.integer(len(parent.content))
    key.parent = parent
    key.is_map_key = True
    child.parent = parent
    child.key = key
    parent.content.append(child)


class TomlDecoder:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="toml", filename=filename)
        try:
            root = _Parser(text).parse()
        except RecursionError:
            raise FormatError("TOML nesting too deep", format="toml", filename=filename) from None
        except FormatError as e:
            if filename and not e.message.startswith("bad file"):
                raise FormatError(f"bad file '{filename}': {e.message}", format="toml",
                                  filename=filename, line=e.line, column=e.column) from None
            raise
        if not root.content:
            return                      # no key, no table: no document (as in the Go yq)
        root.document_index = 0
        root.filename = filename
        root.file_index = file_index
        yield root


# ============================================================================ encoder

_QUOTE_ESCAPES = {"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r", '"': '\\"',
                  "\\": "\\\\"}


def _quote(value: str) -> str:
    """A TOML basic string. (Go's ``%q`` would write ``\\a`` / ``\\x..`` which TOML does not know.)"""
    out = ['"']
    for ch in value:
        escaped = _QUOTE_ESCAPES.get(ch)
        if escaped is not None:
            out.append(escaped)
        elif ch.isprintable():
            out.append(ch)
        elif ord(ch) < 0x10000:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(f"\\U{ord(ch):08X}")
    out.append('"')
    return "".join(out)


def _key_text(key: str) -> str:
    """A bare key when it only has ASCII letters, digits, ``_`` and ``-``; otherwise quoted."""
    return key if _BARE_KEY.fullmatch(key) else _quote(key)


def _dotted(path: list[str]) -> str:
    return ".".join(_key_text(p) for p in path)


def _comment(text: str) -> str:
    """One ``# ...`` line per line of ``text`` (empty when there is no comment)."""
    if not text:
        return ""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("#"):
            line = "# " + line
        lines.append(line + "\n")
    return "".join(lines)


def _line_comment(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if not text.startswith("#"):
        text = "# " + text
    return "  " + text


def _is_array_of_tables(seq: Node) -> bool:
    return bool(seq.content) and all(
        item.kind is Kind.MAPPING and item.encode_hint != "inline" for item in seq.content)


def _is_attribute(node: Node) -> bool:
    if node.kind is Kind.SCALAR:
        return True
    return node.kind is Kind.SEQUENCE and not _is_array_of_tables(node)


def _scalar_text(node: Node) -> str:
    if node.tag == "!!str":
        return _quote(node.value)
    if node.tag == "!!null":
        return '""'                       # TOML has no null
    return node.value


def _heads(key: Node | None, value: Node) -> str:
    """The head comments above a key and above its value (a YAML comment sits on the key)."""
    return "\n".join(c for c in (key.head_comment if key is not None else "", value.head_comment) if c)


class TomlEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = False) -> None:
        self.options = options or Options()
        self.unwrap_scalar = unwrap_scalar
        self._out: list[str] = []
        self._wrote_root_attr = False
        self._leading = ""

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None

    def print_leading_content(self, out: TextIO, content: str) -> None:
        """Comment lines before the first YAML key are written as comments at the top."""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip().startswith("#")]
        self._leading = "\n".join(lines)

    def encode(self, out: TextIO, node: Node) -> None:
        if node.kind is not Kind.MAPPING:
            if node.kind is Kind.SCALAR:
                out.write(node.value + "\n")
                return
            raise FormatError("TOML encoder expects a mapping at the root level", format="toml")
        limit = min(self.options.limits.max_depth, MAX_DEPTH)
        if node_depth(node, limit + 1) > limit + 1:
            raise FormatError(f"TOML nesting too deep (more than {limit} levels)", format="toml")
        self._out = []
        self._wrote_root_attr = False
        try:
            self._root_mapping(node)
        except RecursionError:
            raise FormatError("TOML nesting too deep", format="toml") from None
        out.write("".join(self._out))

    def _w(self, text: str) -> None:
        self._out.append(text)

    # ------------------------------------------------------------------ root

    def _root_mapping(self, node: Node) -> None:
        self._w(_comment(self._leading))
        self._w(_comment(node.head_comment))
        pairs = list(node.map_items())
        for key, value in pairs:
            if _is_attribute(value):
                self._top_level_entry([key.value], value, key)
        for key, value in pairs:
            if not _is_attribute(value):
                self._top_level_entry([key.value], value, key)

    def _top_level_entry(self, path: list[str], node: Node, key_node: Node) -> None:
        key = path[-1]
        if node.kind is Kind.SCALAR:
            self._attribute(key, node, key_node)
        elif node.kind is Kind.SEQUENCE:
            if not node.content or not _is_array_of_tables(node):
                self._array_attribute(key, node, key_node)
                return
            self._array_of_tables(path, node, key_node)
        elif node.kind is Kind.MAPPING:
            if node.encode_hint == "inline":
                self._inline_attribute(key, node, key_node)
            else:
                self._separate_mapping(path, node, key_node)
        else:
            raise FormatError(f"unsupported node kind for TOML: {node.kind.name}", format="toml")

    def _array_of_tables(self, path: list[str], seq: Node, key_node: Node) -> None:
        if self._wrote_root_attr:
            self._w("\n")
            self._wrote_root_attr = False
        self._w(_comment(_heads(key_node, seq)))
        for item in seq.content:
            self._w("[[" + _dotted(path) + "]]\n")
            self._body(path, item)

    # ------------------------------------------------------------------ attributes

    def _attribute(self, key: str, value: Node, key_node: Node | None = None) -> None:
        if value.tag == "!!null":
            return
        self._wrote_root_attr = True
        self._w(_comment(_heads(key_node, value)))
        self._w(_key_text(key) + " = " + _scalar_text(value) + _line_comment(value.line_comment) + "\n")

    def _array_attribute(self, key: str, seq: Node, key_node: Node | None = None) -> None:
        self._wrote_root_attr = True
        self._w(_comment(_heads(key_node, seq)))
        if not seq.content:
            self._w(_key_text(key) + " = []" + _line_comment(seq.line_comment) + "\n")
            return
        if any(item.head_comment for item in seq.content):
            self._w(_key_text(key) + " = [\n")
            last = len(seq.content) - 1
            for i, item in enumerate(seq.content):
                for line in item.head_comment.split("\n"):
                    if line.strip():
                        line = line if line.strip().startswith("#") else "# " + line
                        self._w("  " + line + "\n")
                self._w("  " + self._array_item(item) + ",\n")
                if i < last:
                    self._w("\n")
            self._w("]\n")
            return
        items = ", ".join(self._array_item(item) for item in seq.content)
        self._w(_key_text(key) + " = [" + items + "]" + _line_comment(seq.line_comment) + "\n")

    def _array_item(self, item: Node) -> str:
        if item.kind is Kind.SCALAR:
            return _scalar_text(item)
        if item.kind is Kind.SEQUENCE:
            return self._inline_array(item)
        if item.kind is Kind.MAPPING:
            return self._inline_table(item)
        raise FormatError(f"unsupported array item kind: {item.kind.name}", format="toml")

    def _inline_array(self, seq: Node) -> str:
        return "[" + ", ".join(self._array_item(item) for item in seq.content) + "]"

    def _inline_table(self, table: Node) -> str:
        parts: list[str] = []
        for key, value in table.map_items():
            if value.kind is Kind.SCALAR:
                if value.tag == "!!null":
                    continue
                parts.append(f"{_key_text(key.value)} = {_scalar_text(value)}")
            elif value.kind is Kind.SEQUENCE:
                parts.append(f"{_key_text(key.value)} = {self._inline_array(value)}")
            elif value.kind is Kind.MAPPING:
                parts.append(f"{_key_text(key.value)} = {self._inline_table(value)}")
            else:
                raise FormatError(f"unsupported inline table value kind: {value.kind.name}",
                                  format="toml")
        return "{ " + ", ".join(parts) + " }"

    def _inline_attribute(self, key: str, table: Node, key_node: Node | None = None) -> None:
        self._w(_comment(_heads(key_node, table)))
        self._w(_key_text(key) + " = " + self._inline_table(table) + "\n")

    # ------------------------------------------------------------------ tables

    def _table_header(self, path: list[str], table: Node, key_node: Node | None) -> None:
        if self._wrote_root_attr:
            self._w("\n")
            self._wrote_root_attr = False
        self._w(_comment(_heads(key_node, table)))
        self._w("[" + _dotted(path) + "]\n")

    def _separate_mapping(self, path: list[str], table: Node, key_node: Node | None = None) -> None:
        has_attributes = False
        for _, value in table.map_items():
            if value.kind is Kind.SCALAR and value.tag != "!!null":
                has_attributes = True
            elif value.kind is Kind.MAPPING and value.encode_hint == "inline":
                has_attributes = True
            elif value.kind is Kind.SEQUENCE and not _is_array_of_tables(value):
                has_attributes = True
            if has_attributes:
                break
        if has_attributes or not table.content:
            self._table_header(path, table, key_node)
            self._body(path, table)
            return
        for key, value in table.map_items():
            sub = path + [key.value]
            if value.kind is Kind.MAPPING:
                self._separate_mapping(sub, value, key)
            elif value.kind is Kind.SEQUENCE:
                if _is_array_of_tables(value):
                    self._array_of_tables(sub, value, key)
                else:
                    self._array_attribute(key.value, value, key)
            elif value.kind is Kind.SCALAR:
                self._attribute(key.value, value, key)

    def _body(self, path: list[str], table: Node) -> None:
        """The attributes of a table, then its arrays of tables, then its sub-tables."""
        for key, value in table.map_items():
            if value.kind is Kind.SCALAR:
                self._attribute(key.value, value, key)
            elif value.kind is Kind.MAPPING:
                if value.encode_hint == "inline":
                    self._inline_attribute(key.value, value, key)
            elif value.kind is Kind.SEQUENCE and not _is_array_of_tables(value):
                self._array_attribute(key.value, value, key)
        for key, value in table.map_items():
            if value.kind is Kind.SEQUENCE and _is_array_of_tables(value):
                sub = path + [key.value]
                self._w(_comment(_heads(key, value)))
                for item in value.content:
                    self._w("[[" + _dotted(sub) + "]]\n")
                    self._body(sub, item)
        for key, value in table.map_items():
            if value.kind is Kind.MAPPING and value.encode_hint != "inline":
                self._separate_mapping(path + [key.value], value, key)
