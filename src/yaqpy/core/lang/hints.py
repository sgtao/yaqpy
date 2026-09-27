"""'Not Supported' hints for jq words yaqpy does not read yet (E7, 0926-03 5-6 / 決定 1).

Checked only after the lexer has already failed with "unexpected character" - a word listed
here never changes what parses; it only enriches that same error with a status and, where
there is one, a working alternative today. "Not Supported (yet)" names words this project's
own roadmap (21_docs/0926-03) plans to add later; "Not Supported" names words judged (9 章)
not worth adding - a permanent status, not "not implemented yet".

This table is hand-written from the plan, not derived from jq's source or tests (4 章: 出所の方針).
"""

from __future__ import annotations

import re

_NOT_YET: dict[str, str] = {
    "if": "planned for v0.9 (`if … then … elif … else … end`). "
         "Today: write a rewrite with assignment, or `select`.",
    "then": "part of `if … then … elif … else … end`, planned for v0.9.",
    "elif": "part of `if … then … elif … else … end`, planned for v0.9.",
    "else": "part of `if … then … elif … else … end`, planned for v0.9.",
    "try": "planned for v0.9 (`try … catch …`, and `EXPR?`). Today: `.foo?` already guards "
          "a single traversal.",
    "catch": "part of `try … catch …`, planned for v0.9.",
    "walk": "planned for v0.9. Today: write the recursion out (`..` with `with_entries`/`map`).",
    "reduce": "yaqpy takes the value-then-keyword order: `S as $x ireduce (init; update)`.",
    "foreach": "planned for v1.0. Today: `ireduce` covers a running total.",
    "until": "planned for v1.0.",
    "while": "planned for v1.0.",
    "debug": "planned for v0.9.",
    "stderr": "planned for v0.9.",
    "halt": "planned for v0.9.",
    "halt_error": "planned for v0.9.",
}

_NOT_SUPPORTED: dict[str, str] = {
    "def": "function definitions need scope, recursion and closures that are not planned "
          "(the plan's 決定 7). Write the expression out, or split it across `|`.",
    "import": "reads a file, which does not fit yaqpy's safe-by-default design.",
    "include": "reads a file, which does not fit yaqpy's safe-by-default design.",
    "label": "not planned - the cost is judged too high for the value. "
             "`first(f)`/`limit(n; f)` cover most uses.",
    "break": "goes with `label`, which is not planned.",
    "input": "reads input one value at a time, which does not fit yaqpy's build-everything-"
            "at-once evaluator. Use `eval-all` (`ea`) instead.",
    "inputs": "see `input`. Use `eval-all` (`ea`) instead.",
    "input_line_number": "see `input`: without reading input one line at a time, there is no "
                        "line number to report.",
    "repeat": "an unbounded generator does not fit yaqpy's build-everything-at-once evaluator. "
             "Use `range`/`limit` (bounded) instead.",
    "tostream": "streaming output does not fit yaqpy's build-everything-at-once evaluator.",
    "fromstream": "see `tostream`.",
    "truncate_stream": "see `tostream`.",
    "combinations": "not planned yet (a v1.0 candidate).",
    "infinite": "not planned yet (pending how YAML's `.inf`/`.nan` should map - a v1.0 candidate).",
    "isinfinite": "see `infinite`.",
    "isnormal": "see `infinite`.",
}

_WORD_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def hint_for(expression: str, position: int) -> str | None:
    """A 'Not Supported' line for the jq word starting at ``position``, or ``None`` when the
    text there is not one of the words this table knows about."""
    match = _WORD_PATTERN.match(expression, position)
    if match is None:
        return None
    word = match.group(0)
    if word in _NOT_YET:
        return f"Not Supported (yet): `{word}` - {_NOT_YET[word]}"
    if word in _NOT_SUPPORTED:
        return f"Not Supported: `{word}` - {_NOT_SUPPORTED[word]}"
    return None
