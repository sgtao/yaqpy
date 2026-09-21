"""JSON decoder/encoder built on the standard ``json`` module (design doc 9-2)."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from typing import Any, TextIO

from yaqpy.core.model import tags
from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import FormatError
from yaqpy.options import Options


class _Raw(str):
    """A number kept as its original text."""


class _Object(list):
    """The ``(key, value)`` pairs of a JSON object. A subclass so that ``{}`` (no pairs) is not
    mistaken for ``[]``."""


def _pairs_hook(pairs: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    return _Object(pairs)


def _to_node(value: Any, parent: Node | None = None) -> Node:
    if isinstance(value, _Object):
        node = Node.mapping(parent=parent)
        for key, child in value:
            key_node = Node.string(str(key))
            key_node.tag = "!!str"
            key_node.parent = node
            key_node.is_map_key = True
            child_node = _to_node(child, node)
            child_node.key = key_node
            node.content.extend((key_node, child_node))
        return node
    if isinstance(value, list):
        node = Node.sequence(parent=parent)
        for i, child in enumerate(value):
            key_node = Node.integer(i)
            key_node.parent = node
            key_node.is_map_key = True
            child_node = _to_node(child, node)
            child_node.key = key_node
            node.content.append(child_node)
        return node
    if value is None:
        return Node(Kind.SCALAR, tag="!!null", value="null", parent=parent)
    if isinstance(value, bool):
        return Node(Kind.SCALAR, tag="!!bool", value="true" if value else "false", parent=parent)
    if isinstance(value, _Raw):
        text = str(value)
        if any(c in text for c in ".eE") and not text.lower() in ("nan", "infinity", "-infinity"):
            return Node(Kind.SCALAR, tag="!!float", value=text, parent=parent)
        if text.lower() in ("nan", "infinity", "-infinity"):
            mapped = {"nan": ".nan", "infinity": ".inf", "-infinity": "-.inf"}[text.lower()]
            return Node(Kind.SCALAR, tag="!!float", value=mapped, parent=parent)
        return Node(Kind.SCALAR, tag="!!int", value=text, parent=parent)
    if isinstance(value, str):
        node = Node(Kind.SCALAR, tag="!!str", value=value, parent=parent)
        if tags.resolve_plain(value) != "!!str" or value == "":
            node.style = Style.DOUBLE_QUOTED
        return node
    raise FormatError(f"unsupported JSON value {value!r}", format="json")


class JsonDecoder:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self._decoder = json.JSONDecoder(
            object_pairs_hook=_pairs_hook, parse_int=_Raw, parse_float=_Raw, parse_constant=_Raw,
        )

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="json", filename=filename)
        pos = 0
        index = 0
        n = len(text)
        while True:
            while pos < n and text[pos] in " \t\r\n":
                pos += 1
            if pos >= n:
                return
            try:
                value, pos = self._decoder.raw_decode(text, pos)
            except json.JSONDecodeError as e:
                raise FormatError(f"bad JSON: {e.msg}", format="json", filename=filename,
                                  line=e.lineno, column=e.colno) from None
            except RecursionError:
                raise FormatError("JSON nesting too deep", format="json", filename=filename) from None
            node = _to_node(value)
            node.document_index = index
            node.filename = filename
            node.file_index = file_index
            index += 1
            yield node


def _json_number(node: Node) -> str:
    tag = node.guess_tag()
    value = node.value
    if tag == "!!int":
        try:
            return str(tags.parse_int(value)[1])
        except ValueError:
            return json.dumps(value)
    try:
        number = tags.parse_float(value)
    except ValueError:
        return json.dumps(value)
    if math.isnan(number) or math.isinf(number):
        return "null"
    if _is_json_number_literal(value):
        return value
    text = repr(number)
    if "e" in text or "E" in text:
        mantissa, exp = text.split("e")
        exp_int = int(exp)
        return f"{mantissa}e{'+' if exp_int >= 0 else '-'}{abs(exp_int):02d}"
    if "." not in text:
        text += ".0"
    return text


def _is_json_number_literal(s: str) -> bool:
    import re

    return re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?", s) is not None \
        and any(c in s for c in ".eE")


class JsonEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = True) -> None:
        self.options = options or Options()
        self.indent = self.options.indent
        self.unwrap_scalar = unwrap_scalar

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None

    def print_leading_content(self, out: TextIO, content: str) -> None:
        return None

    def encode(self, out: TextIO, node: Node) -> None:
        if node.kind is Kind.SCALAR and self.unwrap_scalar:
            out.write(node.value + "\n")
            return
        out.write(self.encode_value(node, 0) + "\n")

    def encode_value(self, node: Node, level: int) -> str:
        node = node.resolve_alias()
        if node.kind is Kind.SCALAR:
            return self._scalar(node)
        indent = self.indent
        if node.kind is Kind.MAPPING:
            if not node.content:
                return "{}"
            items = []
            for key, value in node.map_items():
                items.append((json.dumps(key.value, ensure_ascii=False),
                              self.encode_value(value, level + 1)))
            if indent <= 0:
                return "{" + ",".join(f"{k}:{v}" for k, v in items) + "}"
            pad = " " * (indent * (level + 1))
            end = " " * (indent * level)
            return "{\n" + ",\n".join(f"{pad}{k}: {v}" for k, v in items) + "\n" + end + "}"
        if node.kind is Kind.SEQUENCE:
            if not node.content:
                return "[]"
            items = [self.encode_value(c, level + 1) for c in node.content]
            if indent <= 0:
                return "[" + ",".join(items) + "]"
            pad = " " * (indent * (level + 1))
            end = " " * (indent * level)
            return "[\n" + ",\n".join(pad + i for i in items) + "\n" + end + "]"
        return "null"

    @staticmethod
    def _scalar(node: Node) -> str:
        tag = node.guess_tag()
        if tag == "!!null":
            return "null"
        if tag == "!!bool":
            return "true" if node.is_truthy() else "false"
        if tag in ("!!int", "!!float"):
            return _json_number(node)
        return json.dumps(node.value, ensure_ascii=False)
