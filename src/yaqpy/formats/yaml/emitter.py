"""Node -> YAML text (design doc 9-3 (4)), modelled on go-yaml v3's emitter."""

from __future__ import annotations

import re

from yaqpy.core.model.leading import render_leading_content
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import FormatError
from yaqpy.formats.yaml.resolver import resolve_plain

_INDICATORS = set("-?:,[]{}#&*!|>'\"%@`")
_SPECIAL_FLOW = set(",[]{}")
_PRINTABLE_RE = re.compile(
    "[^\t\n\r\x20-\x7e\x85\xa0-퟿-�\U00010000-\U0010ffff]"
)


class YamlEmitter:
    def __init__(self, *, indent: int = 2, compact_sequence_indent: bool = False) -> None:
        if indent < 2:
            indent = 2
        elif indent > 9:
            indent = 9
        self.indent = indent
        self.compact_seq = compact_sequence_indent

    # ------------------------------------------------------------------ public

    def emit(self, node: Node) -> str:
        """Emit one document body (no ``---``). Ends with a newline."""
        lines: list[str] = []
        self._emit_comment_lines(lines, node.head_comment, 0)
        if node.kind is Kind.SCALAR or node.kind is Kind.ALIAS:
            lines.append(self._props(node) + self._scalar_text(node, 0, in_flow=False)
                         + self._line_comment(node))
        elif node.style & Style.FLOW or not node.content:
            lines.append(self._props(node) + self._flow(node) + self._line_comment(node))
        elif node.kind is Kind.MAPPING:
            props = self._props(node)
            if props or node.line_comment:
                lines.append((props + self._line_comment(node)).strip())
            self._emit_mapping(lines, node, 0)
        else:
            props = self._props(node)
            if props or node.line_comment:
                lines.append((props + self._line_comment(node)).strip())
            self._emit_sequence(lines, node, 0)
        text = "\n".join(lines) + "\n"
        if node.foot_comment:
            text += render_leading_content(node.foot_comment)
        return text

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _line_comment(node: Node) -> str:
        if node.line_comment:
            return " " + _ensure_hash(node.line_comment.split("\n")[0])
        return ""

    @staticmethod
    def _line_comment_rest(node: Node, col: int) -> list[str]:
        """Lines 2..n of a multi-line line comment: go-yaml writes them below, at the current indent."""
        if "\n" not in node.line_comment:
            return []
        pad = " " * col
        return [pad + _ensure_hash(raw.lstrip()) if raw.strip() else ""
                for raw in node.line_comment.split("\n")[1:]]

    def _emit_comment_lines(self, lines: list[str], comment: str, col: int) -> None:
        if not comment:
            return
        pad = " " * col
        for raw in comment.split("\n"):
            if raw.strip() == "":
                lines.append("")
            else:
                lines.append(pad + _ensure_hash(raw.strip()))

    @staticmethod
    def _props(node: Node) -> str:
        """Anchor and explicit tag prefix, e.g. ``&a !!str ``."""
        out = ""
        if node.kind is Kind.ALIAS:
            return ""
        if node.anchor:
            out += "&" + node.anchor + " "
        tag = node.tag
        if tag and tag not in ("!!map", "!!seq", "!!merge"):
            explicit = bool(node.style & Style.TAGGED)
            if not tag.startswith("!!"):
                explicit = True
            elif node.kind is Kind.SCALAR and tag not in ("!!str", "!!int", "!!float", "!!bool",
                                                          "!!null", "!!timestamp"):
                explicit = True
            if explicit:
                out += tag + " "
        elif tag in ("!!map", "!!seq") and node.style & Style.TAGGED:
            out += tag + " "
        return out

    # ------------------------------------------------------------------ block

    def _emit_mapping(self, lines: list[str], node: Node, col: int) -> None:
        pad = " " * col
        foot_written = False
        for key, value in node.map_items():
            if foot_written:
                lines.append("")            # go-yaml's foot_indent: a foot comment is set apart
            self._emit_comment_lines(lines, key.head_comment, col)
            if value.head_comment and value.head_comment != key.head_comment:
                self._emit_comment_lines(lines, value.head_comment, col)
            key_text = self._key_text(key, col)
            if key_text is None:
                # complex key
                lines.append(pad + "?")
                self._emit_block_value(lines, key, col, pad + "  ", is_seq_item=False,
                                       key_text=None)
                lines.append(pad + ":")
                self._emit_block_value(lines, value, col, pad + "  ", is_seq_item=False,
                                       key_text=None)
            else:
                self._emit_pair(lines, key, value, col, pad, key_text)
            self._emit_comment_lines(lines, key.foot_comment, col)
            if value.foot_comment and value.foot_comment != key.foot_comment:
                self._emit_comment_lines(lines, value.foot_comment, col)
            foot_written = bool(key.foot_comment or value.foot_comment)

    def _key_text(self, key: Node, col: int) -> str | None:
        if key.kind is Kind.ALIAS:
            return "*" + key.value
        if key.kind is not Kind.SCALAR:
            return None
        text = self._scalar_text(key, col, in_flow=False, is_key=True)
        if "\n" in text:
            return None
        return self._props(key) + text

    def _emit_pair(self, lines: list[str], key: Node, value: Node, col: int, pad: str,
                   key_text: str) -> None:
        head = pad + key_text + ":"
        key_comment = self._line_comment(key)
        value = value
        if value.kind in (Kind.SCALAR, Kind.ALIAS):
            text = self._props(value) + self._scalar_text(value, col, in_flow=False)
            comment = key_comment or self._line_comment(value)
            if text.startswith(("|", ">")):
                # block scalar: header on the key line, body below
                header, _, body = text.partition("\n")
                lines.append(head + " " + header + comment)
                if body:
                    lines.extend(body.split("\n"))
            else:
                lines.append((head + " " + text).rstrip() + comment)
                lines.extend(self._line_comment_rest(key if key_comment else value, col))
            return
        if value.style & Style.FLOW or not value.content:
            lines.append(head + " " + self._props(value) + self._flow(value)
                         + (key_comment or self._line_comment(value)))
            lines.extend(self._line_comment_rest(key if key_comment else value, col))
            return
        props = self._props(value)
        lines.append((head + " " + props).rstrip() + (key_comment or self._line_comment(value)))
        lines.extend(self._line_comment_rest(key if key_comment else value, col))
        if value.kind is Kind.MAPPING:
            self._emit_mapping(lines, value, col + self.indent)
        else:
            seq_col = col if self.compact_seq else col + self.indent
            self._emit_sequence(lines, value, seq_col)

    def _emit_sequence(self, lines: list[str], node: Node, col: int) -> None:
        pad = " " * col
        foot_written = False
        for item in node.content:
            if foot_written:
                lines.append("")
            self._emit_comment_lines(lines, item.head_comment, col)
            self._emit_block_value(lines, item, col, pad, is_seq_item=True, key_text=None)
            self._emit_comment_lines(lines, item.foot_comment, col)
            foot_written = bool(item.foot_comment)

    def _emit_block_value(self, lines: list[str], value: Node, col: int, pad: str, *,
                          is_seq_item: bool, key_text: str | None) -> None:
        prefix = pad + "- " if is_seq_item else pad
        inner_col = col + 2 if is_seq_item else col + 2
        if value.kind in (Kind.SCALAR, Kind.ALIAS):
            text = self._props(value) + self._scalar_text(value, inner_col if is_seq_item else col,
                                                          in_flow=False)
            if text.startswith(("|", ">")):
                header, _, body = text.partition("\n")
                lines.append(prefix + header + self._line_comment(value))
                if body:
                    lines.extend(body.split("\n"))
            else:
                lines.append((prefix + text).rstrip() + self._line_comment(value))
            return
        if value.style & Style.FLOW or not value.content:
            lines.append(prefix + self._props(value) + self._flow(value) + self._line_comment(value))
            return
        props = self._props(value)
        if value.kind is Kind.MAPPING:
            if props or value.line_comment or not is_seq_item:
                lines.append((prefix + props).rstrip() + self._line_comment(value))
                self._emit_mapping(lines, value, inner_col)
            else:
                # compact form: first pair on the dash line
                start = len(lines)
                self._emit_mapping(lines, value, inner_col)
                if len(lines) > start:
                    first = lines[start]
                    lines[start] = prefix + first[inner_col:] if first.startswith(" " * inner_col) else first
                    # head comments before the first key move above the dash
                    self._hoist_leading_comments(lines, start, pad, inner_col, prefix)
        else:
            if props or value.line_comment or not is_seq_item:
                lines.append((prefix + props).rstrip() + self._line_comment(value))
                self._emit_sequence(lines, value, inner_col)
            else:
                start = len(lines)
                self._emit_sequence(lines, value, inner_col)
                if len(lines) > start:
                    first = lines[start]
                    lines[start] = prefix + first[inner_col:] if first.startswith(" " * inner_col) else first
                    self._hoist_leading_comments(lines, start, pad, inner_col, prefix)

    @staticmethod
    def _hoist_leading_comments(lines: list[str], start: int, pad: str, inner_col: int,
                                prefix: str) -> None:
        """If the compact item started with comment lines, put the dash on the first real line."""
        i = start
        if not lines[start].startswith(prefix):
            return
        # lines[start] was rewritten with the prefix; if it is a comment, move the prefix down
        body = lines[start][len(prefix):]
        if body.startswith("#"):
            lines[start] = pad + body
            i = start + 1
            while i < len(lines) and (lines[i].strip().startswith("#") or lines[i].strip() == ""):
                lines[i] = pad + lines[i].strip() if lines[i].strip() else ""
                i += 1
            if i < len(lines) and lines[i].startswith(" " * inner_col):
                lines[i] = prefix + lines[i][inner_col:]

    # ------------------------------------------------------------------ flow

    def _flow(self, node: Node) -> str:
        if node.kind is Kind.MAPPING:
            if not node.content:
                return "{}"
            parts = []
            for key, value in node.map_items():
                k = self._flow_node(key, is_key=True)
                v = self._flow_node(value)
                parts.append(f"{k}: {v}")
            return "{" + ", ".join(parts) + "}"
        if node.kind is Kind.SEQUENCE:
            if not node.content:
                return "[]"
            return "[" + ", ".join(self._flow_node(c) for c in node.content) + "]"
        return self._flow_node(node)

    def _flow_node(self, node: Node, *, is_key: bool = False) -> str:
        if node.kind in (Kind.MAPPING, Kind.SEQUENCE):
            return self._props(node) + self._flow(node)
        if node.kind is Kind.ALIAS:
            return "*" + node.value
        return self._props(node) + self._scalar_text(node, 0, in_flow=True, is_key=is_key)

    # ------------------------------------------------------------------ scalars

    def _scalar_text(self, node: Node, col: int, *, in_flow: bool, is_key: bool = False) -> str:
        if node.kind is Kind.ALIAS:
            return "*" + node.value
        value = node.value
        style = node.style
        tag = node.tag
        if tag == "!!null" and value == "":
            # go-yaml emits an empty plain scalar for an unset null ("key:")
            return "null" if in_flow else ""
        if style & Style.DOUBLE_QUOTED:
            return _double_quote(value)
        if style & Style.SINGLE_QUOTED and "\n" not in value and _single_quote_ok(value):
            return _single_quote(value)
        if style & Style.SINGLE_QUOTED:
            return _double_quote(value)
        if style & Style.LITERAL and not in_flow and not is_key:
            return self._block_scalar(value, col, literal=True)
        if style & Style.FOLDED and not in_flow and not is_key:
            return self._block_scalar(value, col, literal=False)
        if "\n" in value:
            if in_flow or is_key:
                return _double_quote(value)
            return self._block_scalar(value, col, literal=True)
        explicit_tag = bool(style & Style.TAGGED) or (tag != "" and not tag.startswith("!!"))
        if self._plain_ok(value, tag, in_flow, explicit_tag):
            return value
        if _single_quote_ok(value) and not _PRINTABLE_RE.search(value):
            return _double_quote(value) if '"' not in value and "\\" not in value else _single_quote(value)
        return _double_quote(value)

    @staticmethod
    def _plain_ok(value: str, tag: str, in_flow: bool, explicit_tag: bool = False) -> bool:
        if value == "":
            return False
        if tag == "!!str" and not explicit_tag and resolve_plain(value) != "!!str":
            return False
        first = value[0]
        if first in _INDICATORS:
            if first in "-?:" and len(value) > 1 and value[1] not in " \t":
                pass
            else:
                return False
        if value[0] in " \t" or value[-1] in " \t":
            return False
        if ": " in value or " #" in value or value.endswith(":"):
            return False
        if "\t" in value or "\r" in value:
            return False
        if _PRINTABLE_RE.search(value):
            return False
        if in_flow and (set(value) & _SPECIAL_FLOW):
            return False
        if in_flow and ":" in value:
            return False
        if value.startswith("---") or value.startswith("..."):
            return False
        return True

    def _block_scalar(self, value: str, col: int, *, literal: bool) -> str:
        indicator = "|" if literal else ">"
        body = value
        if body.endswith("\n\n") or body == "\n":
            chomp = "+"
            content = body[:-1]
        elif body.endswith("\n"):
            chomp = ""
            content = body[:-1]
        else:
            chomp = "-"
            content = body
        explicit_indent = ""
        first_line = content.split("\n", 1)[0] if content else ""
        if first_line.startswith(" ") or content.startswith("\n"):
            explicit_indent = str(self.indent)
        pad = " " * (col + self.indent)
        if not literal:
            # inverse of folding: each original newline becomes a blank line
            content = "\n\n".join(content.split("\n"))
        lines = [pad + line if line != "" else "" for line in content.split("\n")]
        header = indicator + explicit_indent + chomp
        if content == "" and chomp == "":
            return header + "\n"
        return header + "\n" + "\n".join(lines)


def _ensure_hash(text: str) -> str:
    return text if text.startswith("#") else "# " + text


def _single_quote_ok(value: str) -> bool:
    return not _PRINTABLE_RE.search(value) and "\n" not in value


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_ESCAPES = {
    "\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r", "\b": "\\b", "\f": "\\f",
    "\0": "\\0", "\a": "\\a", "\v": "\\v", "\x1b": "\\e", "\x85": "\\N", "\xa0": "\\_",
    " ": "\\L", " ": "\\P",
}


def _double_quote(value: str) -> str:
    out = ['"']
    for ch in value:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif _PRINTABLE_RE.match(ch):
            code = ord(ch)
            if code <= 0xFF:
                out.append(f"\\x{code:02X}")
            elif code <= 0xFFFF:
                out.append(f"\\u{code:04X}")
            else:
                out.append(f"\\U{code:08X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def emit_document(node: Node, *, indent: int = 2, compact_sequence_indent: bool = False) -> str:
    try:
        return YamlEmitter(indent=indent, compact_sequence_indent=compact_sequence_indent).emit(node)
    except RecursionError:
        raise FormatError("document too deeply nested to emit", format="yaml") from None
