"""XML tokenizer with the behaviour of Go's ``encoding/xml`` decoder (used by yq).

Why not ``xml.parsers.expat``: yq's XML input is not a validating parse. Go's decoder (in the
default, non-strict mode with ``RawToken``) keeps a ``<!DOCTYPE ...>`` declaration as raw text,
does **not** expand entities that the document declares itself (``&writer;`` stays text and is
escaped again on output), tolerates unmatched end tags and returns namespace prefixes untouched.
Round-tripping the documents of the Go test-suite needs exactly that, and expat cannot give it.

The lexer below therefore never expands anything except the five predefined entities and numeric
character references. Because no entity is ever defined or fetched, there is no external-entity
access and no entity-expansion blow-up ("billion laughs"); the only limits needed are the input
size and the nesting depth, which the decoder checks.

The token types mirror Go's (``StartElement`` ...) so the decoder can follow ``decoder_xml.go``.
Names are ``(space, local)`` pairs: ``space`` is the raw prefix (``RawToken``) or, after namespace
translation, the namespace URL.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from yaqpy.errors import FormatError

_XML_URL = "http://www.w3.org/XML/1998/namespace"

Name = tuple[str, str]      # (space, local)


@dataclass(slots=True)
class StartElement:
    name: Name
    attrs: list[tuple[Name, str]] = field(default_factory=list)


@dataclass(slots=True)
class EndElement:
    name: Name


@dataclass(slots=True)
class CharData:
    text: str


@dataclass(slots=True)
class Comment:
    text: str


@dataclass(slots=True)
class ProcInst:
    target: str
    inst: str


@dataclass(slots=True)
class Directive:
    text: str


Token = StartElement | EndElement | CharData | Comment | ProcInst | Directive

_NAME_CHARS = re.compile(r"[A-Za-z0-9_:.\--\U0010FFFF]*")
_UNQUOTED_ATTR = re.compile(r"[A-Za-z0-9_:\-]*")
_SPACE = re.compile(r"[ \t\r\n]*")
_ENTITY = re.compile(r"&(?:#(?:x([0-9a-fA-F]+)|([0-9]+))|([A-Za-z_:-\U0010FFFF][A-Za-z0-9_:.\--\U0010FFFF]*));")
_ILLEGAL_CHAR = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")
_NEWLINES = re.compile(r"\r\n?")
_ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "apos": "'", "quot": '"'}


def is_name(text: str) -> bool:
    """Go's ``isName``: a non-empty name whose first character may start a name."""
    if not text:
        return False
    first = text[0]
    if not (first.isalpha() or first in "_:"):
        return False
    return _NAME_CHARS.fullmatch(text) is not None


def is_valid_directive(text: str) -> bool:
    """Go's ``isValidDirective``: balanced ``<``/``>``, closed quotes and comments."""
    depth = 0
    quote = ""
    in_comment = False
    n = len(text)
    for i, c in enumerate(text):
        if in_comment:
            if c == ">" and i >= 2 and text[i - 2:i + 1] == "-->":
                in_comment = False
        elif quote:
            if c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "<":
            if i + 4 < n and text[i:i + 4] == "<!--":
                in_comment = True
            else:
                depth += 1
        elif c == ">":
            if depth == 0:
                return False
            depth -= 1
    return depth == 0 and not quote and not in_comment


def _split_name(text: str) -> Name:
    """Go's ``nsname``: ``prefix:local`` when there is exactly one colon between two names."""
    if text.count(":") == 1:
        space, local = text.split(":")
        if space and local:
            return space, local
    return "", text


class Lexer:
    """Go's ``Decoder.rawToken`` for ``Strict = false`` (``strict`` switches to the strict rules)."""

    def __init__(self, text: str, *, strict: bool = False) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.strict = strict
        self._to_close: Name | None = None

    # ------------------------------------------------------------------ errors

    def error(self, message: str) -> FormatError:
        line = self.s.count("\n", 0, min(self.i, self.n)) + 1
        return FormatError(f"XML syntax error on line {line}: {message}", format="xml", line=line)

    def eof(self) -> FormatError:
        return self.error("unexpected EOF")

    # ------------------------------------------------------------------ helpers

    def _space(self) -> None:
        self.i = _SPACE.match(self.s, self.i).end()  # type: ignore[union-attr]

    def _read_name(self) -> str | None:
        m = _NAME_CHARS.match(self.s, self.i)
        end = m.end() if m else self.i  # type: ignore[union-attr]
        if end == self.i:
            return None
        name = self.s[self.i:end]
        self.i = end
        if not is_name(name):
            raise self.error(f"invalid XML name: {name}")
        return name

    def _text(self, raw: str, *, cdata: bool = False) -> str:
        """Newline normalisation, entity decoding and the character-range check."""
        text = _NEWLINES.sub("\n", raw) if "\r" in raw else raw
        if not raw.strip(" \t\r\n"):
            return text                          # only blanks: nothing to decode or check
        if not cdata and "&" in text:
            text = self._decode_entities(text)
        bad = _ILLEGAL_CHAR.search(text)
        if bad:
            raise self.error(f"illegal character code U+{ord(bad.group()):04X}")
        return text

    def _decode_entities(self, text: str) -> str:
        def replace(m: re.Match[str]) -> str:
            hex_digits, decimal, name = m.group(1), m.group(2), m.group(3)
            if name is not None:
                if name in _ENTITIES:
                    return _ENTITIES[name]
            else:
                number = int(hex_digits, 16) if hex_digits is not None else int(decimal)
                if number <= 0x10FFFF:
                    return chr(number)
            if self.strict:
                raise self.error(f"invalid character entity {m.group(0)}")
            return m.group(0)                # declared or unknown entities stay text

        if self.strict:
            for m in re.finditer("&", text):
                if _ENTITY.match(text, m.start()) is None:
                    raise self.error("invalid character entity & (no semicolon)")
        return _ENTITY.sub(replace, text)

    # ------------------------------------------------------------------ tokens

    def next(self) -> Token | None:
        if self._to_close is not None:
            name, self._to_close = self._to_close, None
            return EndElement(name)
        if self.i >= self.n:
            return None
        s = self.s
        if s[self.i] != "<":
            end = s.find("<", self.i)
            end = self.n if end < 0 else end
            raw = s[self.i:end]
            self.i = end
            return CharData(self._text(raw))
        self.i += 1
        if self.i >= self.n:
            raise self.eof()
        c = s[self.i]
        if c == "/":
            return self._end_tag()
        if c == "?":
            return self._proc_inst()
        if c == "!":
            return self._bang()
        return self._start_tag()

    def _end_tag(self) -> EndElement:
        self.i += 1
        name = self._read_name()
        if name is None:
            raise self.error("expected element name after </")
        self._space()
        if self.i >= self.n:
            raise self.eof()
        if self.s[self.i] != ">":
            raise self.error(f"invalid characters between </{name} and >")
        self.i += 1
        return EndElement(_split_name(name))

    def _proc_inst(self) -> ProcInst:
        self.i += 1
        target = self._read_name()
        if target is None:
            raise self.error("expected target name after <?")
        self._space()
        end = self.s.find("?>", self.i)
        if end < 0:
            self.i = self.n
            raise self.eof()
        inst = self.s[self.i:end]
        self.i = end + 2
        if target == "xml":
            version = _proc_inst_param("version", inst)
            if version not in ("", "1.0"):
                raise FormatError(f"xml: unsupported version: {version}; only version 1.0 is supported",
                                  format="xml")
        return ProcInst(target, inst)

    def _bang(self) -> Token:
        s = self.s
        self.i += 1                       # the '!'
        if s.startswith("--", self.i):
            self.i += 2
            end = s.find("-->", self.i)
            if end < 0:
                self.i = self.n
                raise self.eof()
            body = s[self.i:end]
            if "--" in body or body.endswith("-"):       # Go: "--" is not allowed inside a comment
                self.i = end + 3
                raise self.error('invalid sequence "--" not allowed in comments')
            self.i = end + 3
            return Comment(body)
        if s.startswith("[CDATA[", self.i):
            self.i += len("[CDATA[")
            end = s.find("]]>", self.i)
            if end < 0:
                self.i = self.n
                raise self.error("unexpected EOF in CDATA section")
            raw = s[self.i:end]
            self.i = end + 3
            return CharData(self._text(raw, cdata=True))
        if s.startswith("-", self.i):
            self.i += 1
            raise self.error("invalid sequence <!- not part of <!--")
        if s.startswith("[", self.i):
            # Go reads "<![" and reports anything but CDATA as an error
            self.i += 1
            raise self.error("invalid <![ sequence")
        return self._directive()

    def _directive(self) -> Directive:
        """``<!DOCTYPE ...>`` and friends: raw text up to the matching ``>``.

        Quotes and nested ``<...>`` are tracked; a comment inside is replaced by one space.
        """
        s = self.s
        out: list[str] = []
        quote = ""
        depth = 0
        i = self.i
        n = self.n
        while True:
            if i >= n:
                self.i = n
                raise self.eof()
            c = s[i]
            if not quote and c == ">" and depth == 0:
                i += 1
                break
            i += 1
            if quote:
                out.append(c)
                if c == quote:
                    quote = ""
            elif c in "'\"":
                out.append(c)
                quote = c
            elif c == ">":
                out.append(c)
                depth -= 1
            elif c == "<":
                if s.startswith("!--", i):
                    end = s.find("-->", i + 3)
                    if end < 0:
                        self.i = n
                        raise self.eof()
                    i = end + 3
                    out.append(" ")
                else:
                    out.append(c)
                    depth += 1
            else:
                out.append(c)
        self.i = i
        return Directive("".join(out))

    def _start_tag(self) -> StartElement:
        name = self._read_name()
        if name is None:
            raise self.error("expected element name after <")
        attrs: list[tuple[Name, str]] = []
        empty = False
        s = self.s
        while True:
            self._space()
            if self.i >= self.n:
                raise self.eof()
            c = s[self.i]
            if c == "/":
                self.i += 1
                if self.i >= self.n:
                    raise self.eof()
                if s[self.i] != ">":
                    raise self.error("expected /> in element")
                self.i += 1
                empty = True
                break
            if c == ">":
                self.i += 1
                break
            attr_name = self._read_name()
            if attr_name is None:
                raise self.error("expected attribute name in element")
            self._space()
            if self.i >= self.n:
                raise self.eof()
            if s[self.i] != "=":
                if self.strict:
                    raise self.error("attribute name without = in element")
                value = _split_name(attr_name)[1]
            else:
                self.i += 1
                self._space()
                value = self._attr_value()
            attrs.append((_split_name(attr_name), value))
        element = _split_name(name)
        if empty:
            self._to_close = element
        return StartElement(element, attrs)

    def _attr_value(self) -> str:
        s = self.s
        if self.i >= self.n:
            raise self.eof()
        quote = s[self.i]
        if quote in "\"'":
            end = s.find(quote, self.i + 1)
            if end < 0:
                self.i = self.n
                raise self.eof()
            raw = s[self.i + 1:end]
            if "<" in raw:
                self.i += 1 + raw.index("<")
                raise self.error("unescaped < inside quoted string")
            self.i = end + 1
            return self._text(raw)
        if self.strict:
            raise self.error("unquoted or missing attribute value in element")
        m = _UNQUOTED_ATTR.match(s, self.i)
        end = m.end() if m else self.i  # type: ignore[union-attr]
        value = s[self.i:end]
        self.i = end
        return value


def _proc_inst_param(param: str, inst: str) -> str:
    """Go's ``procInst``: the value of ``param="..."`` in a processing instruction."""
    match = re.search(rf"""{param}=(?:"([^"]*)"|'([^']*)')""", inst)
    if not match:
        return ""
    return match.group(1) if match.group(1) is not None else match.group(2)


def tokens(text: str, *, strict: bool = False, raw: bool = True) -> Iterator[Token]:
    """The token stream. ``raw`` is Go's ``RawToken`` (no namespace translation, no end-tag check);
    otherwise ``Token``: names are translated to namespace URLs and end tags are matched."""
    lexer = Lexer(text, strict=strict)
    if raw:
        while True:
            token = lexer.next()
            if token is None:
                return
            yield token
    yield from _translated(lexer, strict)


def _translate(name: Name, ns: dict[str, str], *, element: bool) -> Name:
    space, local = name
    if space == "xmlns":
        return name
    if space == "" and not element:
        return name
    if space == "xml":
        space = _XML_URL
    elif space == "" and local == "xmlns":
        return name
    if space in ns:
        space = ns[space]
    return space, local


def _translated(lexer: Lexer, strict: bool) -> Iterator[Token]:
    ns: dict[str, str] = {}
    stack: list[tuple[Name, list[tuple[str, str | None]]]] = []
    while True:
        token = lexer.next()
        if token is None:
            if stack:
                raise lexer.eof()
            return
        if isinstance(token, StartElement):
            saved: list[tuple[str, str | None]] = []
            for (space, local), value in token.attrs:
                if space == "xmlns":
                    saved.append((local, ns.get(local)))
                    ns[local] = value
                elif space == "" and local == "xmlns":
                    saved.append(("", ns.get("")))
                    ns[""] = value
            stack.append((token.name, saved))
            token = StartElement(
                _translate(token.name, ns, element=True),
                [(_translate(n, ns, element=False), v) for n, v in token.attrs])
        elif isinstance(token, EndElement):
            raw_name = token.name
            translated = _translate(raw_name, ns, element=True)
            while True:
                if not stack:
                    raise lexer.error(f"unexpected end element </{raw_name[1]}>")
                open_name, saved = stack[-1]
                if open_name == raw_name:
                    break
                if strict:
                    raise lexer.error(f"element <{open_name[1]}> closed by </{raw_name[1]}>")
                # non-strict: the end tag closes the innermost element, then it is tried again
                stack.pop()
                closed = _translate(open_name, ns, element=True)
                _restore(ns, saved)
                yield EndElement(closed)
            stack.pop()
            _restore(ns, saved)
            token = EndElement(translated)
        yield token


def _restore(ns: dict[str, str], saved: list[tuple[str, str | None]]) -> None:
    for prefix, previous in reversed(saved):
        if previous is None:
            ns.pop(prefix, None)
        else:
            ns[prefix] = previous
