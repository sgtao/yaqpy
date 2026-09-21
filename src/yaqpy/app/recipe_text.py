"""Plain-text presentation of what a recipe did (the CLI prints it; a library user may reuse it)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from yaqpy.app.recipe_service import RecipeRun
from yaqpy.recipes.diff import ADDED, CHANGED, MOVED, REMOVED


def short(value: Any, limit: int = 48) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def summary_lines(run: RecipeRun) -> list[str]:
    """The few lines worth seeing next to a converted result (nothing when all is well)."""
    report = run.report
    if report is None:
        return []
    lines: list[str] = []
    for item in report.dropped:
        label = "dropped" if item.declared else "NOT HANDLED"
        count = f" (x{len(item.where)})" if item.declared and len(item.where) > 1 else ""
        lines.append(f"{label} {item.path}{count} - {item.reason}")
    for added in report.added:
        lines.append(f"added {added.path} = {short(added.value)} - {added.reason}")
    for issue in report.issues:
        lines.append(f"target schema: {issue}")
    lines.extend(f"note: {note}" for note in report.notes)
    return lines


def render_report(run: RecipeRun) -> str:
    recipe, report = run.recipe, run.report
    out = [f"Recipe:  {recipe.name} ({recipe.origin})",
           f"Input:   {run.input_name} ({run.input_format})",
           f"Output:  {run.output_format}"]
    if report is None:
        out.append("(no report: the input has no document, or the recipe produced no result)")
        return "\n".join(out) + "\n"
    if report.checked_drops or report.checked_schema:
        out.append("Verdict: " + ("nothing was lost without the recipe saying so, and the result "
                                  "follows the target schema" if report.clean
                                  else "needs a look (see below)"))
    declared = [d for d in report.dropped if d.declared]
    if declared:
        out += ["", "Dropped (the recipe declares that it does not carry these over):"]
        for item in declared:
            where = ", ".join(item.where[:3]) + (", ..." if len(item.where) > 3 else "")
            out.append(f"  {item.path}  [{where}]  - {item.reason}")
    if report.not_handled:
        out += ["", "Not handled (in the input, but neither carried nor declared dropped):"]
        out += [f"  {item.path}" for item in report.not_handled]
    if report.added:
        out += ["", "Added by the recipe (the input gave nothing):"]
        out += [f"  {a.path} = {short(a.value)}  - {a.reason}" for a in report.added]
    out += ["", "Changes (before -> after; a move is a candidate: the same value at another path):"]
    if not report.changes:
        out.append("  (none)")
    for change in report.changes:
        if change.kind == MOVED:
            out.append(f"  moved    {change.path} -> {change.to_path}  ({short(change.before)})")
        elif change.kind == CHANGED:
            out.append(f"  changed  {change.path}  {short(change.before)} -> {short(change.after)}")
        elif change.kind == REMOVED:
            out.append(f"  removed  {change.path}  ({short(change.before)})")
        elif change.kind == ADDED:
            out.append(f"  added    {change.path}  ({short(change.after)})")
    out += ["", "Target schema:"]
    if not report.checked_schema:
        out.append("  (this recipe has no target schema)")
    elif not report.issues:
        out.append("  the result matches")
    else:
        out += [f"  {issue}" for issue in report.issues]
    if report.notes:
        out += [""] + [f"Note: {note}" for note in report.notes]
    return "\n".join(out) + "\n"


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
    lines = ["  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip()
             for row in (headers, *rows)]
    return "\n".join(lines) + "\n"
