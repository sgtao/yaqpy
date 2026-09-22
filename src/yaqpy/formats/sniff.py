"""Content-based format detection (a yaqpy extension; Go yq has no such thing).

Used only when the file name gives no answer (no extension, an unknown one, or piped/pasted text
with no name at all): the extension always wins first when it names a known format, to keep the
Go-compatible default intact (see ``FormatRegistry.guess_from_filename``). This module only answers
the question "what does the content itself look like", cheaply: it reads the first ``_SAMPLE_LINES``
non-blank, non-comment lines (plus a bounded prefix check for JSON), never the whole file.

The result is a plain guess, not a proof: ``None`` means nothing looked confident enough, and every
caller in this codebase then falls back to "yaml" - the same default a wholly unrecognised file
already got before this module existed.
"""

from __future__ import annotations

import json
import re

_SAMPLE_LINES = 10
_JSON_PARSE_LIMIT = 8 * 1024 * 1024  # 8 MiB: past this a cheap structural check replaces json.loads

_TOML_HEADER = re.compile(r'^\[{1,2}[^\[\]#]+\]{1,2}$')
_EQUALS_LINE = re.compile(r'^[A-Za-z0-9_.\-\[\]"\']+\s*=\s*(.+)$')
# A value shape that only TOML's typed grammar produces; a plain Properties value is unquoted text.
_TOML_VALUE = re.compile(r'^("""|\'\'\'|"|\'|\[|\{|\d{4}-\d{2}-\d{2})')


def _head_lines(text: str, limit: int = _SAMPLE_LINES) -> list[str]:
    """The first ``limit`` lines that are neither blank nor a comment.

    ``#`` is a comment in both TOML and Properties; ``!`` is a comment only in Properties, but
    skipping it here too costs nothing (it is not a valid start of a TOML key either).
    """
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#!":
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _detect_delimited(lines: list[str]) -> str | None:
    """csv/tsv: the header's delimiter count repeated on every sampled line."""
    if len(lines) < 2:
        return None
    header = lines[0]
    tabs, commas = header.count("\t"), header.count(",")
    if tabs == 0 and commas == 0:
        return None
    delimiter, name = ("\t", "tsv") if tabs >= commas else (",", "csv")
    count = header.count(delimiter)
    if count >= 1 and all(line.count(delimiter) == count for line in lines):
        return name
    return None


def detect_format(text: str) -> str | None:
    """Guess a format name (``"json"``, ``"xml"``, ``"toml"``, ``"props"``, ``"csv"``, ``"tsv"``)
    from ``text`` alone. ``None`` when nothing looks confident (the caller then uses "yaml")."""
    stripped = text.lstrip("﻿ \t\r\n")
    if not stripped:
        return None
    if stripped[0] == "<":
        return "xml"
    if stripped[0] in "{[":
        if len(text) <= _JSON_PARSE_LIMIT:
            try:
                json.loads(text)
            except ValueError:
                pass
            else:
                return "json"
        elif stripped.rstrip()[-1:] == ("}" if stripped[0] == "{" else "]"):
            return "json"          # too big to parse for a mere guess; the shape is enough
    lines = _head_lines(text)
    if not lines:
        return None
    if any(_TOML_HEADER.match(line) for line in lines):
        return "toml"
    matches = [_EQUALS_LINE.match(line) for line in lines]
    matched = [m for m in matches if m]
    if len(matched) >= (len(lines) + 1) // 2:
        if any(_TOML_VALUE.match(m.group(1).strip()) for m in matched):
            return "toml"
        return "props"
    return _detect_delimited(lines)
