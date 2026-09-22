"""CSV / TSV decoder and encoder (a port of yq's ``decoder_csv_object.go`` and ``encoder_csv.go``).

* Reading: the first row is the header; every following row becomes a map ``header -> cell`` and the
  document is the list of those maps. A cell is read as a YAML snippet when ``auto_parse`` is on
  (``1`` -> int, ``true`` -> bool, ``cool: true`` -> a map, an empty cell -> null); with
  ``auto_parse`` off only plain scalars are typed and everything else stays a string.
* Writing: a list of scalars is one row; a list of maps is a table (header from the first map, a
  missing key is an empty cell); a list of lists is a table without header. Anything nested
  deeper is refused instead of being written wrongly.

Quoting follows Go's ``encoding/csv`` (a UTF-8 BOM is skipped when reading). ``\\r\\n`` is read as
``\\n``; a bare ``\\r`` stays part of the cell.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TextIO

from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.formats.base import DecodeBudget
from yaqpy.formats.yaml.codec import YamlDecoder
from yaqpy.formats.yaml.resolver import resolve_plain
from yaqpy.options import Options


# ============================================================================ reading

def read_records(text: str, separator: str, *, filename: str = "") -> Iterator[tuple[int, list[str]]]:
    """Yield ``(first line number, fields)`` for every record (Go's ``csv.Reader``, strict quotes).

    Empty lines are skipped. All records must have as many fields as the first one.
    """
    if separator in ('"', "\r", "\n") or len(separator) != 1:
        raise FormatError("csv: invalid field delimiter", format="csv", filename=filename)
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    n = len(text)
    plain = re.compile(f'[^{re.escape(separator)}\\n"]*')
    pos = 0
    line = 1
    expected = -1

    def fail(message: str, at: int, on_line: int, start_line: int) -> FormatError:
        column = at - text.rfind("\n", 0, at)
        where = (f"record on line {start_line}; parse error on line {on_line}, column {column}"
                 if start_line != on_line else f"parse error on line {on_line}, column {column}")
        return FormatError(f"{where}: {message}", format="csv", filename=filename, line=on_line,
                           column=column)

    while pos < n:
        if text[pos] == "\n":
            pos += 1
            line += 1
            continue
        fields: list[str] = []
        start_line = line
        while True:
            if pos < n and text[pos] == '"':
                pos += 1
                parts: list[str] = []
                while True:
                    end = text.find('"', pos)
                    if end < 0:
                        raise fail('extraneous or missing " in quoted-field', n, line, start_line)
                    chunk = text[pos:end]
                    parts.append(chunk)
                    line += chunk.count("\n")
                    if text.startswith('"', end + 1):
                        parts.append('"')
                        pos = end + 2
                        continue
                    pos = end + 1
                    if pos < n and text[pos] not in (separator, "\n"):
                        raise fail('extraneous or missing " in quoted-field', pos, line, start_line)
                    break
                fields.append("".join(parts))
            else:
                match = plain.match(text, pos)
                end = match.end()  # type: ignore[union-attr]
                if end < n and text[end] == '"':
                    raise fail('bare " in non-quoted field', end, line, start_line)
                fields.append(text[pos:end])
                pos = end
            if pos >= n:
                break
            if text[pos] == "\n":
                pos += 1
                line += 1
                break
            pos += 1                    # the separator; the next field follows (maybe an empty one)
        if expected < 0:
            expected = len(fields)
        elif len(fields) != expected:
            raise FormatError(f"record on line {start_line}: wrong number of fields", format="csv",
                              filename=filename, line=start_line)
        yield start_line, fields


_SIMPLE = re.compile(r"(?:[-+.]?[0-9]|[A-Za-z_])[A-Za-z0-9_.+\-]*")
_SIMPLE_WORDS = re.compile(r"[A-Za-z_][A-Za-z0-9_ .,()/'+\-]*[A-Za-z0-9_.)']")


class CsvDecoder:
    """Rows -> ``[{header: cell, ...}, ...]``. ``tsv=True`` reads tab separated values."""

    def __init__(self, options: Options | None = None, *, tsv: bool = False) -> None:
        self.options = options or Options()
        csv = self.options.csv
        self.tsv = tsv
        self.separator = "\t" if tsv else csv.separator
        self.auto_parse = csv.tsv_auto_parse if tsv else csv.auto_parse
        self._format = "tsv" if tsv else "csv"

    # ------------------------------------------------------------------ cells

    def _snippet(self, content: str) -> Node | None:
        """Go's ``parseSnippet``: the cell as a YAML value, or None when it is not one."""
        if content == "":
            return Node(Kind.SCALAR, tag="!!null", value="")
        if _SIMPLE.fullmatch(content) or _SIMPLE_WORDS.fullmatch(content):
            # a plain scalar: the YAML parser would give the same node (a test compares them)
            return Node(Kind.SCALAR, tag=resolve_plain(content), value=content)
        decoder = YamlDecoder(self.options)
        try:
            documents = list(decoder.decode_documents(content, process_leading=True))
        except FormatError:
            return None
        if not documents:
            return None
        node = documents[0]
        if node.kind is Kind.SCALAR:
            node.line_comment = node.leading_content
        else:
            node.head_comment = node.leading_content
        node.leading_content = ""
        node.line = 0
        node.column = 0
        if node.tag == "!!str":
            # decoding drops line breaks: use the original text
            text_node = Node(Kind.SCALAR, tag="!!str", value=content)
            text_node.line_comment = node.line_comment
            return text_node
        return node

    def _cell(self, content: str) -> Node:
        node = self._snippet(content)
        if node is None or (not self.auto_parse and (node.kind is not Kind.SCALAR
                                                     or node.value != content)):
            return Node(Kind.SCALAR, tag="!!str", value=content)
        return node

    # ------------------------------------------------------------------ documents

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True,
                         budget: DecodeBudget | None = None) -> Iterator[Node]:
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format=self._format, filename=filename)
        try:
            records = read_records(text, self.separator, filename=filename)
            header_record = next(records, None)
            if header_record is None:
                return
            header = header_record[1]
            root = Node.sequence()
            for _, row in records:
                if budget is not None:
                    budget.tick()
                obj = Node.mapping()
                obj.parent = root
                for name, cell in zip(header, row):
                    key = Node(Kind.SCALAR, tag="!!str", value=name)
                    value = self._cell(cell)
                    key.parent = obj
                    key.is_map_key = True
                    value.parent = obj
                    value.key = key
                    obj.content.append(key)
                    obj.content.append(value)
                index = Node.integer(len(root.content))
                index.parent = root
                index.is_map_key = True
                obj.key = index
                root.content.append(obj)
        except FormatError as e:
            if filename and not e.message.startswith("bad file"):
                raise FormatError(f"bad file '{filename}': {e.message}", format=self._format,
                                  filename=filename, line=e.line, column=e.column) from None
            raise
        root.document_index = 0
        root.filename = filename
        root.file_index = file_index
        yield root


# ============================================================================ writing

def _needs_quotes(field: str, separator: str) -> bool:
    """Go's ``Writer.fieldNeedsQuotes``."""
    if field == "":
        return False
    if field == "\\.":
        return True
    if separator in field or '"' in field or "\n" in field or "\r" in field:
        return True
    first = field[0]
    return first.isspace() and first not in "\x1c\x1d\x1e\x1f"


def format_row(fields: list[str], separator: str) -> str:
    out: list[str] = []
    for field in fields:
        if _needs_quotes(field, separator):
            out.append('"' + field.replace('"', '""') + '"')
        else:
            out.append(field)
    return separator.join(out) + "\n"


class CsvEncoder:
    def __init__(self, options: Options | None = None, *, tsv: bool = False,
                 unwrap_scalar: bool = False) -> None:
        self.options = options or Options()
        self.separator = "\t" if tsv else self.options.csv.separator
        self.unwrap_scalar = unwrap_scalar
        if self.separator in ('"', "\r", "\n") or len(self.separator) != 1:
            raise FormatError("csv: invalid field delimiter", format="tsv" if tsv else "csv")

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None

    def print_leading_content(self, out: TextIO, content: str) -> None:
        return None

    # ------------------------------------------------------------------ rows

    def _row(self, cells: list[Node]) -> str:
        values: list[str] = []
        for i, child in enumerate(cells):
            if child.kind is not Kind.SCALAR:
                raise FormatError(
                    f"csv encoding only works for arrays of scalars (string/numbers/booleans), "
                    f"child[{i}] is a {child.tag}", format="csv")
            values.append(child.value)
        return format_row(values, self.separator)

    def encode(self, out: TextIO, node: Node) -> None:
        if node.kind is Kind.SCALAR:
            out.write(node.value + "\n")
            return
        if node.kind is not Kind.SEQUENCE:
            raise FormatError(f"csv encoding only works for arrays, got: {node.tag}", format="csv")
        if not node.content:
            return
        first = node.content[0]
        if first.kind is Kind.SCALAR:
            out.write(self._row(node.content))
        elif first.kind is Kind.MAPPING:
            out.write(self._objects(node.content))
        else:
            out.write(self._arrays(node.content))

    def _arrays(self, rows: list[Node]) -> str:
        lines: list[str] = []
        for i, child in enumerate(rows):
            if child.kind is not Kind.SEQUENCE:
                raise FormatError(
                    f"csv encoding only works for arrays of scalars (string/numbers/booleans), "
                    f"child[{i}] is a {child.tag}", format="csv")
            lines.append(self._row(child.content))
        return "".join(lines)

    def _objects(self, rows: list[Node]) -> str:
        headers = [key.value for key, _ in rows[0].map_items()]
        lines = [format_row(headers, self.separator)]
        for i, child in enumerate(rows):
            if child.kind is not Kind.MAPPING:
                raise FormatError(
                    "csv object encoding only works for arrays of flat objects "
                    f"(string key => string/numbers/boolean value), child[{i}] is a {child.tag}",
                    format="csv")
            cells: list[Node] = []
            for name in headers:
                value = child.get_map_value(name)
                cells.append(value if value is not None else Node(Kind.SCALAR, tag="!!null", value=""))
            lines.append(self._row(cells))
        return "".join(lines)
