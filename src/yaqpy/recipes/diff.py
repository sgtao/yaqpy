"""Compare a document before and after a conversion, path by path.

Both sides are flattened to ``path -> value`` (a leaf is a scalar, an empty ``{}`` or an empty
``[]``). A path only in the input is *removed*, one only in the output is *added*, one in both with
another value is *changed*. A removed and an added leaf that carry the same value, when that value
occurs once on each side, are reported as a *move* (a rename candidate) instead: ``max_tokens`` that
turned up as ``generationConfig.maxOutputTokens`` is one number, not one deletion and one addition.
Only a candidate: two different fields can hold the same number.

Paths are compared as they are. When a list is rebuilt, its items are compared by position, so a
list that lost its first item shows every later item as changed, unless the values can be followed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
MOVED = "moved"


@dataclass(frozen=True, slots=True)
class Change:
    kind: str
    path: str                 # for MOVED: where it was
    to_path: str = ""         # for MOVED: where it is now
    before: Any = None
    after: Any = None


def flatten(data: Any) -> dict[str, Any]:
    """``{".a[0].b": 1, ...}``; the root of a scalar is ``"."``."""
    leaves: dict[str, Any] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict) and node:
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list) and node:
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        else:
            leaves[path or "."] = node

    walk(data, "")
    return leaves


def _fingerprint(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _movable(value: Any) -> bool:
    """A value that identifies a field: not a bool or null (they occur everywhere), not empty."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (dict, list)):
        return False           # only an empty container can be a leaf, and that says nothing
    return value != ""


def diff(before: Any, after: Any) -> list[Change]:
    old, new = flatten(before), flatten(after)
    changed = {p: (old[p], new[p]) for p in old if p in new and _fingerprint(old[p]) != _fingerprint(new[p])}
    # A path whose value changed is also a place a value left and a place a value arrived, so a
    # value that moved into (or out of) it is found there too: when a list is rebuilt, the items
    # change their positions and every position would otherwise look like an edit.
    leaving = {**{p: v for p, v in old.items() if p not in new}, **{p: v[0] for p, v in changed.items()}}
    arriving = {**{p: v for p, v in new.items() if p not in old}, **{p: v[1] for p, v in changed.items()}}

    def by_value(items: dict[str, Any]) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for path, value in items.items():
            if _movable(value):
                grouped.setdefault(_fingerprint(value), []).append(path)
        return grouped

    gone, came = by_value(leaving), by_value(arriving)
    changes: list[Change] = []
    moved_from: set[str] = set()
    moved_to: set[str] = set()
    for fingerprint, sources in gone.items():
        targets = came.get(fingerprint, [])
        if len(sources) == 1 and len(targets) == 1 and sources[0] != targets[0]:
            changes.append(Change(MOVED, sources[0], targets[0], before=leaving[sources[0]],
                                  after=arriving[targets[0]]))
            moved_from.add(sources[0])
            moved_to.add(targets[0])
    for path, (was, now) in changed.items():
        if path in moved_from and path in moved_to:
            continue                                            # both sides are explained by moves
        if path in moved_to:
            changes.append(Change(REMOVED, path, before=was))    # the new value came from elsewhere
        elif path in moved_from:
            changes.append(Change(ADDED, path, after=now))       # the old value went elsewhere
        else:
            changes.append(Change(CHANGED, path, before=was, after=now))
    changes.extend(Change(REMOVED, p, before=v) for p, v in leaving.items()
                   if p not in changed and p not in moved_from)
    changes.extend(Change(ADDED, p, after=v) for p, v in arriving.items()
                   if p not in changed and p not in moved_to)
    order = {MOVED: 0, CHANGED: 1, REMOVED: 2, ADDED: 3}
    changes.sort(key=lambda c: order[c.kind])       # stable: the input's order within each kind
    return changes
