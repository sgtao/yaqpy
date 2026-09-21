"""Golden-test harness: run extracted Go scenarios and compare like ``resultToString``."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yaqpy.app.printer import ResultPrinter
from yaqpy.app.service import YqService
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.core.model.convert import to_python
from yaqpy.core.model.node import Kind, Node
from yaqpy.errors import EvaluationError, ExpressionSyntaxError, YqError
from yaqpy.formats.yaml.codec import YamlDecoder, YamlEncoder
from yaqpy.options import Options, SecurityPolicy, YamlOptions

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden" / "operators"

# Operators implemented in phase 1 (design doc 8-2); scenarios from these files
# make up the MVP pass rate.
MVP_FILES = {
    "operator_traverse_path", "operator_recursive_descent", "operator_pipe", "operator_union",
    "operator_select", "operator_assign", "operator_add", "operator_subtract", "operator_multiply",
    "operator_divide", "operator_modulo", "operator_alternative", "operator_equals",
    "operators_compare", "operator_booleans", "operator_value", "operator_collect",
    "operator_collect_object", "operator_create_map", "operator_length", "operator_keys",
    "operator_has", "operator_delete", "operator_entries", "operator_map", "operator_sort",
    "operator_path", "operator_variables", "operator_env", "operator_tag", "operator_style",
    "operator_comments", "operator_document_index", "operator_file", "operator_parent",
    "operator_slice",
}

# operators_test.go's TestMain pins ``Now`` to this instant (the 4 is nanoseconds).
GO_TEST_NOW = datetime(2021, 5, 19, 1, 2, 3, 0, tzinfo=timezone.utc)

_RESULT_RE = re.compile(r"^D(?P<doc>\d+), P\[(?P<path>[^\]]*)\], \((?P<tag>[^)]*)\)::(?P<body>.*)$", re.DOTALL)


@dataclass(slots=True)
class Outcome:
    id: str
    source: str
    status: str            # exact | semantic | fail | error | unsupported | unresolved | skipped
    detail: str = ""
    expected: list[str] | None = None
    actual: list[str] | None = None


def load_scenarios(directory: Path = GOLDEN_DIR) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "extracted.json":
            continue
        scenarios.extend(json.loads(path.read_text(encoding="utf-8")))
    return scenarios


def format_path(path: list[str | int]) -> str:
    return "[" + " ".join(str(p) for p in path) + "]"


def result_to_string(node: Node, options: Options) -> str:
    """Go's ``resultToString``: ``D<doc>, P<path>, (<tag>)::<yaml>``."""
    encoder = YamlEncoder(options, unwrap_scalar=True)
    buf = io.StringIO()

    class _Sink:
        def write(self, text: str) -> None:
            buf.write(text)

        def finish(self) -> str:
            return buf.getvalue()

    ResultPrinter(encoder, _Sink()).print_results([node])
    tag = "alias" if node.kind is Kind.ALIAS else node.tag
    return f"D{node.document()}, P{format_path(node.path())}, ({tag})::{buf.getvalue()}"


def run_scenario(scenario: dict[str, Any]) -> Outcome:
    sid = scenario["id"]
    source = scenario["source"]
    if scenario.get("unresolved"):
        return Outcome(sid, source, "unresolved", "; ".join(scenario["unresolved"]))
    if scenario.get("requires_format"):
        return Outcome(sid, source, "skipped", f"requires format {scenario['requires_format']}")
    fix_merge = (scenario["description"].startswith("FIXED:")
                 or scenario.get("group", "").startswith("fixed"))
    # envOperatorSecurityDisabledScenarios run with DisableEnvOps=true in Go
    env_disabled = scenario["expected_error"] == "env operations have been disabled"
    options = Options(
        indent=4,
        security=SecurityPolicy(allow_env=not env_disabled, allow_file=True),
        yaml=YamlOptions(indent=4, fix_merge_anchor_to_spec=fix_merge),
    )
    service = YqService(InMemoryFileSystem(), StaticEnvironment(scenario.get("environment") or {}),
                        clock=lambda: GO_TEST_NOW)
    inputs: list[Node] = []
    try:
        if scenario["document"] != "":
            decoder = YamlDecoder(options)
            inputs.extend(decoder.decode_documents(scenario["document"], filename="sample.yml",
                                                   file_index=0))
            if scenario["document2"] != "":
                inputs.extend(decoder.decode_documents(scenario["document2"], filename="another.yml",
                                                       file_index=1, process_leading=True))
            for node in inputs:
                node.evaluate_together = True    # Go's readDocuments
        else:
            inputs.append(Node.null(value=""))
        results = service.evaluate_nodes(scenario["expression"], inputs, options)
        actual = [result_to_string(n, options) for n in results]
    except (ExpressionSyntaxError, EvaluationError) as e:
        message = str(e)
        if ("unknown operator" in message or "unexpected character" in message)                 and not scenario["expected_error"]:
            return Outcome(sid, source, "unsupported", message)
        if scenario["expected_error"]:
            status = "exact" if message == scenario["expected_error"] else "semantic"
            return Outcome(sid, source, status, f"expected error {scenario['expected_error']!r}, got {message!r}")
        return Outcome(sid, source, "error", message)
    except YqError as e:
        if scenario["expected_error"]:
            status = "exact" if str(e) == scenario["expected_error"] else "semantic"
            return Outcome(sid, source, status, str(e))
        return Outcome(sid, source, "error", f"{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001 - report crashes as errors
        return Outcome(sid, source, "error", f"CRASH {type(e).__name__}: {e}")
    if scenario["expected_error"]:
        return Outcome(sid, source, "fail", f"expected error {scenario['expected_error']!r} but got results",
                       scenario["expected_error"], actual)
    expected = scenario["expected"]
    if actual == expected:
        return Outcome(sid, source, "exact", "", expected, actual)
    if semantically_equal(expected, actual, options):
        return Outcome(sid, source, "semantic", "", expected, actual)
    return Outcome(sid, source, "fail", "", expected, actual)


def _parse_result(text: str, options: Options) -> tuple[str, str, str, Any] | None:
    m = _RESULT_RE.match(text)
    if m is None:
        return None
    body = m.group("body")
    try:
        docs = list(YamlDecoder(options).decode_documents(body, process_leading=False))
        value = [to_python(d) for d in docs]
    except Exception:  # noqa: BLE001
        value = body.strip()
    return m.group("doc"), m.group("path"), m.group("tag"), value


def semantically_equal(expected: list[str], actual: list[str], options: Options) -> bool:
    if len(expected) != len(actual):
        return False
    for e, a in zip(expected, actual):
        pe = _parse_result(e, options)
        pa = _parse_result(a, options)
        if pe is None or pa is None:
            if e.strip() != a.strip():
                return False
            continue
        if pe[:3] != pa[:3]:
            return False
        if pe[3] != pa[3]:
            # tolerate numeric formatting differences (1e+06 vs 1000000.0)
            if not _numbers_equal(pe[3], pa[3]):
                return False
    return True


def _numbers_equal(a: Any, b: Any) -> bool:
    try:
        return float(str(a)) == float(str(b))
    except (TypeError, ValueError):
        return False


def summarize(outcomes: list[Outcome]) -> dict[str, Any]:
    def bucket(items: list[Outcome]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in items:
            counts[o.status] = counts.get(o.status, 0) + 1
        return counts

    def rate(items: list[Outcome]) -> float:
        applicable = [o for o in items if o.status in ("exact", "semantic", "fail", "error")]
        if not applicable:
            return 0.0
        passed = sum(1 for o in applicable if o.status in ("exact", "semantic"))
        return passed / len(applicable)

    mvp = [o for o in outcomes if o.source[:-len("_test.go")] in MVP_FILES]
    return {
        "all": {"counts": bucket(outcomes), "pass_rate": rate(outcomes), "total": len(outcomes)},
        "mvp": {"counts": bucket(mvp), "pass_rate": rate(mvp), "total": len(mvp)},
    }
