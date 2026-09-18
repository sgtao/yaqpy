"""Leading content: the comments, blank lines, directives and ``---`` separators
that appear before the first document (yq's ``$yqDocSeparator$`` convention)."""

from __future__ import annotations

import re

DOC_SEPARATOR_MARKER = "$yqDocSeparator$"
_COMMENT_LINE = re.compile(r"^\s*#")


def render_leading_content(content: str, *, print_doc_separators: bool = True) -> str:
    """Go's ``PrintYAMLLeadingContent``: turn stored leading content back into text."""
    if content == "":
        return ""
    out: list[str] = []
    lines = content.split("\n")
    # split() leaves a trailing "" when content ends with "\n"
    trailing_newline = content.endswith("\n")
    if trailing_newline:
        lines = lines[:-1]
    for raw in lines:
        line = raw
        ending = "\n"
        if line.endswith("\r"):
            line = line[:-1]
            ending = "\r\n"
        if DOC_SEPARATOR_MARKER in line:
            if print_doc_separators:
                out.append("---" + ending)
            continue
        if line != "" and line[0] != "%" and not _COMMENT_LINE.match(line):
            line = "# " + line
        out.append(line + ending)
    text = "".join(out)
    if not trailing_newline and lines and not text.endswith("\n"):
        text += "\n"
    return text
