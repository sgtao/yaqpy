"""The Node data model (design doc section 5) - Go's ``CandidateNode``."""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from typing import Any

from yaqpy.core.model import tags as _tags
from yaqpy.errors import EvaluationError


class Kind(enum.Enum):
    MAPPING = "map"
    SEQUENCE = "seq"
    SCALAR = "scalar"
    ALIAS = "alias"


class Style(enum.Flag):
    NONE = 0
    TAGGED = enum.auto()
    DOUBLE_QUOTED = enum.auto()
    SINGLE_QUOTED = enum.auto()
    LITERAL = enum.auto()
    FOLDED = enum.auto()
    FLOW = enum.auto()


STYLE_NAMES: dict[Style, str] = {
    Style.NONE: "",
    Style.TAGGED: "tagged",
    Style.DOUBLE_QUOTED: "double",
    Style.SINGLE_QUOTED: "single",
    Style.LITERAL: "literal",
    Style.FOLDED: "folded",
    Style.FLOW: "flow",
}
STYLE_BY_NAME: dict[str, Style] = {v: k for k, v in STYLE_NAMES.items()}


def parse_style(name: str) -> Style:
    try:
        return STYLE_BY_NAME[name]
    except KeyError:
        raise EvaluationError(f"unknown style {name}") from None


def style_name(style: Style) -> str:
    return STYLE_NAMES.get(style, "<unknown>")


class Node:
    """A mutable tree node. Mappings keep ``content`` as ``[k0, v0, k1, v1, ...]``."""

    __slots__ = (
        "kind", "style", "tag", "value", "anchor", "alias", "content",
        "head_comment", "line_comment", "foot_comment",
        "parent", "key", "leading_content",
        "document_index", "filename", "file_index",
        "line", "column", "evaluate_together", "is_map_key", "encode_hint",
    )

    def __init__(
        self,
        kind: Kind = Kind.SCALAR,
        *,
        tag: str = "",
        value: str = "",
        style: Style = Style.NONE,
        anchor: str = "",
        alias: Node | None = None,
        content: list[Node] | None = None,
        head_comment: str = "",
        line_comment: str = "",
        foot_comment: str = "",
        parent: Node | None = None,
        key: Node | None = None,
        leading_content: str = "",
        document_index: int = 0,
        filename: str = "",
        file_index: int = 0,
        line: int = 0,
        column: int = 0,
        evaluate_together: bool = False,
        is_map_key: bool = False,
        encode_hint: str = "",
    ) -> None:
        self.kind = kind
        self.style = style
        self.tag = tag
        self.value = value
        self.anchor = anchor
        self.alias = alias
        self.content: list[Node] = content if content is not None else []
        self.head_comment = head_comment
        self.line_comment = line_comment
        self.foot_comment = foot_comment
        self.parent = parent
        self.key = key
        self.leading_content = leading_content
        self.document_index = document_index
        self.filename = filename
        self.file_index = file_index
        self.line = line
        self.column = column
        self.evaluate_together = evaluate_together
        self.is_map_key = is_map_key
        # how a format-specific encoder should write a mapping (TOML): "", "inline" or "block"
        self.encode_hint = encode_hint

    # ------------------------------------------------------------------ factories
    @classmethod
    def scalar(cls, value: str, tag: str = "!!str", **kw: Any) -> Node:
        return cls(Kind.SCALAR, tag=tag, value=value, **kw)

    @classmethod
    def string(cls, value: str, **kw: Any) -> Node:
        tag = "!!merge" if value == "<<" else "!!str"
        return cls(Kind.SCALAR, tag=tag, value=value, **kw)

    @classmethod
    def null(cls, value: str = "null", **kw: Any) -> Node:
        return cls(Kind.SCALAR, tag="!!null", value=value, **kw)

    @classmethod
    def boolean(cls, flag: bool, **kw: Any) -> Node:
        return cls(Kind.SCALAR, tag="!!bool", value="true" if flag else "false", **kw)

    @classmethod
    def integer(cls, number: int, **kw: Any) -> Node:
        return cls(Kind.SCALAR, tag="!!int", value=str(number), **kw)

    @classmethod
    def mapping(cls, **kw: Any) -> Node:
        return cls(Kind.MAPPING, tag="!!map", **kw)

    @classmethod
    def sequence(cls, **kw: Any) -> Node:
        return cls(Kind.SEQUENCE, tag="!!seq", **kw)

    @classmethod
    def from_value(cls, value: Any, text: str) -> Node:
        """Go's ``createScalarNode``: tag from the Python type, text as given."""
        if value is None:
            tag = "!!null"
        elif isinstance(value, bool):
            tag = "!!bool"
        elif isinstance(value, int):
            tag = "!!int"
        elif isinstance(value, float):
            tag = "!!float"
        else:
            tag = "!!str"
        return cls(Kind.SCALAR, tag=tag, value=text)

    # ------------------------------------------------------------------ identity
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        tag = "alias" if self.kind is Kind.ALIAS else self.tag
        value = self.value if self.value != "" else f"{len(self.content)} kids"
        return f"D{self.document()}, P{self.nice_path()}, {self.kind.name} ({tag})::{value}"

    def create_child(self) -> Node:
        return Node(parent=self)

    def document(self) -> int:
        node = self
        while node.parent is not None:
            node = node.parent
        return node.document_index

    def get_filename(self) -> str:
        node = self
        while node.parent is not None:
            node = node.parent
        return node.filename

    def get_file_index(self) -> int:
        node = self
        while node.parent is not None:
            node = node.parent
        return node.file_index

    def identity_key(self) -> str:
        """Go's ``GetKey``: used to de-duplicate traversal matches."""
        prefix = f"key-{self.value}-" if self.is_map_key else ""
        key = self.key.value if self.key is not None else ""
        return f"{prefix}{self.document()} - {key}"

    def parsed_key(self) -> str | int | None:
        if self.is_map_key:
            return self.value
        if self.key is None:
            return None
        if self.key.tag == "!!str":
            return self.key.value
        try:
            return _tags.parse_int(self.key.value)[1]
        except ValueError:
            return self.key.value

    def path(self) -> list[str | int]:
        key = self.parsed_key()
        if self.parent is not None and key is not None:
            return [*self.parent.path(), key]
        if key is not None:
            return [key]
        return []

    def nice_path(self) -> str:
        out: list[str] = []
        for i, element in enumerate(self.path()):
            text = str(element)
            if isinstance(element, int):
                out.append(f"[{text}]")
            elif i == 0:
                out.append(text)
            elif "." in text:
                out.append(f"[{text}]")
            else:
                out.append(f".{text}")
        return "".join(out)

    # ------------------------------------------------------------------ children
    def add_key_value(self, raw_key: Node, raw_value: Node) -> tuple[Node, Node]:
        key = raw_key.copy()
        key.parent = self
        key.is_map_key = True
        value = raw_value.copy()
        value.parent = self
        value.is_map_key = False
        value.key = key
        self.content.append(key)
        self.content.append(value)
        return key, value

    def add_child(self, raw_child: Node) -> Node:
        value = raw_child.copy()
        value.parent = self
        value.is_map_key = False
        index = len(self.content)
        key_node = Node.integer(index)
        key_node.parent = self
        value.key = key_node
        self.content.append(value)
        return value

    def add_children(self, children: Iterable[Node]) -> None:
        if self.kind is Kind.MAPPING:
            items = list(children)
            for i in range(0, len(items) - 1, 2):
                self.add_key_value(items[i], items[i + 1])
        else:
            for child in children:
                self.add_child(child)

    def get_map_value(self, key: str) -> Node | None:
        content = self.content
        for i in range(0, len(content) - 1, 2):
            if content[i].value == key:
                return content[i + 1]
        return None

    def map_items(self) -> Iterator[tuple[Node, Node]]:
        content = self.content
        for i in range(0, len(content) - 1, 2):
            yield content[i], content[i + 1]

    def values(self) -> list[Node]:
        if self.kind is Kind.MAPPING:
            return [self.content[i] for i in range(1, len(self.content), 2)]
        if self.kind is Kind.SEQUENCE:
            return list(self.content)
        return []

    def can_visit_values(self) -> bool:
        return self.kind in (Kind.MAPPING, Kind.SEQUENCE)

    # ------------------------------------------------------------------ copying
    def copy(self, deep: bool = True) -> Node:
        clone = Node(
            self.kind,
            style=self.style,
            tag=self.tag,
            value=self.value,
            anchor=self.anchor,
            alias=self.alias,
            head_comment=self.head_comment,
            line_comment=self.line_comment,
            foot_comment=self.foot_comment,
            parent=self.parent,
            key=self.key.copy() if self.key is not None else None,
            leading_content=self.leading_content,
            document_index=self.document_index,
            filename=self.filename,
            file_index=self.file_index,
            line=self.line,
            column=self.column,
            evaluate_together=self.evaluate_together,
            is_map_key=self.is_map_key,
            encode_hint=self.encode_hint,
        )
        if deep:
            clone.add_children(self.content)
        return clone

    def copy_without_content(self) -> Node:
        return self.copy(deep=False)

    def create_replacement(self, kind: Kind, tag: str, value: str) -> Node:
        node = Node(kind, tag=tag, value=value)
        return self.copy_as_replacement(node)

    def copy_as_replacement(self, replacement: Node) -> Node:
        new = replacement.copy()
        new.parent = self.parent
        new.key = self if self.is_map_key else self.key
        return new

    def create_replacement_with_comments(self, kind: Kind, tag: str, style: Style) -> Node:
        replacement = self.create_replacement(kind, tag, "")
        replacement.leading_content = self.leading_content
        replacement.head_comment = self.head_comment
        replacement.line_comment = self.line_comment
        replacement.foot_comment = self.foot_comment
        replacement.style = style
        return replacement

    # ------------------------------------------------------------------ assignment
    def guess_tag(self) -> str:
        return _tags.guess_tag(self.tag, self.value)

    def update_from(self, other: Node, *, dont_overwrite_anchor: bool = False,
                    clobber_custom_tags: bool = False) -> None:
        """Go's ``UpdateFrom``: the body of ``=`` / ``|=``."""
        if self is other:
            return
        if (self.kind is not Kind.SCALAR and not self.content) or (
            self.guess_tag() != other.guess_tag()
        ):
            self.style = other.style
        self.content = []
        self.kind = other.kind
        self.add_children(other.content)
        self.value = other.value
        self.update_attributes_from(
            other, dont_overwrite_anchor=dont_overwrite_anchor,
            clobber_custom_tags=clobber_custom_tags,
        )

    def update_attributes_from(self, other: Node, *, dont_overwrite_anchor: bool = False,
                               clobber_custom_tags: bool = False) -> None:
        if self.kind is not other.kind:
            self.content = []
            self.value = ""
        self.kind = other.kind
        if clobber_custom_tags or self.tag.startswith("!!") or self.tag == "":
            self.tag = other.tag
        self.alias = other.alias
        if not dont_overwrite_anchor:
            self.anchor = other.anchor
        if self.style is Style.NONE:
            self.style = other.style
        if other.encode_hint:
            self.encode_hint = other.encode_hint
        if other.foot_comment != "":
            self.foot_comment = other.foot_comment
        if other.head_comment != "":
            self.head_comment = other.head_comment
        if other.line_comment != "":
            self.line_comment = other.line_comment

    # ------------------------------------------------------------------ predicates
    def is_null(self) -> bool:
        return self.tag == "!!null"

    def is_truthy(self) -> bool:
        if self.tag == "!!null":
            return False
        if self.kind is Kind.SCALAR and self.tag == "!!bool":
            return self.value.lower() in ("y", "yes", "on", "true")
        return True

    def resolve_alias(self) -> Node:
        node = self
        visited: set[int] = set()
        while node.kind is Kind.ALIAS:
            if id(node) in visited:
                raise EvaluationError("alias cycle detected")
            visited.add(id(node))
            if node.alias is None:
                raise EvaluationError(f"alias '{node.value}' has no target")
            node = node.alias
        return node

    def value_rep(self) -> Any:
        """Go's ``GetValueRep``: the scalar as a Python value."""
        tag = self.guess_tag()
        if tag == "!!int":
            return _tags.parse_int(self.value)[1]
        if tag == "!!float":
            return _tags.parse_float(self.value)
        if tag == "!!bool":
            return self.is_truthy()
        if tag == "!!null":
            return None
        return self.value

    # ------------------------------------------------------------------ equality
    def deep_equal(self, other: Node) -> bool:
        if self.kind is not other.kind:
            return False
        if self.kind is Kind.SCALAR:
            if self.guess_tag() != other.guess_tag():
                return False
        if self.tag == "!!null":
            return True
        if self.kind is Kind.SCALAR:
            return self.value == other.value
        if self.kind is Kind.SEQUENCE:
            if len(self.content) != len(other.content):
                return False
            return all(a.deep_equal(b) for a, b in zip(self.content, other.content))
        if self.kind is Kind.MAPPING:
            if len(self.content) != len(other.content):
                return False
            for key, value in self.map_items():
                idx = other.find_key_index(key)
                if idx < 0 or not value.deep_equal(other.content[idx + 1]):
                    return False
            return True
        return False

    def find_key_index(self, item: Node) -> int:
        for i in range(0, len(self.content) - 1, 2):
            if self.content[i].deep_equal(item):
                return i
        return -1

    def find_in_array(self, item: Node) -> int:
        for i, child in enumerate(self.content):
            if child.deep_equal(item):
                return i
        return -1
