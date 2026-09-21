"""Nesting depth of a node tree."""

from __future__ import annotations

from yaqpy.core.model.node import Node


def node_depth(root: Node, limit: int) -> int:
    """Nesting depth of a node tree (stops early once ``limit`` is exceeded)."""
    deepest = 0
    stack = [(root, 1)]
    while stack:
        node, level = stack.pop()
        deepest = max(deepest, level)
        if deepest > limit:
            return deepest
        for child in node.content:
            stack.append((child, level + 1))
    return deepest
