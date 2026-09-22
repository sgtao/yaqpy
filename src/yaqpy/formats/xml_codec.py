"""XML decoder / encoder (a port of yq's ``decoder_xml.go`` and ``encoder_xml.go``).

Conversion rules (the same as the Go yq, so scripts move between the two):

* an element becomes a map key; its children become the map value; a repeated child name
  becomes a list;
* attributes are keys with the attribute prefix (``+@name``); text next to attributes or children
  goes to the ``+content`` key;
* ``<?target ...?>`` becomes the key ``+p_target``; ``<!DOCTYPE ...>`` becomes ``+directive``
  (kept as raw text, never interpreted);
* every text value is a string (``"4"``, not ``4``); use ``from_yaml`` / tag conversions to type it;
* comments become YAML comments (head, line and foot) and come back on output.

Security: entities that the document declares are **not** expanded (the text ``&name;`` stays as
it is, like the Go decoder), nothing is fetched, and no external DTD is read. The input size
(``Limits.max_input_bytes``) and the element depth are limited: at most ``MAX_DEPTH`` levels,
or ``Limits.max_depth`` when that is smaller (the conversion recurses, so the depth has to stay
far below Python's recursion limit).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TextIO

from yaqpy.core.model.leading import DOC_SEPARATOR_MARKER
from yaqpy.core.model.depth import node_depth
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import FormatError
from yaqpy.formats import xml_tokens as xt
from yaqpy.formats.base import DecodeBudget
from yaqpy.options import Options

MAX_DEPTH = 200
"""Deepest element nesting the XML codec accepts (both directions)."""

# ============================================================================ decoder


class _Kv:
    """One child name with all the elements that share it (Go's ``xmlChildrenKv``)."""

    __slots__ = ("key", "nodes", "foot")

    def __init__(self, key: str, node: _XmlNode) -> None:
        self.key = key
        self.nodes = [node]
        self.foot = ""


class _XmlNode:
    __slots__ = ("children", "index", "head", "foot", "line", "data")

    def __init__(self, data: list[str] | None = None) -> None:
        self.children: list[_Kv] = []
        self.index: dict[str, _Kv] = {}
        self.head = ""
        self.foot = ""
        self.line = ""
        self.data: list[str] = data if data is not None else []

    def add_child(self, name: str, node: _XmlNode) -> None:
        kv = self.index.get(name)
        if kv is None:
            kv = _Kv(name, node)
            self.index[name] = kv
            self.children.append(kv)
        else:
            kv.nodes.append(node)


class _Element:
    __slots__ = ("parent", "node", "label", "state")

    def __init__(self, parent: _Element | None, node: _XmlNode, label: str = "") -> None:
        self.parent = parent
        self.node = node
        self.label = label
        self.state = ""


_COMMENT_PREFIX = re.compile(r"(^|\n)([A-Za-z])")


def _join(parts: list[str], sep: str) -> str:
    return sep.join(p for p in parts if p != "")


def _process_comment(comment: str) -> str:
    """Go's ``processComment``: XML comment text -> YAML comment (``#`` on every line)."""
    if comment == "":
        return ""
    replaced = _COMMENT_PREFIX.sub(r"\1 \2", comment)
    return "#" + replaced.rstrip(" ").replace("\n", "\n#")


_ASCII_NON_GRAPHIC = "".join(chr(c) for c in range(0x21)) + "\x7f"


def _trim_non_graphic(text: str) -> str:
    """Go's ``trimNonGraphic``: drop leading and trailing non-graphic characters and spaces."""
    if text.isascii():
        return text.strip(_ASCII_NON_GRAPHIC)
    first = -1
    last = -1
    for i, ch in enumerate(text):
        if not ch.isprintable() or ch.isspace():
            continue
        if first < 0:
            first = i
        last = i
    if first < 0:
        return ""
    return text[first:last + 1]


def _scalar(value: str) -> Node:
    return Node(Kind.SCALAR, tag="!!str", value=value)


def _null() -> Node:
    return Node(Kind.SCALAR, tag="!!null", value="")


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


class XmlDecoder:
    def __init__(self, options: Options | None = None) -> None:
        self.options = options or Options()
        self.prefs = self.options.xml

    # ------------------------------------------------------------------ conversion

    def _create_sequence(self, nodes: list[_XmlNode]) -> Node:
        seq = Node.sequence()
        for child in nodes:
            _append_item(seq, self._convert(child))
        return seq

    def _value_from_data(self, values: list[str]) -> Node:
        if not values:
            return _null()
        if len(values) == 1:
            return _scalar(values[0])
        seq = Node.sequence()
        for value in values:
            _append_item(seq, _scalar(value))
        return seq

    def _create_map(self, n: _XmlNode) -> Node:
        node = Node.mapping()
        if n.data:
            label = _scalar(self.prefs.content_name)
            label.head_comment = _process_comment(n.head)
            label.line_comment = _process_comment(n.line)
            label.foot_comment = _process_comment(n.foot)
            _append_pair(node, label, self._value_from_data(n.data))
        for i, kv in enumerate(n.children):
            label = _scalar(kv.key)
            if i == 0:
                label.head_comment = _process_comment(n.head)
            label.foot_comment = _process_comment(kv.foot)
            children = kv.nodes
            if len(children) > 1:
                value = self._create_sequence(children)
            else:
                child = children[0]
                # a comment before a scalar moves to its key (or becomes a line comment)
                if not child.children and child.head != "":
                    if child.data:
                        label.head_comment = _join([label.head_comment, child.head.strip()], "\n")
                        child.head = ""
                    else:
                        child.line = child.head
                        child.head = ""
                value = self._convert(child)
            _append_pair(node, label, value)
        return node

    def _convert(self, n: _XmlNode) -> Node:
        if n.children:
            return self._create_map(n)
        scalar = self._value_from_data(n.data)
        scalar.head_comment = _process_comment(n.head)
        scalar.line_comment = _process_comment(n.line)
        if scalar.tag == "!!seq":
            scalar.content[0].head_comment = scalar.line_comment
            scalar.line_comment = ""
        scalar.foot_comment = _process_comment(n.foot)
        return scalar

    # ------------------------------------------------------------------ tokens -> tree

    def _read(self, text: str, root: _XmlNode, budget: DecodeBudget | None = None) -> None:
        prefs = self.prefs
        max_depth = min(self.options.limits.max_depth, MAX_DEPTH)
        elem: _Element | None = _Element(None, root)
        started = False
        depth = 0
        for token in xt.tokens(text, strict=prefs.strict_mode, raw=prefs.raw_token):
            if budget is not None:
                budget.tick()
            if isinstance(token, xt.StartElement):
                if elem is None:
                    elem = _Element(None, _XmlNode())     # a start tag after a stray end tag
                elem.state = "started"
                space, local = token.name
                label = f"{space}:{local}" if prefs.keep_namespace and space else local
                depth += 1
                if depth > max_depth:
                    raise FormatError(f"XML nesting too deep (more than {max_depth} levels)",
                                      format="xml")
                elem = _Element(elem, _XmlNode(), label)
                for (a_space, a_local), value in token.attrs:
                    name = f"{a_space}:{a_local}" if prefs.keep_namespace and a_space else a_local
                    elem.node.add_child(prefs.attribute_prefix + name, _XmlNode([value]))
            elif isinstance(token, xt.CharData):
                bit = _trim_non_graphic(token.text)
                if not started and bit:
                    raise FormatError(f"invalid XML: Encountered chardata [{bit}] outside of XML node",
                                      format="xml")
                if bit and elem is not None:
                    elem.node.data.append(bit)
                    elem.state = "chardata"
            elif isinstance(token, xt.EndElement):
                depth = max(0, depth - 1)
                if elem is None:
                    continue
                elem.state = "finished"
                if elem.parent is not None:
                    elem.parent.node.add_child(elem.label, elem.node)
                elem = elem.parent
            elif isinstance(token, xt.Comment):
                if elem is None:
                    continue
                if elem.state == "started":
                    _apply_foot_comment(elem, token.text)
                elif elem.state == "chardata":
                    elem.node.line = _join([elem.node.line, token.text], " ")
                else:
                    elem.node.head = _join([elem.node.head, token.text], " ")
            elif isinstance(token, xt.ProcInst):
                if not prefs.skip_proc_inst and elem is not None:
                    elem.node.add_child(prefs.proc_inst_prefix + token.target, _XmlNode([token.inst]))
            elif isinstance(token, xt.Directive):
                if not prefs.skip_directives and elem is not None:
                    elem.node.add_child(prefs.directive_name, _XmlNode([token.text]))
            started = True

    def decode_documents(self, text: str, *, filename: str = "", file_index: int = 0,
                         process_leading: bool = True,
                         budget: DecodeBudget | None = None) -> Iterator[Node]:
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8", "surrogatepass")) > self.options.limits.max_input_bytes:
            raise FormatError("input exceeds max_input_bytes", format="xml", filename=filename)
        root = _XmlNode()
        try:
            self._read(text, root, budget)
            node = self._convert(root)
        except RecursionError:
            raise FormatError("XML nesting too deep", format="xml", filename=filename) from None
        except FormatError as e:
            if filename and not e.message.startswith("bad file"):
                raise FormatError(f"bad file '{filename}': {e.message}", format="xml",
                                  filename=filename, line=e.line, column=e.column) from None
            raise
        node.document_index = 0
        node.filename = filename
        node.file_index = file_index
        yield node


def _apply_foot_comment(elem: _Element, comment: str) -> None:
    """A comment right after a start tag: it belongs to the last child, or to the element itself."""
    node = elem.node
    if node.children:
        kv = node.children[-1]
        if kv.nodes and not kv.nodes[0].children:
            target = kv.nodes[-1]
            target.foot = _join([target.foot, comment], " ")
        else:
            kv.foot = _join([node.foot, comment], " ")
    else:
        node.foot = _join([node.foot, comment], " ")


# ============================================================================ encoder

_ESCAPE = {
    '"': "&#34;", "'": "&#39;", "&": "&amp;", "<": "&lt;", ">": "&gt;", "\t": "&#x9;", "\r": "&#xD;",
}
_ESCAPE_TEXT = str.maketrans(_ESCAPE)
_ESCAPE_ATTR = str.maketrans({**_ESCAPE, "\n": "&#xA;"})
_ILLEGAL_CHAR = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")
_BAD_NAME_CHARS = re.compile(r"[\s<>&\"'=/]")


def _escape(text: str, table: dict[int, str]) -> str:
    return _ILLEGAL_CHAR.sub("�", text.translate(table))


class _Printer:
    """The output side of Go's ``xml.Encoder`` with ``Indent("", indent)``: indentation follows
    start and end tags only; text, comments, processing instructions and directives are inline."""

    def __init__(self, indent: str) -> None:
        self.indent = indent
        self.parts: list[str] = []
        self.depth = 0
        self.indented_in = False
        self.put_newline = False
        self.tags: list[str] = []
        self.written = False

    def _write_indent(self, delta: int) -> None:
        if not self.indent:
            return
        if delta < 0:
            self.depth -= 1
            if self.indented_in:
                self.indented_in = False
                return
            self.indented_in = False
        if self.put_newline:
            self.parts.append("\n")
        else:
            self.put_newline = True
        self.parts.append(self.indent * self.depth)
        if delta > 0:
            self.depth += 1
            self.indented_in = True

    def _put(self, text: str) -> None:
        self.parts.append(text)
        self.written = True

    def raw(self, text: str) -> None:
        """Written straight to the output (Go: ``e.writer.Write``), outside the indentation state."""
        self.parts.append(text)

    def start(self, name: str, attrs: list[tuple[str, str]]) -> None:
        if not name:
            raise FormatError("xml: start tag with no name", format="xml")
        _check_name(name)
        self.tags.append(name)
        self._write_indent(1)
        out = ["<", name]
        for attr_name, value in attrs:
            if not attr_name:
                continue
            _check_name(attr_name)
            out.append(f' {attr_name}="{_escape(value, _ESCAPE_ATTR)}"')
        out.append(">")
        self._put("".join(out))

    def end(self, name: str) -> None:
        if not self.tags or self.tags[-1] != name:
            raise FormatError(f"xml: end tag </{name}> does not match the open element", format="xml")
        self.tags.pop()
        self._write_indent(-1)
        self._put(f"</{name}>")

    def char_data(self, text: str) -> None:
        self._put(_escape(text, _ESCAPE_TEXT))

    def comment(self, text: str) -> None:
        if "-->" in text:
            raise FormatError("xml: EncodeToken of Comment containing --> marker", format="xml")
        self._put(f"<!--{text}-->")

    def proc_inst(self, target: str, inst: str) -> None:
        if target == "xml" and self.written:
            raise FormatError("xml: EncodeToken of ProcInst xml target only valid for xml "
                              "declaration, first token encoded", format="xml")
        if not xt.is_name(target):
            raise FormatError("xml: EncodeToken of ProcInst with invalid Target", format="xml")
        if "?>" in inst:
            raise FormatError("xml: EncodeToken of ProcInst containing ?> marker", format="xml")
        self._put(f"<?{target} {inst}?>" if inst else f"<?{target}?>")

    def directive(self, text: str) -> None:
        if not xt.is_valid_directive(text):
            raise FormatError("xml: EncodeToken of Directive containing wrong < or --> markers",
                              format="xml")
        self._put(f"<!{text}>")

    def text(self) -> str:
        return "".join(self.parts)


def _check_name(name: str) -> None:
    """Element and attribute names may not contain characters that would break the markup.

    Go writes whatever it is given; yaqpy refuses instead of producing a broken document.
    (``+@name`` style names from the ``+@+@name`` case are still accepted, like in Go.)
    """
    if _BAD_NAME_CHARS.search(name):
        raise FormatError(f"xml: {name!r} cannot be used as an element or attribute name",
                          format="xml")


_MULTILINE_COMMENT = re.compile(r"(^|\n) *# ?(.*)")
_SINGLE_LINE_COMMENT = re.compile(r"^[ \t\n\f\r]*#(.*)\n?")


def _head(node: Node) -> str:
    return node.head_comment.replace("#", "", 1)


def _line(node: Node) -> str:
    return node.line_comment.replace("#", "", 1)


def _foot(node: Node) -> str:
    return node.foot_comment.replace("#", "", 1)


def _head_and_line(node: Node) -> str:
    return _head(node) + _line(node)


def _content_text(value: Node) -> str:
    """The text of a ``+content`` value. Text that was split by child elements or comments comes
    back as a list; its pieces are written one after the other, separated by a space (the
    position between the children is not kept, the words are)."""
    if value.kind is Kind.SCALAR:
        return value.value
    if value.kind is Kind.SEQUENCE and all(item.kind is Kind.SCALAR for item in value.content):
        return " ".join(item.value for item in value.content)
    raise FormatError(f"cannot use {value.tag} as the text of an element, only scalars and lists "
                      "of scalars are supported", format="xml")


class XmlEncoder:
    def __init__(self, options: Options | None = None, *, unwrap_scalar: bool = False) -> None:
        self.options = options or Options()
        self.prefs = self.options.xml
        self.unwrap_scalar = unwrap_scalar
        self.indent = " " * self.prefs.indent
        self._leading = ""

    def can_handle_aliases(self) -> bool:
        return False

    def print_document_separator(self, out: TextIO) -> None:
        return None

    def print_leading_content(self, out: TextIO, content: str) -> None:
        lines = [ln for ln in content.splitlines(keepends=True) if DOC_SEPARATOR_MARKER not in ln]
        self._leading = "".join(lines)

    # ------------------------------------------------------------------ entry point

    def encode(self, out: TextIO, node: Node) -> None:
        limit = min(self.options.limits.max_depth, MAX_DEPTH)
        if node_depth(node, limit + 1) > limit + 1:      # + the value under the innermost element
            raise FormatError(f"XML nesting too deep (more than {limit} levels)", format="xml")
        try:
            out.write(self._encode(node))
        except RecursionError:
            raise FormatError("XML nesting too deep", format="xml") from None

    def _encode(self, node: Node) -> str:
        p = _Printer(self.indent)
        xml_key = self.prefs.proc_inst_prefix + "xml"
        if node.tag == "!!map":
            # the <?xml ... ?> declaration always comes first
            for key, value in node.map_items():
                if key.value == xml_key:
                    p.proc_inst("xml", value.value)
                    p.raw("\n")
        if self._leading != "":
            self._comment(p, self._leading)
            p.char_data("\n")
        if node.kind is Kind.MAPPING:
            self._top_level_map(p, node)
        elif node.kind is Kind.SCALAR:
            p.char_data(node.value)
            return p.text()
        else:
            raise FormatError(f"cannot encode {node.tag} to XML - only maps can be encoded",
                              format="xml")
        p.char_data("\n")
        return p.text()

    # ------------------------------------------------------------------ pieces

    def _comment(self, p: _Printer, comment: str) -> None:
        if comment == "":
            return
        raw = comment.encode("utf-8")
        if len(raw) > 2 and b"\n" in raw[1:-1]:
            if comment.endswith("\n"):
                comment = comment[:-1]
            comment = _MULTILINE_COMMENT.sub(r"\1\2", comment)
            if comment[:1] not in ("\n", " "):
                comment = " " + comment
        else:
            comment = _SINGLE_LINE_COMMENT.sub(r"\1", comment)
        if not comment.endswith((" ", "\n")):
            comment += " "
        p.comment(comment)

    def _top_level_map(self, p: _Printer, node: Node) -> None:
        prefs = self.prefs
        self._comment(p, _head_and_line(node))
        xml_key = prefs.proc_inst_prefix + "xml"
        for key, value in node.map_items():
            self._comment(p, _head_and_line(key))
            if _head_and_line(key) != "":
                p.char_data("\n")
            if key.value == xml_key:
                pass                              # already written first
            elif key.value.startswith(prefs.proc_inst_prefix):
                p.proc_inst(key.value.replace(prefs.proc_inst_prefix, "", 1), value.value)
                p.raw("\n")
            elif key.value == prefs.directive_name:
                p.directive(value.value)
                p.raw("\n")
            else:
                self._do_encode(p, value, key.value)
            self._comment(p, _foot(key))
        self._comment(p, _foot(node))

    def _encode_start(self, p: _Printer, node: Node, name: str, attrs: list[tuple[str, str]]) -> None:
        p.start(name, attrs)
        self._comment(p, _head(node))

    def _encode_end(self, p: _Printer, node: Node, name: str) -> None:
        p.end(name)
        self._comment(p, _foot(node))

    def _do_encode(self, p: _Printer, node: Node, name: str) -> None:
        if node.kind is Kind.MAPPING:
            self._encode_map(p, node, name)
        elif node.kind is Kind.SEQUENCE:
            self._encode_array(p, node, name)
        elif node.kind is Kind.SCALAR:
            self._encode_start(p, node, name, [])
            p.char_data(node.value)
            self._comment(p, _line(node))
            self._encode_end(p, node, name)
        else:
            raise FormatError(f"unsupported type {node.tag}", format="xml")

    def _encode_array(self, p: _Printer, node: Node, name: str) -> None:
        self._comment(p, _head_and_line(node))
        for value in node.content:
            self._do_encode(p, value, name)
        self._comment(p, _foot(node))

    def _is_attribute(self, name: str) -> bool:
        prefs = self.prefs
        return (name.startswith(prefs.attribute_prefix)
                and name != prefs.content_name
                and name != prefs.directive_name
                and not name.startswith(prefs.proc_inst_prefix))

    def _encode_map(self, p: _Printer, node: Node, name: str) -> None:
        prefs = self.prefs
        attrs: list[tuple[str, str]] = []
        for key, value in node.map_items():
            if self._is_attribute(key.value):
                if value.kind is not Kind.SCALAR:
                    raise FormatError(
                        f"cannot use {value.tag} as attribute, only scalars are supported",
                        format="xml")
                attrs.append((key.value.replace(prefs.attribute_prefix, "", 1), value.value))
        self._encode_start(p, node, name, attrs)
        for key, value in node.map_items():
            self._comment(p, _head_and_line(key))
            if key.value.startswith(prefs.proc_inst_prefix):
                p.proc_inst(key.value.replace(prefs.proc_inst_prefix, "", 1), value.value)
            elif key.value == prefs.directive_name:
                p.directive(value.value)
            elif key.value == prefs.content_name:
                self._comment(p, _head_and_line(value))
                p.char_data(_content_text(value))
                self._comment(p, _foot(value))
            elif not self._is_attribute(key.value):
                self._do_encode(p, value, key.value)
            self._comment(p, _foot(key))
        self._encode_end(p, node, name)
