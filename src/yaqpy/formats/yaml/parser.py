"""YAML text -> Node trees (design doc 9-3).

This is a hand written, line oriented block/flow parser that builds ``Node``
objects directly (parser and composer are merged for simplicity; comment
assignment follows go-yaml v3 as closely as practical, see the design doc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from yaqpy.core.model.node import Kind, Node, Style
from yaqpy.errors import YamlSyntaxError
from yaqpy.formats.base import DecodeBudget
from yaqpy.formats.yaml.resolver import resolve_plain

_FLOW_END = set(",]}")
_ANCHOR_END = set(" \t,[]{}")
_TAG_END = set(" \t,[]{}")
_DOC_START = re.compile(r"^---(?:[ \t]|$)")
_DOC_END = re.compile(r"^\.\.\.(?:[ \t]|$)")


@dataclass(slots=True)
class CommentGroup:
    column: int
    lines: list[str]
    blank_after: bool = False
    blank_before: bool = False

    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(slots=True)
class _Line:
    text: str
    indent: int
    blank: bool
    comment: bool


@dataclass(slots=True)
class ParseResult:
    documents: list[Node] = field(default_factory=list)


class YamlParser:
    def __init__(self, text: str, *, filename: str = "", line_offset: int = 0,
                 max_depth: int = 1000, anchors: dict[str, Node] | None = None,
                 budget: DecodeBudget | None = None) -> None:
        self.filename = filename
        self.line_offset = line_offset
        self.max_depth = max_depth
        self.anchors: dict[str, Node] = anchors if anchors is not None else {}
        self._budget = budget
        raw_lines = text.split("\n")
        if raw_lines and raw_lines[-1] == "":
            raw_lines.pop()
        self.lines: list[_Line] = []
        for raw in raw_lines:
            if raw.endswith("\r"):
                raw = raw[:-1]
            stripped = raw.lstrip(" ")
            indent = len(raw) - len(stripped)
            blank = stripped.strip(" \t") == ""
            comment = stripped.startswith("#")
            self.lines.append(_Line(raw, indent, blank, comment))
        self.li = 0
        self.pending: list[CommentGroup] = []
        self._depth = 0

    # ------------------------------------------------------------------ utilities

    def _error(self, message: str, li: int | None = None, col: int = 0) -> YamlSyntaxError:
        line_no = (self.li if li is None else li) + 1 + self.line_offset
        return YamlSyntaxError(message, line=line_no, column=col + 1, filename=self.filename)

    def _tick(self) -> None:
        """巨大な文書のデコード中でも中止・タイムアウトが効くように、主要な走査ループごとに呼ぶ

        （5-4 節 U1。評価と同じ ``StepBudget`` を共有するので、中止フラグと締切の両方に反応する）。
        """
        if self._budget is not None:
            self._budget.tick()

    def eof(self) -> bool:
        return self.li >= len(self.lines)

    def line(self) -> _Line:
        return self.lines[self.li]

    def _is_doc_marker(self, li: int) -> bool:
        if li >= len(self.lines):
            return False
        text = self.lines[li].text
        return bool(_DOC_START.match(text) or _DOC_END.match(text))

    def collect_comments(self) -> list[CommentGroup]:
        """Consume blank and comment-only lines; return them grouped."""
        groups: list[CommentGroup] = list(self.pending)
        self.pending = []
        current: CommentGroup | None = None
        saw_blank = False
        while not self.eof():
            ln = self.line()
            if ln.blank:
                if current is not None:
                    current.blank_after = True
                    current = None
                saw_blank = True
                self.li += 1
                continue
            if ln.comment:
                if ln.text.lstrip(" ").startswith("#") and "\t" in ln.text[:ln.indent]:
                    raise self._error("found a tab character where an indentation space is expected")
                if current is None:
                    current = CommentGroup(ln.indent, [], blank_before=saw_blank)
                    groups.append(current)
                current.lines.append(ln.text.strip())
                saw_blank = False
                self.li += 1
                continue
            break
        return groups

    # ------------------------------------------------------------------ stream

    def parse_stream(self) -> list[Node]:
        documents: list[Node] = []
        while True:
            self._tick()
            doc = self.parse_document(first=not documents)
            if doc is None:
                break
            documents.append(doc)
        return documents

    def parse_document(self, *, first: bool) -> Node | None:
        groups = self.collect_comments()
        # directives
        while not self.eof() and self.line().text.startswith("%"):
            self.li += 1
            groups.extend(self.collect_comments())
        explicit_start = False
        inline_col: int | None = None
        if not self.eof() and _DOC_START.match(self.line().text):
            explicit_start = True
            rest = self.line().text[3:]
            stripped = rest.lstrip(" \t")
            if stripped and not stripped.startswith("#"):
                inline_col = len(self.line().text) - len(stripped)
            elif stripped.startswith("#"):
                groups.append(CommentGroup(0, [stripped.strip()]))
                self.li += 1
            else:
                self.li += 1
        if not explicit_start and (self.eof() or _DOC_END.match(self.line().text)):
            if not self.eof() and _DOC_END.match(self.line().text):
                self.li += 1
                return self._empty_document(groups)
            if groups and first:
                return self._empty_document(groups)
            self.pending = groups
            return None
        if inline_col is not None:
            root = self._parse_node_at(self.li, inline_col, parent_indent=-1, allow_seq_same_indent=False)
        else:
            groups.extend(self.collect_comments())
            if self.eof() or self._is_doc_marker(self.li):
                root = self._empty_document(groups)
                groups = []
            else:
                root = self._parse_node_at(self.li, self.line().indent, parent_indent=-1,
                                           allow_seq_same_indent=False)
        if groups:
            root.head_comment = _join_comments([g.text() for g in groups] + ([root.head_comment] if root.head_comment else []))
        trailing = self.collect_comments()
        if not self.eof() and _DOC_END.match(self.line().text):
            self.li += 1
            trailing.extend(self.collect_comments())
        if not self.eof() and not self._is_doc_marker(self.li):
            ln = self.line()
            raise self._error(f"did not find expected key or document marker near {ln.text.strip()[:20]!r}",
                              col=ln.indent)
        if trailing:
            root.foot_comment = _join_comments(([root.foot_comment] if root.foot_comment else [])
                                              + [g.text() for g in trailing])
        return root

    def _empty_document(self, groups: list[CommentGroup]) -> Node:
        node = Node.null(value="")
        node.line = self.li + self.line_offset
        if groups:
            node.head_comment = _join_comments([g.text() for g in groups])
        return node

    # ------------------------------------------------------------------ nodes

    def _parse_node_at(self, li: int, col: int, *, parent_indent: int,
                       allow_seq_same_indent: bool) -> Node:
        """Parse the node whose first character is at (li, col)."""
        self._depth += 1
        if self._depth > self.max_depth:
            raise self._error("document nesting too deep")
        try:
            return self._parse_node_inner(li, col, parent_indent, allow_seq_same_indent)
        finally:
            self._depth -= 1

    def _parse_node_inner(self, li: int, col: int, parent_indent: int,
                          allow_seq_same_indent: bool) -> Node:
        self.li = li
        text = self.line().text
        if text[col:col + 1] == "\t":
            raise self._error("found a tab character where an indentation space is expected", col=col)
        anchor, tag, ci = self._parse_properties(text, col)
        rest = text[ci:]
        rest_stripped = rest.lstrip(" \t")
        if (anchor or tag) and (rest_stripped == "" or rest_stripped.startswith("#")):
            # properties on their own line; content follows
            line_comment = rest_stripped.strip() if rest_stripped.startswith("#") else ""
            self.li += 1
            groups = self.collect_comments()
            if self.eof() or self._is_doc_marker(self.li) or self.line().indent <= parent_indent:
                node = Node.null(value="")
                self.pending = groups
            else:
                nxt = self.line()
                if nxt.indent == col and not (allow_seq_same_indent and nxt.text[col:].startswith("-")):
                    # e.g. `key: &a\n  x: 1` requires deeper indent; `&a\nx: 1` at root is fine
                    if parent_indent >= 0 and col <= parent_indent:
                        node = Node.null(value="")
                        self.pending = groups
                    else:
                        self.pending = groups
                        node = self._parse_node_at(self.li, nxt.indent, parent_indent=parent_indent,
                                                   allow_seq_same_indent=allow_seq_same_indent)
                else:
                    self.pending = groups
                    node = self._parse_node_at(self.li, nxt.indent, parent_indent=parent_indent,
                                               allow_seq_same_indent=allow_seq_same_indent)
            self._apply_properties(node, anchor, tag)
            if line_comment and not node.line_comment:
                node.line_comment = line_comment
            node.line = li + 1 + self.line_offset
            node.column = col + 1
            return node
        # value on this line
        if rest.startswith("-") and (len(rest) == 1 or rest[1] in " \t"):
            node = self._parse_block_sequence(li, ci)
        elif rest.startswith("?") and (len(rest) == 1 or rest[1] in " \t"):
            node = self._parse_block_mapping(li, ci)
        elif self._is_implicit_key(li, ci):
            if anchor or tag:
                # `!!merge <<: *a` / `&x key: v`: the properties belong to the key, and the
                # mapping's column is where the key (including its properties) starts.
                return self._parse_block_mapping(li, col)
            node = self._parse_block_mapping(li, ci)
        else:
            pending = self.pending
            self.pending = []
            node = self._parse_inline_value(li, ci, parent_indent)
            if pending:
                node.head_comment = _join_comments([*(g.text() for g in pending), node.head_comment])
        self._apply_properties(node, anchor, tag)
        return node

    def _apply_properties(self, node: Node, anchor: str, tag: str) -> None:
        if anchor:
            node.anchor = anchor
            self.anchors[anchor] = node
        if tag:
            node.tag = tag
            node.style |= Style.TAGGED
            if tag == "!!str" and node.kind is Kind.SCALAR:
                pass

    def _parse_properties(self, text: str, ci: int) -> tuple[str, str, int]:
        anchor = ""
        tag = ""
        n = len(text)
        while ci < n:
            ch = text[ci]
            if ch == "&" and not anchor:
                end = ci + 1
                while end < n and text[end] not in _ANCHOR_END:
                    end += 1
                anchor = text[ci + 1:end]
                if anchor == "":
                    raise self._error("anchor name cannot be empty", col=ci)
                ci = end
            elif ch == "!" and not tag:
                end = ci + 1
                if end < n and text[end] == "<":
                    close = text.find(">", end)
                    if close < 0:
                        raise self._error("unterminated verbatim tag", col=ci)
                    end = close + 1
                else:
                    while end < n and text[end] not in _TAG_END:
                        end += 1
                tag = text[ci:end]
                ci = end
            else:
                break
            while ci < n and text[ci] in " \t":
                ci += 1
        return anchor, tag, ci

    # ------------------------------------------------------------------ keys

    def _scan_key(self, text: str, ci: int) -> tuple[str, Style, int] | None:
        """If an implicit key starts at ci, return (key_text, style, index_after_colon)."""
        n = len(text)
        if ci >= n:
            return None
        ch = text[ci]
        if ch in "\"'":
            end = self._find_quote_end(text, ci)
            if end < 0:
                return None
            raw = text[ci:end + 1]
            after = end + 1
            j = after
            while j < n and text[j] in " \t":
                j += 1
            if j < n and text[j] == ":" and (j + 1 >= n or text[j + 1] in " \t"):
                value = _unquote_double(raw[1:-1], self, ci) if ch == '"' else raw[1:-1].replace("''", "'")
                return value, (Style.DOUBLE_QUOTED if ch == '"' else Style.SINGLE_QUOTED), j + 1
            return None
        if ch in "[{":
            return None
        if ch == "*":
            end = ci + 1
            while end < n and text[end] not in _ANCHOR_END and text[end] != ":":
                end += 1
            j = end
            while j < n and text[j] in " \t":
                j += 1
            if j < n and text[j] == ":" and (j + 1 >= n or text[j + 1] in " \t"):
                return text[ci:end], Style.NONE, j + 1
            return None
        # plain key: scan for ": " or ":" at end (not inside)
        j = ci
        while j < n:
            c = text[j]
            if c == ":" and (j + 1 >= n or text[j + 1] in " \t"):
                key = text[ci:j].rstrip(" \t")
                if key == "" or " #" in key or key.startswith("#"):
                    return None
                return key, Style.NONE, j + 1
            if c == "#" and j > ci and text[j - 1] in " \t":
                return None
            j += 1
        return None

    def _is_implicit_key(self, li: int, ci: int) -> bool:
        text = self.lines[li].text
        return self._scan_key(text, ci) is not None

    @staticmethod
    def _find_quote_end(text: str, start: int) -> int:
        quote = text[start]
        i = start + 1
        n = len(text)
        while i < n:
            c = text[i]
            if quote == '"' and c == "\\":
                i += 2
                continue
            if c == quote:
                if quote == "'" and i + 1 < n and text[i + 1] == "'":
                    i += 2
                    continue
                return i
            i += 1
        return -1

    # ------------------------------------------------------------------ block mapping

    def _parse_block_mapping(self, li: int, col: int) -> Node:
        node = Node.mapping()
        node.line = li + 1 + self.line_offset
        node.column = col + 1
        self.li = li
        first = True
        last_key: Node | None = None
        while True:
            self._tick()
            if first:
                groups: list[CommentGroup] = self.pending
                self.pending = []
                ln = self.line()
            else:
                groups = self.collect_comments()
                if self.eof() or self._is_doc_marker(self.li):
                    self._attach_trailing(groups, node, last_key, col)
                    break
                ln = self.line()
                if ln.indent != col or ln.text[col:].startswith("- ") or ln.text[col:] == "-":
                    if ln.indent > col:
                        raise self._error("bad indentation of a mapping entry", col=ln.indent)
                    self._attach_trailing(groups, node, last_key, col)
                    break
            text = ln.text
            if "\t" in text[:col] or text[col:col + 1] == "\t":
                raise self._error("found a tab character where an indentation space is expected")
            key_line = self.li
            if text[col:].startswith("?") and (len(text) == col + 1 or text[col + 1] in " \t"):
                key = self._parse_complex_key(self.li, col)
                after = self._after_complex_key(col)
                if after is None:
                    value = Node.null(value="")
                else:
                    value = self._parse_mapping_value(after, col)
            else:
                anchor, tag, ci = self._parse_properties(text, col)
                scanned = self._scan_key(text, ci)
                if scanned is None:
                    raise self._error(f"could not find expected ':' near {text[col:col + 30]!r}", col=col)
                key_text, key_style, after_colon = scanned
                if text[ci] == "*" and key_style is Style.NONE:
                    key = self._make_alias(key_text[1:], key_line, ci)
                else:
                    key = Node(Kind.SCALAR, value=key_text, style=key_style)
                    key.tag = "!!str" if key_style is not Style.NONE else _resolve_key_tag(key_text)
                key.line = key_line + 1 + self.line_offset
                key.column = ci + 1
                self._apply_properties(key, anchor, tag)
                value = self._parse_mapping_value(after_colon, col, key)
            key.parent = node
            key.is_map_key = True
            value.parent = node
            value.key = key
            value.is_map_key = False
            self._attach_groups(groups, key, last_key, node, first)
            node.content.append(key)
            node.content.append(value)
            last_key = key
            first = False
        return node

    def _parse_mapping_value(self, after_colon: int, col: int, key: Node | None = None) -> Node:
        text = self.line().text
        ci = after_colon
        while ci < len(text) and text[ci] in " \t":
            ci += 1
        rest = text[ci:]
        if rest == "" or rest.startswith("#"):
            comment = rest.strip()
            self.li += 1
            groups = self.collect_comments()
            if self.eof() or self._is_doc_marker(self.li):
                value = Node.null(value="")
                self.pending = groups
            else:
                nxt = self.line()
                if nxt.indent > col or (nxt.indent == col and nxt.text[col:].startswith("-")
                                        and (len(nxt.text) == col + 1 or nxt.text[col + 1] in " \t")):
                    self.pending = groups
                    value = self._parse_node_at(self.li, nxt.indent, parent_indent=col,
                                                allow_seq_same_indent=True)
                else:
                    value = Node.null(value="")
                    self.pending = groups
            if comment:
                if key is not None and not key.line_comment:
                    key.line_comment = comment
                elif not value.line_comment:
                    value.line_comment = comment
            return value
        return self._parse_inline_value(self.li, ci, col)

    def _parse_complex_key(self, li: int, col: int) -> Node:
        text = self.lines[li].text
        ci = col + 1
        while ci < len(text) and text[ci] in " \t":
            ci += 1
        rest = text[ci:]
        if rest == "" or rest.startswith("#"):
            self.li += 1
            groups = self.collect_comments()
            if not self.eof() and self.line().indent > col:
                self.pending = groups
                return self._parse_node_at(self.li, self.line().indent, parent_indent=col,
                                           allow_seq_same_indent=False)
            self.pending = groups
            return Node.null(value="")
        return self._parse_node_at(li, ci, parent_indent=col, allow_seq_same_indent=False)

    def _after_complex_key(self, col: int) -> int | None:
        groups = self.collect_comments()
        self.pending = groups
        if self.eof():
            return None
        ln = self.line()
        if ln.indent == col and ln.text[col:].startswith(":") and (
            len(ln.text) == col + 1 or ln.text[col + 1] in " \t"
        ):
            self.pending = []
            return col + 1
        return None

    # ------------------------------------------------------------------ block sequence

    def _parse_block_sequence(self, li: int, col: int) -> Node:
        node = Node.sequence()
        node.line = li + 1 + self.line_offset
        node.column = col + 1
        self.li = li
        first = True
        last_item: Node | None = None
        while True:
            self._tick()
            if first:
                groups: list[CommentGroup] = self.pending
                self.pending = []
                ln = self.line()
                text = ln.text
            else:
                groups = self.collect_comments()
                if self.eof() or self._is_doc_marker(self.li):
                    self._attach_trailing(groups, node, last_item, col)
                    break
                ln = self.line()
                text = ln.text
                if ln.indent != col or not (text[col:].startswith("-")
                                            and (len(text) == col + 1 or text[col + 1] in " \t")):
                    if ln.indent > col:
                        raise self._error("bad indentation of a sequence entry", col=ln.indent)
                    self._attach_trailing(groups, node, last_item, col)
                    break
            if "\t" in text[:col]:
                raise self._error("found a tab character where an indentation space is expected")
            item_line = self.li
            ci = col + 1
            while ci < len(text) and text[ci] in " \t":
                ci += 1
            rest = text[ci:]
            if rest == "" or rest.startswith("#"):
                comment = rest.strip()
                self.li += 1
                inner = self.collect_comments()
                if not self.eof() and not self._is_doc_marker(self.li) and self.line().indent > col:
                    self.pending = inner
                    item = self._parse_node_at(self.li, self.line().indent, parent_indent=col,
                                               allow_seq_same_indent=False)
                else:
                    item = Node.null(value="")
                    self.pending = inner
                if comment and not item.line_comment:
                    item.line_comment = comment
            else:
                item = self._parse_node_at(item_line, ci, parent_indent=col,
                                           allow_seq_same_indent=False)
            key_node = Node.integer(len(node.content))
            key_node.parent = node
            key_node.is_map_key = True
            item.parent = node
            item.key = key_node
            item.is_map_key = False
            self._attach_groups(groups, item, last_item, node, first)
            node.content.append(item)
            last_item = item
            first = False
        return node

    # ------------------------------------------------------------------ comments

    def _attach_groups(self, groups: list[CommentGroup], next_node: Node, prev: Node | None,
                       container: Node, first: bool) -> None:
        if not groups:
            return
        head: list[str] = []
        for i, g in enumerate(groups):
            is_last = i == len(groups) - 1
            if is_last and not g.blank_after:
                head.append(g.text())
            elif prev is not None and g.column >= container.column - 1:
                prev.foot_comment = _join_comments([prev.foot_comment, g.text()])
            elif prev is None and first:
                head.append(g.text())
            else:
                head.append(g.text())
        if head:
            next_node.head_comment = _join_comments([next_node.head_comment, *head])

    def _attach_trailing(self, groups: list[CommentGroup], container: Node, last: Node | None,
                         col: int) -> None:
        if not groups:
            return
        mine: list[CommentGroup] = []
        outer: list[CommentGroup] = []
        for g in groups:
            (mine if g.column >= col and col > 0 else outer).append(g)
        if col == 0:
            # root level: everything belongs to the document (handled by parse_document)
            outer = groups
            mine = []
        if mine and last is not None:
            last.foot_comment = _join_comments([last.foot_comment, *[g.text() for g in mine]])
        elif mine:
            container.foot_comment = _join_comments([container.foot_comment, *[g.text() for g in mine]])
        self.pending = outer + self.pending

    # ------------------------------------------------------------------ inline values

    def _parse_inline_value(self, li: int, ci: int, block_indent: int) -> Node:
        self.li = li
        text = self.line().text
        anchor, tag, ci = self._parse_properties(text, ci)
        rest = text[ci:]
        stripped = rest.lstrip(" \t")
        if stripped == "" or stripped.startswith("#"):
            comment = stripped.strip()
            self.li += 1
            groups = self.collect_comments()
            if not self.eof() and not self._is_doc_marker(self.li) and self.line().indent > block_indent:
                self.pending = groups
                node = self._parse_node_at(self.li, self.line().indent, parent_indent=block_indent,
                                           allow_seq_same_indent=False)
            else:
                node = Node.null(value="")
                self.pending = groups
            self._apply_properties(node, anchor, tag)
            if comment and not node.line_comment:
                node.line_comment = comment
            return node
        ch = rest[0]
        if ch in "[{":
            node = self._parse_flow(li, ci)
        elif ch == '"':
            node = self._parse_double_quoted(li, ci)
        elif ch == "'":
            node = self._parse_single_quoted(li, ci)
        elif ch in "|>":
            node = self._parse_block_scalar(li, ci, block_indent)
        elif ch == "*":
            node = self._parse_alias(li, ci)
        else:
            node = self._parse_plain(li, ci, block_indent)
        node.line = li + 1 + self.line_offset
        node.column = ci + 1
        self._apply_properties(node, anchor, tag)
        return node

    def _finish_line(self, li: int, ci: int, node: Node) -> None:
        """Consume the rest of line ``li`` after a value; attach a trailing comment."""
        text = self.lines[li].text
        j = ci
        while j < len(text) and text[j] in " \t":
            j += 1
        if j < len(text):
            if text[j] == "#":
                node.line_comment = text[j:].strip()
            else:
                raise self._error(f"unexpected content after value: {text[j:j + 20]!r}", li, j)
        self.li = li + 1

    def _make_alias(self, name: str, li: int, ci: int) -> Node:
        if name == "":
            raise self._error("alias name cannot be empty", li, ci)
        target = self.anchors.get(name)
        if target is None:
            raise self._error(f"unknown anchor '{name}' referenced", li, ci)
        node = Node(Kind.ALIAS, value=name, alias=target)
        node.line = li + 1 + self.line_offset
        node.column = ci + 1
        return node

    def _parse_alias(self, li: int, ci: int) -> Node:
        text = self.lines[li].text
        end = ci + 1
        while end < len(text) and text[end] not in _ANCHOR_END:
            end += 1
        node = self._make_alias(text[ci + 1:end], li, ci)
        self._finish_line(li, end, node)
        return node

    def _parse_plain(self, li: int, ci: int, block_indent: int) -> Node:
        text = self.lines[li].text
        first_line, end = _scan_plain_block(text, ci)
        parts = [first_line]
        node = Node(Kind.SCALAR)
        comment_line = li
        comment_ci = end
        self.li = li + 1
        # continuation lines
        while True:
            j = self.li
            blanks = 0
            while j < len(self.lines) and self.lines[j].blank:
                blanks += 1
                j += 1
            if j >= len(self.lines) or self._is_doc_marker(j):
                break
            ln = self.lines[j]
            if ln.indent <= block_indent or ln.comment:
                break
            cont = ln.text[ln.indent:]
            if _looks_like_structure(cont):
                break
            piece, cend = _scan_plain_block(ln.text, ln.indent)
            if blanks:
                parts.append("\n" * blanks + piece)
            else:
                parts.append(" " + piece)
            comment_line = j
            comment_ci = cend
            self.li = j + 1
            if cend < len(ln.text) and ln.text[cend:].lstrip().startswith("#"):
                break
        value = _fold_plain(parts)
        node.value = value
        node.tag = resolve_plain(value)
        self._finish_line(comment_line, comment_ci, node)
        return node

    def _parse_double_quoted(self, li: int, ci: int) -> Node:
        text = self.lines[li].text
        node = Node(Kind.SCALAR, tag="!!str", style=Style.DOUBLE_QUOTED)
        chunks: list[str] = []
        i = ci + 1
        cur_li = li
        pending_newlines = 0
        first_segment = True
        while True:
            if cur_li >= len(self.lines):
                raise self._error("unterminated double-quoted string", li, ci)
            text = self.lines[cur_li].text
            n = len(text)
            segment: list[str] = []
            escaped_newline = False
            closed = False
            while i < n:
                c = text[i]
                if c == "\\":
                    if i + 1 >= n:
                        escaped_newline = True
                        i += 1
                        break
                    nxt = text[i + 1]
                    esc, consumed = _decode_escape(text, i, self, cur_li)
                    segment.append(esc)
                    i += consumed
                    continue
                if c == '"':
                    closed = True
                    i += 1
                    break
                segment.append(c)
                i += 1
            seg = "".join(segment)
            if not first_segment:
                seg = seg.lstrip(" \t")
            if closed:
                seg_text = seg if first_segment else seg
                if not first_segment and not escaped_newline:
                    pass
                chunks.append(("\n" * pending_newlines if pending_newlines else (" " if not first_segment and not chunks_end_escaped(chunks) else "")) + seg)
                break
            # line continues
            seg = seg.rstrip(" \t") if not escaped_newline else seg
            if first_segment:
                chunks.append(seg)
            else:
                chunks.append(("\n" * pending_newlines if pending_newlines else (" " if not chunks_end_escaped(chunks) else "")) + seg)
            if escaped_newline:
                chunks.append(_ESCAPED_NEWLINE)  # marker: no folding space
            first_segment = False
            cur_li += 1
            pending_newlines = 0
            while cur_li < len(self.lines) and self.lines[cur_li].blank:
                pending_newlines += 1
                cur_li += 1
            if cur_li >= len(self.lines):
                raise self._error("unterminated double-quoted string", li, ci)
            i = 0
            while i < len(self.lines[cur_li].text) and self.lines[cur_li].text[i] in " \t":
                i += 1
        node.value = "".join(chunks).replace(_ESCAPED_NEWLINE, "")
        self._finish_line(cur_li, i, node)
        return node

    def _parse_single_quoted(self, li: int, ci: int) -> Node:
        node = Node(Kind.SCALAR, tag="!!str", style=Style.SINGLE_QUOTED)
        chunks: list[str] = []
        i = ci + 1
        cur_li = li
        pending_newlines = 0
        first_segment = True
        while True:
            if cur_li >= len(self.lines):
                raise self._error("unterminated single-quoted string", li, ci)
            text = self.lines[cur_li].text
            n = len(text)
            segment: list[str] = []
            closed = False
            while i < n:
                c = text[i]
                if c == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        segment.append("'")
                        i += 2
                        continue
                    closed = True
                    i += 1
                    break
                segment.append(c)
                i += 1
            seg = "".join(segment)
            if not first_segment:
                seg = seg.lstrip(" \t")
            if closed:
                chunks.append(("\n" * pending_newlines if pending_newlines else (" " if not first_segment else "")) + seg)
                break
            seg = seg.rstrip(" \t")
            if first_segment:
                chunks.append(seg)
            else:
                chunks.append(("\n" * pending_newlines if pending_newlines else " ") + seg)
            first_segment = False
            cur_li += 1
            pending_newlines = 0
            while cur_li < len(self.lines) and self.lines[cur_li].blank:
                pending_newlines += 1
                cur_li += 1
            i = 0
            if cur_li < len(self.lines):
                while i < len(self.lines[cur_li].text) and self.lines[cur_li].text[i] in " \t":
                    i += 1
        node.value = "".join(chunks)
        self._finish_line(cur_li, i, node)
        return node

    def _parse_block_scalar(self, li: int, ci: int, block_indent: int) -> Node:
        text = self.lines[li].text
        literal = text[ci] == "|"
        j = ci + 1
        chomp = ""
        explicit = 0
        while j < len(text) and text[j] in "+-0123456789":
            c = text[j]
            if c in "+-":
                if chomp:
                    raise self._error("repeated chomping indicator", li, j)
                chomp = c
            else:
                if explicit:
                    raise self._error("repeated indentation indicator", li, j)
                explicit = int(c)
                if explicit == 0:
                    raise self._error("indentation indicator cannot be 0", li, j)
            j += 1
        node = Node(Kind.SCALAR, tag="!!str", style=Style.LITERAL if literal else Style.FOLDED)
        rest = text[j:].strip()
        if rest.startswith("#"):
            node.line_comment = rest
        elif rest:
            raise self._error("unexpected characters after block scalar indicator", li, j)
        # determine content indent
        base = max(block_indent, -1)
        content_indent: int | None = None
        if explicit:
            content_indent = (base if base >= 0 else 0) + explicit
        k = li + 1
        raw_lines: list[str] = []
        while k < len(self.lines):
            ln = self.lines[k]
            if content_indent is None:
                if ln.blank:
                    raw_lines.append("")
                    k += 1
                    continue
                if ln.indent <= base:
                    break
                content_indent = ln.indent
                for idx, prev in enumerate(raw_lines):
                    if len(prev) > content_indent:
                        raise self._error("leading all-space line must not have more spaces than the first content line", li + 1 + idx)
                # blank lines before the first content line may contain spaces beyond the indent
            if ln.blank:
                raw_lines.append(ln.text[content_indent:] if len(ln.text) > content_indent else "")
                k += 1
                continue
            if ln.indent < content_indent:
                break
            if self._is_doc_marker(k) and content_indent == 0:
                break
            raw_lines.append(ln.text[content_indent:])
            k += 1
        # trailing blank lines: belong to the scalar for chomping purposes
        self.li = k
        # strip trailing blank lines but remember them
        trailing = 0
        while raw_lines and raw_lines[-1].strip(" \t") == "" and (raw_lines[-1] == "" or True):
            if raw_lines[-1] != "":
                # whitespace-only line at/after indent counts as an empty line
                pass
            raw_lines.pop()
            trailing += 1
        if literal:
            body = "\n".join(raw_lines)
        else:
            body = _fold_block(raw_lines)
        if raw_lines:
            if chomp == "-":
                value = body
            elif chomp == "+":
                value = body + "\n" * (trailing + 1)
            else:
                value = body + "\n"
        else:
            value = "\n" * trailing if chomp == "+" else ""
        node.value = value
        # give trailing blank lines back to the caller when they were not chomped
        if chomp != "+" and trailing:
            self.li = k - trailing
        return node

    # ------------------------------------------------------------------ flow

    def _parse_flow(self, li: int, ci: int) -> Node:
        node, li2, ci2 = self._parse_flow_node(li, ci, self.max_depth)
        self._finish_line(li2, ci2, node)
        return node

    def _flow_skip(self, li: int, ci: int, comment_sink: Node | None) -> tuple[int, int]:
        """Skip whitespace, newlines and comments inside a flow collection."""
        while True:
            if li >= len(self.lines):
                raise self._error("unterminated flow collection", li - 1)
            text = self.lines[li].text
            while ci < len(text) and text[ci] in " \t":
                ci += 1
            if ci < len(text) and text[ci] == "#":
                if comment_sink is not None and not comment_sink.line_comment:
                    comment_sink.line_comment = text[ci:].strip()
                ci = len(text)
            if ci >= len(text):
                li += 1
                ci = 0
                continue
            return li, ci

    def _parse_flow_node(self, li: int, ci: int, depth: int) -> tuple[Node, int, int]:
        if depth <= 0:
            raise self._error("flow collection nesting too deep", li, ci)
        text = self.lines[li].text
        anchor, tag, ci = self._parse_properties(text, ci)
        if ci >= len(text) or text[ci] in " \t":
            li, ci = self._flow_skip(li, ci, None)
            text = self.lines[li].text
        ch = text[ci]
        if ch == "[":
            node, li, ci = self._parse_flow_sequence(li, ci, depth)
        elif ch == "{":
            node, li, ci = self._parse_flow_mapping(li, ci, depth)
        elif ch == '"':
            node, li, ci = self._parse_flow_quoted(li, ci, double=True)
        elif ch == "'":
            node, li, ci = self._parse_flow_quoted(li, ci, double=False)
        elif ch == "*":
            end = ci + 1
            while end < len(text) and text[end] not in _ANCHOR_END and text[end] != ":":
                end += 1
            node = self._make_alias(text[ci + 1:end], li, ci)
            ci = end
        else:
            node, li, ci = self._parse_flow_plain(li, ci)
        node.line = li + 1 + self.line_offset
        node.column = ci + 1
        self._apply_properties(node, anchor, tag)
        return node, li, ci

    def _parse_flow_sequence(self, li: int, ci: int, depth: int) -> tuple[Node, int, int]:
        node = Node.sequence(style=Style.FLOW)
        node.line = li + 1 + self.line_offset
        node.column = ci + 1
        ci += 1
        while True:
            li, ci = self._flow_skip(li, ci, node)
            text = self.lines[li].text
            if text[ci] == "]":
                return node, li, ci + 1
            if text[ci] == ",":
                raise self._error("unexpected ',' in flow sequence", li, ci)
            if text[ci] == "?" and (ci + 1 >= len(text) or text[ci + 1] in " \t"):
                li, ci = self._flow_skip(li, ci + 1, node)
            item, li, ci = self._parse_flow_node(li, ci, depth - 1)
            li, ci = self._flow_skip(li, ci, node)
            text = self.lines[li].text
            if text[ci] == ":" and (ci + 1 >= len(text) or text[ci + 1] in " \t,]}"):
                # single-pair mapping inside a sequence
                li, ci = self._flow_skip(li, ci + 1, node)
                text = self.lines[li].text
                if text[ci] in ",]":
                    value: Node = Node.null(value="")
                else:
                    value, li, ci = self._parse_flow_node(li, ci, depth - 1)
                pair = Node.mapping(style=Style.FLOW)
                self._append_pair(pair, item, value)
                item = pair
                li, ci = self._flow_skip(li, ci, node)
                text = self.lines[li].text
            self._append_item(node, item)
            if text[ci] == ",":
                ci += 1
                continue
            if text[ci] == "]":
                return node, li, ci + 1
            raise self._error("expected ',' or ']' in flow sequence", li, ci)

    def _parse_flow_mapping(self, li: int, ci: int, depth: int) -> tuple[Node, int, int]:
        node = Node.mapping(style=Style.FLOW)
        node.line = li + 1 + self.line_offset
        node.column = ci + 1
        ci += 1
        while True:
            li, ci = self._flow_skip(li, ci, node)
            text = self.lines[li].text
            if text[ci] == "}":
                return node, li, ci + 1
            if text[ci] == ",":
                raise self._error("unexpected ',' in flow mapping", li, ci)
            if text[ci] == "?" and (ci + 1 >= len(text) or text[ci + 1] in " \t"):
                li, ci = self._flow_skip(li, ci + 1, node)
                text = self.lines[li].text
            if text[ci] == ":" and (ci + 1 >= len(text) or text[ci + 1] in " \t,}"):
                key: Node = Node.null(value="")
            else:
                key, li, ci = self._parse_flow_node(li, ci, depth - 1)
            li, ci = self._flow_skip(li, ci, node)
            text = self.lines[li].text
            # JSON-like keys ("key":value) allow an adjacent value without a space
            adjacent_ok = bool(key.style & (Style.DOUBLE_QUOTED | Style.SINGLE_QUOTED))
            if text[ci] == ":" and (adjacent_ok or ci + 1 >= len(text) or text[ci + 1] in " \t,}[]{"):
                li, ci = self._flow_skip(li, ci + 1, node)
                text = self.lines[li].text
                if text[ci] in ",}":
                    value: Node = Node.null(value="")
                else:
                    value, li, ci = self._parse_flow_node(li, ci, depth - 1)
                li, ci = self._flow_skip(li, ci, node)
                text = self.lines[li].text
            else:
                value = Node.null(value="")
            self._append_pair(node, key, value)
            if text[ci] == ",":
                ci += 1
                continue
            if text[ci] == "}":
                return node, li, ci + 1
            raise self._error("expected ',' or '}' in flow mapping", li, ci)

    def _append_pair(self, mapping: Node, key: Node, value: Node) -> None:
        if key.kind is Kind.SCALAR and key.tag == "!!str" and key.value == "<<" \
                and key.style is Style.NONE:
            key.tag = "!!merge"
        key.parent = mapping
        key.is_map_key = True
        value.parent = mapping
        value.key = key
        mapping.content.append(key)
        mapping.content.append(value)

    def _append_item(self, sequence: Node, item: Node) -> None:
        key_node = Node.integer(len(sequence.content))
        key_node.parent = sequence
        key_node.is_map_key = True
        item.parent = sequence
        item.key = key_node
        sequence.content.append(item)

    def _parse_flow_quoted(self, li: int, ci: int, *, double: bool) -> tuple[Node, int, int]:
        # reuse the block quoted parsers but stop before _finish_line
        saved = self.li
        if double:
            node = self._parse_double_quoted_raw(li, ci)
        else:
            node = self._parse_single_quoted_raw(li, ci)
        li2, ci2 = self._quoted_end
        self.li = saved
        return node, li2, ci2

    def _parse_double_quoted_raw(self, li: int, ci: int) -> Node:
        original_finish = self._finish_line
        end: list[tuple[int, int]] = []

        def capture(l: int, c: int, node: Node) -> None:
            end.append((l, c))

        self._finish_line = capture  # type: ignore[method-assign]
        try:
            node = self._parse_double_quoted(li, ci)
        finally:
            self._finish_line = original_finish  # type: ignore[method-assign]
        self._quoted_end = end[0]
        return node

    def _parse_single_quoted_raw(self, li: int, ci: int) -> Node:
        original_finish = self._finish_line
        end: list[tuple[int, int]] = []

        def capture(l: int, c: int, node: Node) -> None:
            end.append((l, c))

        self._finish_line = capture  # type: ignore[method-assign]
        try:
            node = self._parse_single_quoted(li, ci)
        finally:
            self._finish_line = original_finish  # type: ignore[method-assign]
        self._quoted_end = end[0]
        return node

    def _parse_flow_plain(self, li: int, ci: int) -> tuple[Node, int, int]:
        parts: list[str] = []
        cur_li = li
        i = ci
        pending_newlines = 0
        while True:
            if cur_li >= len(self.lines):
                raise self._error("unterminated flow collection", li, ci)
            text = self.lines[cur_li].text
            n = len(text)
            start = i
            while i < n:
                c = text[i]
                if c in _FLOW_END:
                    break
                if c == ":" and (i + 1 >= n or text[i + 1] in " \t,]}[{"):
                    break
                if c == "#" and (i == start or text[i - 1] in " \t"):
                    break
                i += 1
            piece = text[start:i].strip(" \t")
            if piece:
                if parts:
                    parts.append(("\n" * pending_newlines) if pending_newlines else " ")
                parts.append(piece)
            if i < n and text[i] != "#":
                break
            # continue on next line
            if i < n and text[i] == "#":
                i = n
            cur_li += 1
            pending_newlines = 0
            while cur_li < len(self.lines) and self.lines[cur_li].blank:
                pending_newlines += 1
                cur_li += 1
            if cur_li >= len(self.lines):
                raise self._error("unterminated flow collection", li, ci)
            i = 0
            t = self.lines[cur_li].text
            while i < len(t) and t[i] in " \t":
                i += 1
        value = "".join(parts)
        node = Node(Kind.SCALAR, value=value, tag=resolve_plain(value))
        if value == "<<":
            node.tag = "!!merge"
        return node, cur_li, i


# ---------------------------------------------------------------------- helpers

_ESCAPED_NEWLINE = "\x1e<yaqpy-escaped-newline>\x1e"


def chunks_end_escaped(chunks: list[str]) -> bool:
    return bool(chunks) and chunks[-1] == _ESCAPED_NEWLINE


def _join_comments(parts: list[str]) -> str:
    return "\n".join(p for p in parts if p)


def _resolve_key_tag(text: str) -> str:
    if text == "<<":
        return "!!merge"
    return resolve_plain(text)


def _scan_plain_block(text: str, ci: int) -> tuple[str, int]:
    """Scan a plain scalar on one line starting at ci. Returns (text, end_index)."""
    n = len(text)
    i = ci
    while i < n:
        c = text[i]
        if c == "#" and i > ci and text[i - 1] in " \t":
            break
        if c == ":" and (i + 1 >= n or text[i + 1] in " \t"):
            break
        i += 1
    piece = text[ci:i].rstrip(" \t")
    end = ci + len(piece)
    return piece, end


def _looks_like_structure(cont: str) -> bool:
    if cont.startswith("- ") or cont == "-" or cont.startswith("? ") or cont == "?":
        return True
    if cont.startswith("#"):
        return True
    # key: value on a continuation line ends the scalar (it is really a syntax error)
    i = 0
    n = len(cont)
    while i < n:
        c = cont[i]
        if c == ":" and (i + 1 >= n or cont[i + 1] in " \t"):
            return True
        if c == "#" and i > 0 and cont[i - 1] in " \t":
            break
        i += 1
    return False


def _fold_plain(parts: list[str]) -> str:
    """Join plain scalar pieces: single line breaks fold to a space, blank lines to newlines."""
    out = parts[0]
    for part in parts[1:]:
        if part.startswith("\n"):
            out += part
        else:
            out += part
    return out


def _fold_block(lines: list[str]) -> str:
    """Fold a ``>`` block scalar body (without trailing newline handling)."""
    out: list[str] = []
    prev_more_indented = False
    prev_blank = True
    for idx, line in enumerate(lines):
        more_indented = line.startswith((" ", "\t")) and line.strip() != ""
        if line == "":
            out.append("\n")
            prev_blank = True
            prev_more_indented = False if not more_indented else prev_more_indented
            continue
        if idx == 0 or prev_blank:
            out.append(line)
        elif more_indented or prev_more_indented:
            out.append("\n" + line)
        else:
            out.append(" " + line)
        prev_blank = False
        prev_more_indented = more_indented
    text = "".join(out)
    # blank lines: the first "\n" after text is the fold; extra blank lines add newlines
    return _normalise_folded(lines)


def _normalise_folded(lines: list[str]) -> str:
    result: list[str] = []
    i = 0
    n = len(lines)
    prev_more = False
    while i < n:
        line = lines[i]
        if line == "":
            # count blank run
            j = i
            while j < n and lines[j] == "":
                j += 1
            blanks = j - i
            if result:
                nxt_more = j < n and lines[j].startswith((" ", "\t"))
                if prev_more or nxt_more:
                    result.append("\n" * (blanks + 1))
                else:
                    result.append("\n" * blanks)
            i = j
            continue
        more = line.startswith((" ", "\t"))
        if result and not result[-1].endswith("\n"):
            if more or prev_more:
                result.append("\n")
            else:
                result.append(" ")
        result.append(line)
        prev_more = more
        i += 1
    return "".join(result)


_SIMPLE_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f",
    "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85",
    "_": "\xa0", "L": " ", "P": " ",
}


def _decode_escape(text: str, i: int, parser: YamlParser, li: int) -> tuple[str, int]:
    nxt = text[i + 1]
    if nxt in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[nxt], 2
    width = {"x": 2, "u": 4, "U": 8}.get(nxt)
    if width is None:
        raise parser._error(f"invalid escape sequence \\{nxt}", li, i)
    digits = text[i + 2:i + 2 + width]
    if len(digits) != width:
        raise parser._error("truncated escape sequence", li, i)
    try:
        return chr(int(digits, 16)), 2 + width
    except ValueError:
        raise parser._error("invalid escape sequence", li, i) from None


def _unquote_double(raw: str, parser: YamlParser, ci: int) -> str:
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\" and i + 1 < n:
            esc, consumed = _decode_escape(raw, i, parser, parser.li)
            out.append(esc)
            i += consumed
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_documents(text: str, *, filename: str = "", line_offset: int = 0,
                    max_depth: int = 1000, anchors: dict[str, Node] | None = None,
                    budget: DecodeBudget | None = None) -> list[Node]:
    parser = YamlParser(text, filename=filename, line_offset=line_offset, max_depth=max_depth,
                        anchors=anchors, budget=budget)
    try:
        return parser.parse_stream()
    except RecursionError:
        raise YamlSyntaxError("document nesting too deep", filename=filename) from None
