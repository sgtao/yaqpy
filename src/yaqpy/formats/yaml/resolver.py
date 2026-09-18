"""Tag resolution for YAML scalars (YAML 1.2 Core Schema plus go-yaml's extras)."""

from __future__ import annotations

import re

from yaqpy.core.model import tags as _tags

# go-yaml v3 resolves these plain scalars to !!timestamp
TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}"
    r"(?:(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}(?:\.[0-9]*)?"
    r"(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?)?$"
)
BINARY_INT_RE = re.compile(r"^[-+]?0b[01_]+$")


def resolve_plain(text: str) -> str:
    """Tag for a plain (unquoted) scalar."""
    tag = _tags.resolve_plain(text)
    if tag == "!!str":
        if TIMESTAMP_RE.match(text):
            return "!!timestamp"
        if BINARY_INT_RE.match(text):
            return "!!int"
    return tag


def is_plain_safe_for_tag(text: str, tag: str) -> bool:
    """True if emitting ``text`` as a plain scalar would resolve back to ``tag``."""
    return resolve_plain(text) == tag
