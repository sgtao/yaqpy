"""Go (RE2) regular expressions on top of Python's ``re``.

Go's ``regexp`` and Python's ``re`` agree on most patterns. This module bridges the
differences that matter for yq expressions:

* ``$`` (without ``(?m)``) and ``\\z`` match only at the very end of the text. Python's ``$``
  also matches before a trailing newline, which YAML block scalars usually have.
* ``(?<name>...)`` names a group (Go 1.22+); Python only knows ``(?P<name>...)``.
* POSIX classes such as ``[[:alpha:]]``.
* ``ReplaceAllString`` templates use ``$1`` / ``${name}`` / ``$$`` instead of ``\\1``.
* Empty matches right after a previous match are skipped by Go's "find all".
* ``offset`` / ``length`` reported by ``match`` are UTF-8 byte counts in Go.

Not supported (the pattern is refused with an error): ``\\pL`` / ``\\p{...}`` classes,
``(?U)``, and inline flags that are not at the start of the pattern.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

_POSIX = {
    "alnum": "0-9A-Za-z", "alpha": "A-Za-z", "ascii": "\\x00-\\x7f", "blank": "\\t ",
    "cntrl": "\\x00-\\x1f\\x7f", "digit": "0-9", "graph": "!-~", "lower": "a-z",
    "print": " -~", "punct": "!-/:-@\\[-`{-~", "space": "\\t\\n\\v\\f\\r ",
    "upper": "A-Z", "word": "0-9A-Za-z_", "xdigit": "0-9A-Fa-f",
}
_LEADING_FLAGS = re.compile(r"^\(\?([a-zA-Z]+)\)")


class RegexError(ValueError):
    """The pattern is not valid, or uses something this port does not support."""


def _leading_flags(pattern: str) -> tuple[str, int, bool]:
    """Strip leading ``(?flags)`` groups; return (rest, re flags, multiline)."""
    flags = 0
    multiline = False
    while True:
        match = _LEADING_FLAGS.match(pattern)
        if match is None:
            return pattern, flags, multiline
        for letter in match.group(1):
            if letter == "i":
                flags |= re.IGNORECASE
            elif letter == "m":
                flags |= re.MULTILINE
                multiline = True
            elif letter == "s":
                flags |= re.DOTALL
            elif letter == "U":
                raise RegexError("the (?U) flag (ungreedy) is not supported")
            else:
                raise RegexError(f"invalid or unsupported Perl syntax: `(?{letter}`")
        pattern = pattern[match.end():]


def _translate(pattern: str, multiline: bool) -> str:
    out: list[str] = []
    i, n = 0, len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\" and i + 1 < n:
            nxt = pattern[i + 1]
            if nxt in "pP":
                raise RegexError("unicode character classes (\\p{...}) are not supported")
            if nxt == "z" and not in_class:
                out.append("\\Z")
            elif nxt == "Q":                     # \Q...\E: a literal run
                end = pattern.find("\\E", i + 2)
                literal = pattern[i + 2:] if end < 0 else pattern[i + 2:end]
                out.append(re.escape(literal))
                i = n if end < 0 else end + 2
                continue
            else:
                out.append(c + nxt)
            i += 2
            continue
        if in_class:
            if c == "[" and pattern.startswith("[:", i):
                end = pattern.find(":]", i + 2)
                if end > 0:
                    name = pattern[i + 2:end]
                    negated = name.startswith("^")
                    body = _POSIX.get(name[1:] if negated else name)
                    if body is None or negated:
                        raise RegexError(f"invalid character class range: `{pattern[i:end + 2]}`")
                    out.append(body)
                    i = end + 2
                    continue
            if c == "]":
                in_class = False
                out.append(c)
            else:
                out.append("\\[" if c == "[" else c)   # a [ inside a class is a literal
        elif c == "[":
            in_class = True
            out.append(c)
            i += 1
            if i < n and pattern[i] == "^":
                out.append("^")
                i += 1
            if i < n and pattern[i] == "]":      # a leading ] is a literal
                out.append("\\]")
                i += 1
            continue
        elif c == "(" and pattern.startswith("(?<", i) and pattern[i + 3:i + 4] not in ("=", "!"):
            out.append("(?P<")
            i += 3
            continue
        elif c == "$" and not multiline:
            out.append("\\Z")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def compile_go(pattern: str) -> re.Pattern[str]:
    rest, flags, multiline = _leading_flags(pattern)
    try:
        return re.compile(_translate(rest, multiline), flags)
    except re.error as e:
        raise RegexError(f"error parsing regexp: {e}") from None


# ----------------------------------------------------------------------------- find all

def find_all(regex: re.Pattern[str], text: str) -> Iterator[re.Match[str]]:
    """Go's ``FindAll``: leftmost matches; an empty match abutting the previous one is skipped."""
    pos, previous_end = 0, -1
    while pos <= len(text):
        match = regex.search(text, pos)
        if match is None:
            return
        accept = True
        if match.end() == pos:                   # an empty match at the search position
            if match.start() == previous_end:
                accept = False
            pos += 1
        else:
            pos = match.end()
        previous_end = match.end()
        if accept:
            yield match


def byte_offset(text: str, index: int) -> int:
    """The UTF-8 offset of character ``index`` (Go reports offsets in bytes)."""
    if text.isascii():
        return index
    return len(text[:index].encode("utf-8", "surrogatepass"))


def byte_length(text: str) -> int:
    return len(text) if text.isascii() else len(text.encode("utf-8", "surrogatepass"))


# ----------------------------------------------------------------------------- replace

def _name_end(template: str, start: int) -> int:
    end = start
    while end < len(template) and (template[end].isalpha() or template[end].isdigit()
                                   or template[end] == "_"):
        end += 1
    return end


def _group_text(match: re.Match[str], name: str) -> str:
    if name.isdigit() and name.isascii():
        index = int(name)
        if index <= (match.re.groups or 0):
            return match.group(index) or ""
        return ""
    # Go takes the first group with that name that took part in the match
    if name in match.re.groupindex:
        return match.group(name) or ""
    return ""


def expand(template: str, match: re.Match[str]) -> str:
    """Go's ``Regexp.Expand``: ``$1``, ``${1}``, ``$name``, ``${name}`` and ``$$``."""
    out: list[str] = []
    i, n = 0, len(template)
    while i < n:
        at = template.find("$", i)
        if at < 0:
            out.append(template[i:])
            break
        out.append(template[i:at])
        i = at
        if i + 1 < n and template[i + 1] == "$":
            out.append("$")
            i += 2
            continue
        braced = i + 1 < n and template[i + 1] == "{"
        start = i + (2 if braced else 1)
        end = _name_end(template, start)
        closes = braced and end < n and template[end] == "}"
        if end == start or (braced and not closes):
            out.append("$")                      # malformed: a literal dollar sign
            i += 1
            continue
        out.append(_group_text(match, template[start:end]))
        i = end + (1 if braced else 0)
    return "".join(out)


def replace_all(regex: re.Pattern[str], text: str, template: str) -> str:
    """Go's ``ReplaceAllString``."""
    out: list[str] = []
    last = 0
    for match in find_all(regex, text):
        out.append(text[last:match.start()])
        out.append(expand(template, match))
        last = match.end()
    out.append(text[last:])
    return "".join(out)
