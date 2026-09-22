"""TOON (Token-Oriented Object Notation) encoder and decoder, spec v4.1 (2026-07-26).

Standard library only. TOON has no comments in its data model: the spec says
decoders MUST drop ``#`` comment lines and encoders MUST NOT emit them, so
YAML comments are lost on the way to TOON, exactly like JSON output.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import TextIO

from yaqpy.core.model import tags
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import FormatError
from yaqpy.formats.base import DecodeBudget
from yaqpy.options import Options

DELIMITERS = {",": "", "\t": "\t", "|": "|"}          # delimiter -> header symbol
_UNQUOTED_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_NUMERIC_LIKE_RE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)
_LITERALS = {"true", "false", "null"}


class ToonError(FormatError):
    code = "toon"

    def __init__(self, message: str, *, line: int = 0, filename: str = "") -> None:
        super().__init__(message, format="toon", filename=filename, line=line)

    def __str__(self) -> str:
        if self.line:
            return f"line {self.line}: {self.message}"
        return self.message


# =============================================================================
# scalars
# =============================================================================

def _escape(text: str) -> str:
    out: list[str] = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _needs_quotes(text: str, delimiter: str) -> bool:
    if text == "" or text != text.strip(" \t\r\n"):
        return True
    if text in _LITERALS or _NUMERIC_LIKE_RE.match(text):
        return True
    if any(c in text for c in ':"\\[]{}') or delimiter in text:
        return True
    if any(ord(c) < 0x20 for c in text):
        return True
    return text.startswith(("-", "#"))


def encode_string(text: str, delimiter: str) -> str:
    return _escape(text) if _needs_quotes(text, delimiter) else text


def encode_key(key: str) -> str:
    return key if _UNQUOTED_KEY_RE.match(key) else _escape(key)


def canonical_number(value: float | int) -> str:
    """Spec §2 canonical form: no exponent for 0 or 1e-6 <= |n| < 1e21, no trailing zeros."""
    if isinstance(value, int):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("non-finite number")
    if value == 0:
        return "0"
    magnitude = abs(value)
    text = repr(value)
    if 1e-6 <= magnitude < 1e21:
        plain = format(Decimal(text), "f")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        return plain
    mantissa, _, exponent = text.partition("e")
    if exponent == "":
        return text
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    sign = "-" if exponent.startswith("-") else "+"
    digits = exponent.lstrip("+-").lstrip("0") or "0"
    return f"{mantissa}e{sign}{digits}"


def scalar_text(node: Node, delimiter: str) -> str:
    tag = node.guess_tag()
    value = node.value
    if tag == "!!null":
        return "null"
    if tag == "!!bool":
        return "true" if node.is_truthy() else "false"
    if tag == "!!int":
        try:
            return str(tags.parse_int(value)[1])
        except ValueError:
            return encode_string(value, delimiter)
    if tag == "!!float":
        try:
            number = tags.parse_float(value)
            return canonical_number(number)
        except ValueError:
            return encode_string(value, delimiter)
    return encode_string(value, delimiter)


# =============================================================================
# encoder
# =============================================================================

def _resolve(node: Node) -> Node:
    return node.resolve_alias() if node.kind is Kind.ALIAS else node


def _is_primitive(node: Node) -> bool:
    return _resolve(node).kind is Kind.SCALAR


def _key_set(node: Node) -> tuple[str, ...]:
    return tuple(k.value for k, _ in node.map_items())


def _column_kind(values: list[Node]) -> str | None:
    """'primitive' if every value is a scalar, 'nested' if every value is a non-empty
    mapping with the same key set whose columns are uniform too, else None."""
    if all(_is_primitive(v) for v in values):
        return "primitive"
    resolved = [_resolve(v) for v in values]
    if not all(v.kind is Kind.MAPPING and v.content for v in resolved):
        return None
    keys = _key_set(resolved[0])
    if any(set(_key_set(v)) != set(keys) or len(_key_set(v)) != len(keys) for v in resolved):
        return None
    for key in keys:
        column = [v.get_map_value(key) for v in resolved]
        if any(c is None for c in column) or _column_kind(column) is None:  # type: ignore[arg-type]
            return None
    return "nested"


def _is_tabular(items: list[Node]) -> bool:
    resolved = [_resolve(i) for i in items]
    if not items or not all(v.kind is Kind.MAPPING and v.content for v in resolved):
        return False
    keys = _key_set(resolved[0])
    if len(set(keys)) != len(keys):
        return False
    for v in resolved:
        ks = _key_set(v)
        if len(ks) != len(keys) or set(ks) != set(keys):
            return False
    return all(_column_kind([v.get_map_value(k) for v in resolved]) is not None  # type: ignore[list-item]
               for k in keys)


def _is_keyed_tabular(node: Node) -> bool:
    items = list(node.map_items())
    if len(items) < 2:
        return False
    keys = [k.value for k, _ in items]
    if len(set(keys)) != len(keys):
        return False
    return _is_tabular([v for _, v in items])


class ToonEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = False) -> None:
        self.options = options or Options()
        self.unwrap_scalar = unwrap_scalar
        self.delimiter = self.options.toon.delimiter
        self.symbol = DELIMITERS[self.delimiter]
        self.indent = " " * self.options.toon.indent
        self.keyed_tabular = self.options.toon.keyed_tabular
        self._emitted = False

    # ------------------------------------------------------------------ Encoder protocol

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None     # results are separated by a blank line in encode()

    def print_leading_content(self, out: TextIO, content: str) -> None:
        return None

    def encode(self, out: TextIO, node: Node) -> None:
        # TOON has no document separator, so consecutive results / documents are
        # separated by one blank line (a TOON decoder ignores blank lines).
        if self._emitted:
            out.write("\n")
        self._emitted = True
        node = _resolve(node)
        if node.kind is Kind.SCALAR and self.unwrap_scalar:
            out.write(node.value + "\n")
            return
        text = self.encode_to_string(node)
        out.write(text + "\n" if text != "" else "")

    # ------------------------------------------------------------------ core

    def encode_to_string(self, node: Node) -> str:
        node = _resolve(node)
        if node.kind is Kind.SCALAR:
            return scalar_text(node, self.delimiter)
        if node.kind is Kind.SEQUENCE:
            return "\n".join(self._array_lines(node, "", 0))
        if not node.content:
            return ""
        if self.keyed_tabular and _is_keyed_tabular(node):
            return "\n".join(self._keyed_tabular_lines(node, "", 0))
        return "\n".join(self._object_lines(node, 0))

    def _pad(self, depth: int) -> str:
        return self.indent * depth

    def _object_lines(self, node: Node, depth: int) -> list[str]:
        lines: list[str] = []
        pad = self._pad(depth)
        for key, value in node.map_items():
            lines.extend(self._field_lines(encode_key(key.value), value, depth, pad))
        return lines

    def _field_lines(self, key_text: str, value: Node, depth: int, pad: str) -> list[str]:
        value = _resolve(value)
        if value.kind is Kind.SCALAR:
            return [f"{pad}{key_text}: {scalar_text(value, self.delimiter)}"]
        if value.kind is Kind.SEQUENCE:
            return self._array_lines(value, key_text, depth)
        if not value.content:
            return [f"{pad}{key_text}:"]
        if self.keyed_tabular and _is_keyed_tabular(value):
            return self._keyed_tabular_lines(value, key_text, depth)
        return [f"{pad}{key_text}:", *self._object_lines(value, depth + 1)]

    # ------------------------------------------------------------------ arrays

    def _header(self, key_text: str, count: int, keyed: bool = False, fields: str | None = None) -> str:
        colon = ":" if keyed else ""
        head = f"{key_text}[{count}{colon}{self.symbol}]"
        if fields is not None:
            head += "{" + fields + "}"
        return head + ":"

    def _array_lines(self, node: Node, key_text: str, depth: int) -> list[str]:
        pad = self._pad(depth)
        items = list(node.content)
        if not items:
            return [f"{pad}{key_text}: []" if key_text else f"{pad}[]"]
        if all(_is_primitive(i) for i in items):
            cells = self.delimiter.join(scalar_text(_resolve(i), self.delimiter) for i in items)
            return [f"{pad}{self._header(key_text, len(items))} {cells}"]
        if _is_tabular(items):
            return self._tabular_lines(items, key_text, depth)
        lines = [f"{pad}{self._header(key_text, len(items))}"]
        for item in items:
            lines.extend(self._list_item_lines(_resolve(item), depth + 1))
        return lines

    def _tabular_lines(self, items: list[Node], key_text: str, depth: int) -> list[str]:
        resolved = [_resolve(i) for i in items]
        fields = self._field_list(resolved[0])
        lines = [f"{self._pad(depth)}{self._header(key_text, len(items), fields=fields)}"]
        row_pad = self._pad(depth + 1)
        for row in resolved:
            lines.append(row_pad + self.delimiter.join(self._leaf_cells(row)))
        return lines

    def _field_list(self, row: Node) -> str:
        parts: list[str] = []
        for key, value in row.map_items():
            value = _resolve(value)
            if value.kind is Kind.MAPPING:
                parts.append(encode_key(key.value) + "{" + self._field_list(value) + "}")
            else:
                parts.append(encode_key(key.value))
        return self.delimiter.join(parts)

    def _leaf_cells(self, row: Node) -> list[str]:
        cells: list[str] = []
        for _, value in row.map_items():
            value = _resolve(value)
            if value.kind is Kind.MAPPING:
                cells.extend(self._leaf_cells(value))
            else:
                cells.append(scalar_text(value, self.delimiter))
        return cells

    def _keyed_tabular_lines(self, node: Node, key_text: str, depth: int) -> list[str]:
        entries = [(k, _resolve(v)) for k, v in node.map_items()]
        fields = self._field_list(entries[0][1])
        lines = [f"{self._pad(depth)}{self._header(key_text, len(entries), keyed=True, fields=fields)}"]
        row_pad = self._pad(depth + 1)
        for key, value in entries:
            lines.append(f"{row_pad}{encode_key(key.value)}: "
                         + self.delimiter.join(self._leaf_cells(value)))
        return lines

    def _list_item_lines(self, item: Node, depth: int) -> list[str]:
        pad = self._pad(depth)
        if item.kind is Kind.SCALAR:
            return [f"{pad}- {scalar_text(item, self.delimiter)}"]
        if item.kind is Kind.SEQUENCE:
            inner = self._array_lines(item, "", depth)
            return [f"{pad}- {inner[0][len(pad):]}", *inner[1:]]
        if not item.content:
            return [f"{pad}-"]
        if self.keyed_tabular and _is_keyed_tabular(item):
            inner = self._keyed_tabular_lines(item, "", depth + 1)
        else:
            inner = self._object_lines(item, depth + 1)
        first = inner[0]
        inner_pad = self._pad(depth + 1)
        assert first.startswith(inner_pad)
        return [f"{pad}- {first[len(inner_pad):]}", *inner[1:]]


# =============================================================================
# decoder
# =============================================================================

class _Line:
    __slots__ = ("number", "depth", "text")

    def __init__(self, number: int, depth: int, text: str) -> None:
        self.number = number
        self.depth = depth
        self.text = text


_HEADER_RE = re.compile(
    r"^(?P<key>\"(?:[^\"\\]|\\.)*\"|[^\[\]{}:\"]*?)\[(?P<marker>#?)(?P<count>[0-9]+)(?P<keyed>:?)"
    r"(?P<delim>[\t|,]?)\](?:\{(?P<fields>.*)\})?:(?P<rest>.*)$", re.DOTALL,
)


class ToonDecoder:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.indent = self.options.toon.indent
        self.strict = self.options.toon.strict
        self.filename = ""
        self._budget: DecodeBudget | None = None

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True,
                         budget: DecodeBudget | None = None) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="toon", filename=filename)
        self.filename = filename
        self._budget = budget
        lines = self._scan(text)
        if not lines:
            if text.strip(" \t\r\n") == "" and not any(
                    ln.lstrip(" ").startswith("#") for ln in text.split("\n")):
                return
            return
        root = self.decode_root(lines)
        root.document_index = 0
        root.filename = filename
        root.file_index = file_index
        yield root

    def decode_value(self, text: str) -> Node:
        lines = self._scan(text)
        if not lines:
            return Node.mapping()
        return self.decode_root(lines)

    # ------------------------------------------------------------------ scanning

    def _error(self, message: str, line: int = 0) -> ToonError:
        return ToonError(message, line=line, filename=self.filename)

    def _tick(self) -> None:
        """巨大な文書のデコード中でも中止・タイムアウトが効くように、行を消費するたびに呼ぶ（U1）。"""
        if self._budget is not None:
            self._budget.tick()

    def _scan(self, text: str) -> list[_Line]:
        out: list[_Line] = []
        for number, raw in enumerate(text.split("\n"), start=1):
            if raw.endswith("\r"):
                raw = raw[:-1]
            stripped = raw.lstrip(" ")
            if stripped.strip(" \t") == "" or stripped.startswith("#"):
                continue        # blank lines and comment lines are dropped (spec §3)
            spaces = len(raw) - len(stripped)
            if stripped.startswith("\t"):
                raise self._error("tabs are not allowed for indentation", number)
            if self.strict and spaces % self.indent != 0:
                raise self._error(f"indentation of {spaces} spaces is not a multiple of {self.indent}", number)
            out.append(_Line(number, spaces // self.indent, stripped.rstrip(" ")))
        return out

    # ------------------------------------------------------------------ root

    def decode_root(self, lines: list[_Line]) -> Node:
        first = lines[0]
        if first.depth != 0:
            raise self._error("the first line must not be indented", first.number)
        header = self._match_header(first.text)
        if header is not None and header["key"] == "":
            node, end = self._decode_array_from_header(header, lines, 0, key_node=None)
            self._check_trailing(lines, end)
            return node
        if first.text == "[]":
            self._check_trailing(lines, 1)
            return Node.sequence()
        if len(lines) == 1 and header is None and self._split_key_value(first.text, first.number) is None:
            return self._scalar_node(first.text.strip(" "), ",", first.number)
        node, end = self._decode_object(lines, 0, 0)
        self._check_trailing(lines, end)
        return node

    def _check_trailing(self, lines: list[_Line], end: int) -> None:
        if end < len(lines):
            raise self._error("unexpected content after the root value", lines[end].number)

    # ------------------------------------------------------------------ objects

    def _decode_object(self, lines: list[_Line], start: int, depth: int) -> tuple[Node, int]:
        node = Node.mapping()
        i = start
        seen: set[str] = set()
        while i < len(lines):
            self._tick()
            ln = lines[i]
            if ln.depth < depth:
                break
            if ln.depth > depth:
                raise self._error("unexpected indentation", ln.number)
            key_node, value, i = self._decode_field(lines, i, depth)
            if key_node.value in seen and self.strict:
                raise self._error(f"duplicate key {key_node.value!r}", ln.number)
            seen.add(key_node.value)
            node.add_key_value(key_node, value)
        return node, i

    def _decode_field(self, lines: list[_Line], i: int, depth: int) -> tuple[Node, Node, int]:
        ln = lines[i]
        header = self._match_header(ln.text)
        if header is not None:
            key_node = self._key_node(header["key"], ln.number)
            value, end = self._decode_array_from_header(header, lines, i, key_node=key_node)
            return key_node, value, end
        split = self._split_key_value(ln.text, ln.number)
        if split is None:
            raise self._error("expected `key: value`", ln.number)
        key_text, rest = split
        key_node = self._key_node(key_text, ln.number)
        rest = rest.strip(" ")
        if rest == "":
            # empty object or nested object on the following lines
            if i + 1 < len(lines) and lines[i + 1].depth > depth:
                if lines[i + 1].depth != depth + 1:
                    raise self._error("indentation jumps more than one level", lines[i + 1].number)
                value, end = self._decode_object(lines, i + 1, depth + 1)
                return key_node, value, end
            return key_node, Node.mapping(), i + 1
        if rest == "[]":
            return key_node, Node.sequence(), i + 1
        value = self._scalar_node(rest, ",", ln.number)
        return key_node, value, i + 1

    # ------------------------------------------------------------------ arrays

    def _match_header(self, text: str) -> dict[str, str] | None:
        m = _HEADER_RE.match(text)
        if m is None:
            return None
        parts = m.groupdict()
        if parts["fields"] is not None and parts["fields"] == "":
            raise self._error("empty field list `{}` in array header")
        if parts["key"] != "" and not (parts["key"].startswith('"') or _UNQUOTED_KEY_RE.match(parts["key"])):
            return None
        return parts

    def _delimiter_of(self, header: dict[str, str]) -> str:
        return header["delim"] or ","

    def _decode_array_from_header(self, header: dict[str, str], lines: list[_Line], i: int, *,
                                  key_node: Node | None) -> tuple[Node, int]:
        ln = lines[i]
        count = int(header["count"])
        delimiter = self._delimiter_of(header)
        rest = header["rest"]
        fields_text = header["fields"]
        keyed = header["keyed"] == ":"
        if keyed and fields_text is None:
            raise self._error("keyed tabular header needs a field list", ln.number)
        if fields_text is not None:
            if rest.strip(" ") != "":
                raise self._error("unexpected content after tabular header", ln.number)
            fields = self._parse_fields(fields_text, delimiter, ln.number)
            if keyed:
                return self._decode_keyed_rows(lines, i + 1, ln.depth + 1, fields, count, delimiter)
            return self._decode_tabular_rows(lines, i + 1, ln.depth + 1, fields, count, delimiter)
        if rest.strip(" ") != "":
            cells = self._split_cells(rest, delimiter, ln.number)
            if self.strict and len(cells) != count:
                raise self._error(f"expected {count} values but found {len(cells)}", ln.number)
            node = Node.sequence()
            for cell in cells:
                node.add_child(self._scalar_node(cell, delimiter, ln.number))
            return node, i + 1
        # list form
        node = Node.sequence()
        j = i + 1
        while j < len(lines) and lines[j].depth == ln.depth + 1 and lines[j].text.startswith("-") \
                and (lines[j].text == "-" or lines[j].text[1] == " "):
            self._tick()
            item, j = self._decode_list_item(lines, j, ln.depth + 1)
            node.add_child(item)
        if j < len(lines) and lines[j].depth > ln.depth:
            raise self._error("expected a `- ` list item", lines[j].number)
        if self.strict and len(node.content) != count:
            raise self._error(f"expected {count} items but found {len(node.content)}", ln.number)
        return node, j

    def _decode_list_item(self, lines: list[_Line], i: int, depth: int) -> tuple[Node, int]:
        ln = lines[i]
        body = ln.text[2:] if len(ln.text) > 1 else ""
        if body.strip(" ") == "":
            if i + 1 < len(lines) and lines[i + 1].depth == depth + 1:
                return self._decode_object(lines, i + 1, depth + 1)
            return Node.mapping(), i + 1
        header = self._match_header(body)
        if header is not None and header["key"] == "":
            # nested array: `- [N]: ...` / `- [N]{...}:` / `- [N]:`
            shifted = [_Line(ln.number, depth, body), *lines[i + 1:]]
            node, used = self._decode_array_from_header(header, shifted, 0, key_node=None)
            return node, i + used
        if body == "[]":
            return Node.sequence(), i + 1
        split = self._split_key_value(body, ln.number)
        if split is None and header is None:
            return self._scalar_node(body.strip(" "), ",", ln.number), i + 1
        # object item: first field on the hyphen line, remaining fields at depth + 1
        shifted = [_Line(ln.number, depth + 1, body), *lines[i + 1:]]
        node, used = self._decode_object(shifted, 0, depth + 1)
        return node, i + used

    def _parse_fields(self, text: str, delimiter: str, number: int) -> list[tuple[str, list]]:
        """Return a list of (key, nested_fields) where nested_fields is [] for leaves."""
        fields: list[tuple[str, list]] = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == '"':
                end = self._quoted_end(text, i, number)
                key = self._unescape(text[i + 1:end], number)
                i = end + 1
            else:
                j = i
                while j < n and text[j] not in (delimiter, "{", "}"):
                    j += 1
                key = text[i:j].strip(" ")
                i = j
            nested: list = []
            if i < n and text[i] == "{":
                close = self._matching_brace(text, i, number)
                nested = self._parse_fields(text[i + 1:close], delimiter, number)
                i = close + 1
            if key == "":
                raise self._error("empty field name in header", number)
            fields.append((key, nested))
            if i < n:
                if text[i] != delimiter:
                    raise self._error("malformed field list in header", number)
                i += 1
        return fields

    @staticmethod
    def _matching_brace(text: str, start: int, number: int) -> int:
        depth = 0
        in_quote = False
        i = start
        while i < len(text):
            c = text[i]
            if in_quote:
                if c == "\\":
                    i += 1
                elif c == '"':
                    in_quote = False
            elif c == '"':
                in_quote = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise ToonError("unbalanced `{` in header", line=number)

    @staticmethod
    def _leaf_count(fields: list[tuple[str, list]]) -> int:
        return sum(ToonDecoder._leaf_count(nested) if nested else 1 for _, nested in fields)

    def _row_to_object(self, fields: list[tuple[str, list]], cells: list[str], delimiter: str,
                       number: int) -> Node:
        node = Node.mapping()
        pos = 0

        def build(field_list: list[tuple[str, list]]) -> Node:
            nonlocal pos
            obj = Node.mapping()
            for key, nested in field_list:
                if nested:
                    obj.add_key_value(Node.string(key), build(nested))
                else:
                    obj.add_key_value(Node.string(key), self._scalar_node(cells[pos], delimiter, number))
                    pos += 1
            return obj

        node = build(fields)
        return node

    def _decode_tabular_rows(self, lines: list[_Line], i: int, depth: int,
                             fields: list[tuple[str, list]], count: int, delimiter: str) -> tuple[Node, int]:
        node = Node.sequence()
        width = self._leaf_count(fields)
        j = i
        while j < len(lines) and lines[j].depth == depth and self._match_header(lines[j].text) is None \
                and not lines[j].text.startswith("- ") and lines[j].text != "-":
            self._tick()
            ln = lines[j]
            if self._looks_like_field(ln.text):
                break
            cells = self._split_cells(ln.text, delimiter, ln.number)
            if self.strict and len(cells) != width:
                raise self._error(f"expected {width} cells but found {len(cells)}", ln.number)
            if len(cells) < width:
                cells += [""] * (width - len(cells))
            node.add_child(self._row_to_object(fields, cells, delimiter, ln.number))
            j += 1
        if j < len(lines) and lines[j].depth > depth:
            raise self._error("unexpected indentation inside a tabular array", lines[j].number)
        if self.strict and len(node.content) != count:
            raise self._error(f"expected {count} rows but found {len(node.content)}", lines[i - 1].number)
        return node, j

    def _looks_like_field(self, text: str) -> bool:
        """Rows never contain an unquoted `key:` prefix; a sibling field does."""
        split = self._split_key_value(text, 0, quiet=True)
        return split is not None and split[1].strip(" ") != "" and not self._is_row_like(text)

    def _is_row_like(self, text: str) -> bool:
        return False

    def _decode_keyed_rows(self, lines: list[_Line], i: int, depth: int,
                           fields: list[tuple[str, list]], count: int, delimiter: str) -> tuple[Node, int]:
        node = Node.mapping()
        width = self._leaf_count(fields)
        j = i
        while j < len(lines) and lines[j].depth == depth:
            self._tick()
            ln = lines[j]
            split = self._split_key_value(ln.text, ln.number)
            if split is None:
                raise self._error("expected `key: cells` entry row", ln.number)
            key_text, rest = split
            cells = self._split_cells(rest, delimiter, ln.number)
            if self.strict and len(cells) != width:
                raise self._error(f"expected {width} cells but found {len(cells)}", ln.number)
            if len(cells) < width:
                cells += [""] * (width - len(cells))
            node.add_key_value(self._key_node(key_text, ln.number),
                               self._row_to_object(fields, cells, delimiter, ln.number))
            j += 1
        if self.strict and len(node.content) // 2 != count:
            raise self._error(f"expected {count} entries but found {len(node.content) // 2}",
                              lines[i - 1].number)
        return node, j

    # ------------------------------------------------------------------ tokens

    def _quoted_end(self, text: str, start: int, number: int) -> int:
        i = start + 1
        while i < len(text):
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c == '"':
                return i
            i += 1
        raise self._error("unterminated quoted string", number)

    def _unescape(self, body: str, number: int) -> str:
        out: list[str] = []
        i = 0
        n = len(body)
        while i < n:
            c = body[i]
            if c != "\\":
                out.append(c)
                i += 1
                continue
            if i + 1 >= n:
                raise self._error("invalid escape sequence", number)
            nxt = body[i + 1]
            simple = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
            elif nxt == "u" and i + 6 <= n:
                try:
                    code = int(body[i + 2:i + 6], 16)
                except ValueError:
                    raise self._error("invalid \\u escape", number) from None
                if 0xD800 <= code <= 0xDFFF:
                    raise self._error("lone surrogate in \\u escape", number)
                out.append(chr(code))
                i += 6
            else:
                raise self._error(f"invalid escape sequence \\{nxt}", number)
        return "".join(out)

    def _split_key_value(self, text: str, number: int, *, quiet: bool = False) -> tuple[str, str] | None:
        """Split at the first unquoted colon. Returns (key_text, rest) or None."""
        if text.startswith('"'):
            end = self._quoted_end(text, 0, number)
            after = text[end + 1:]
            stripped = after.lstrip(" ")
            if not stripped.startswith(":"):
                if quiet:
                    return None
                return None
            return text[:end + 1], stripped[1:]
        idx = text.find(":")
        if idx < 0:
            return None
        return text[:idx], text[idx + 1:]

    def _key_node(self, key_text: str, number: int) -> Node:
        key_text = key_text.strip(" ")
        if key_text.startswith('"'):
            end = self._quoted_end(key_text, 0, number)
            if end != len(key_text) - 1:
                raise self._error("unexpected characters after quoted key", number)
            key = self._unescape(key_text[1:-1], number)
        else:
            key = key_text
            if self.strict and not _UNQUOTED_KEY_RE.match(key):
                raise self._error(f"key {key!r} must be quoted", number)
        return Node.string(key)

    def _split_cells(self, text: str, delimiter: str, number: int) -> list[str]:
        cells: list[str] = []
        i = 0
        n = len(text)
        while True:
            while i < n and text[i] == " ":
                i += 1
            if i < n and text[i] == '"':
                end = self._quoted_end(text, i, number)
                token = text[i:end + 1]
                i = end + 1
                while i < n and text[i] == " ":
                    i += 1
                if i < n and text[i] != delimiter:
                    raise self._error("unexpected characters after quoted value", number)
            else:
                j = i
                while j < n and text[j] != delimiter:
                    j += 1
                token = text[i:j].strip(" ")
                i = j
            cells.append(token)
            if i >= n:
                break
            i += 1        # skip the delimiter
            if i >= n:
                cells.append("")
                break
        return cells

    def _scalar_node(self, token: str, delimiter: str, number: int) -> Node:
        token = token.strip(" ")
        if token.startswith('"'):
            end = self._quoted_end(token, 0, number)
            if end != len(token) - 1:
                raise self._error("unexpected characters after quoted value", number)
            value = self._unescape(token[1:-1], number)
            node = Node.string(value)
            node.tag = "!!str"
            if tags.resolve_plain(value) != "!!str" or value == "":
                node.style = Style.DOUBLE_QUOTED
            return node
        if token == "null":
            return Node.null()
        if token == "true" or token == "false":
            return Node.boolean(token == "true")
        if _NUMBER_RE.match(token):
            tag = "!!float" if any(c in token for c in ".eE") else "!!int"
            return Node.scalar(token, tag)
        node = Node.string(token)
        if node.tag == "!!str" and tags.resolve_plain(token) != "!!str":
            node.style = Style.DOUBLE_QUOTED
        return node
