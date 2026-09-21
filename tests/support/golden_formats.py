"""Golden-test harness for the Go *format* scenarios (XML, CSV/TSV, TOML, properties).

The scenarios live in ``tests/golden/formats/<name>.json`` (see ``tools/extract_go_scenarios.py``).
Each one names a ``scenario_type`` that says which decoder and encoder the Go test wires together
(``decode``: xml -> yaml, ``encode``: yaml -> xml, ``roundtrip``: xml -> xml, ...). ``CASES`` is the
same table for yaqpy. A format that is not registered yet makes its scenarios ``unsupported``, so
this file only fails once a format is implemented and then regresses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yaqpy.app.dto import EvalMode, EvaluateRequest, InputSource
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.printer import MemorySink
from yaqpy.app.service import YqService
from yaqpy.core.model.convert import to_python
from yaqpy.errors import UnknownFormatError, YqError
from yaqpy.formats.yaml.codec import YamlDecoder
from yaqpy.options import CsvOptions, Options, PropertiesOptions, XmlOptions, YamlOptions
from tests.support.golden import Outcome

_COMMENT_RE = re.compile(r"#[^\n]*")

FORMATS_DIR = Path(__file__).resolve().parent.parent / "golden" / "formats"

# Formats covered so far (the Go test files that are extracted).
FORMAT_FILES = ("xml", "csv", "toml", "properties")


@dataclass(frozen=True, slots=True)
class Case:
    """How one Go ``scenarioType`` maps onto yaqpy."""

    input_format: str
    output_format: str
    options: Options
    unwrap_scalar: bool | None = None
    expects_error: bool = False


_YAML = Options()
_YAML_INDENT4 = Options(indent=4, yaml=YamlOptions(indent=4))


def _xml(**kwargs: Any) -> Options:
    return Options(xml=XmlOptions(**kwargs))


def _props(**kwargs: Any) -> Options:
    return Options(props=PropertiesOptions(**kwargs))


# (source file, scenario type) -> Case. Types not listed are reported as "unresolved".
CASES: dict[tuple[str, str], Case] = {
    # ---- XML (xml_test.go: testXMLScenario)
    ("xml", ""): Case("xml", "yaml", _YAML_INDENT4),
    ("xml", "decode"): Case("xml", "yaml", _YAML_INDENT4),
    ("xml", "encode"): Case("yaml", "xml", _YAML),
    ("xml", "roundtrip"): Case("xml", "xml", _YAML),
    ("xml", "decode-keep-ns"): Case("xml", "yaml", _xml(keep_namespace=True)),
    ("xml", "decode-raw-token"): Case("xml", "yaml", _xml(raw_token=True)),
    ("xml", "decode-raw-token-off"): Case("xml", "yaml", _xml(raw_token=False)),
    ("xml", "roundtrip-skip-directives"): Case("xml", "xml", _xml(skip_directives=True)),
    ("xml", "decode-error"): Case("xml", "yaml", _YAML, expects_error=True),
    ("xml", "encode-error"): Case("yaml", "xml", _YAML, expects_error=True),
    # ---- CSV / TSV (csv_test.go: testCSVScenario)
    ("csv", "encode-csv"): Case("yaml", "csv", _YAML),
    ("csv", "encode-tsv"): Case("yaml", "tsv", _YAML),
    ("csv", "decode-csv"): Case("csv", "yaml", _YAML),
    ("csv", "decode-csv-no-auto"): Case("csv", "yaml", Options(csv=CsvOptions(auto_parse=False))),
    ("csv", "decode-tsv-object"): Case("tsv", "yaml", _YAML),
    ("csv", "roundtrip-csv"): Case("csv", "csv", _YAML),
    # ---- TOML (toml_test.go: testTomlScenario)
    ("toml", ""): Case("toml", "yaml", _YAML),
    ("toml", "decode"): Case("toml", "yaml", _YAML),
    ("toml", "decode-error"): Case("toml", "yaml", _YAML, expects_error=True),
    ("toml", "roundtrip"): Case("toml", "toml", _YAML),
    ("toml", "encode"): Case("yaml", "toml", _YAML),
    ("toml", "encode-json"): Case("json", "toml", _YAML),
    # ---- properties (properties_test.go: TestPropertyScenarios)
    ("properties", ""): Case("yaml", "props", _YAML),
    ("properties", "decode"): Case("props", "yaml", _YAML),
    ("properties", "decode-array-brackets"): Case("props", "yaml", _props(use_array_brackets=True)),
    ("properties", "encode-wrapped"): Case("yaml", "props", _YAML, unwrap_scalar=False),
    ("properties", "encode-array-brackets"): Case("yaml", "props", _props(use_array_brackets=True)),
    ("properties", "encode-custom-separator"): Case("yaml", "props", _props(key_value_separator=" :@ ")),
    ("properties", "roundtrip"): Case("props", "props", _YAML),
}


def load_format_scenarios(directory: Path = FORMATS_DIR) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for name in FORMAT_FILES:
        path = directory / f"{name}.json"
        if path.exists():
            scenarios.extend(json.loads(path.read_text(encoding="utf-8")))
    return scenarios


def source_name(scenario: dict[str, Any]) -> str:
    """``xml_test.go`` -> ``xml``."""
    return scenario["source"][:-len("_test.go")]


def case_for(scenario: dict[str, Any]) -> Case | None:
    return CASES.get((source_name(scenario), scenario["scenario_type"]))


def run_format_scenario(scenario: dict[str, Any]) -> Outcome:
    sid = scenario["id"]
    source = scenario["source"]
    if scenario.get("unresolved"):
        return Outcome(sid, source, "unresolved", "; ".join(scenario["unresolved"]))
    case = case_for(scenario)
    if case is None:
        return Outcome(sid, source, "unresolved", f"unknown scenario type {scenario['scenario_type']!r}")
    options = case.options
    service = YqService(InMemoryFileSystem(), StaticEnvironment({}))
    request = EvaluateRequest(
        expression=scenario["expression"] or ".",
        inputs=(InputSource("sample.yml", scenario["input"]),),
        mode=EvalMode.STREAM,
        options=options,
        input_format=case.input_format,
        output_format=case.output_format,
        unwrap_scalar=case.unwrap_scalar,
    )
    try:
        actual = service.evaluate(request, MemorySink()).output or ""
    except UnknownFormatError as e:
        return Outcome(sid, source, "unsupported", str(e))
    except YqError as e:
        if case.expects_error:
            status = "exact" if str(e) == scenario["expected_error"] else "semantic"
            return Outcome(sid, source, status,
                           f"expected error {scenario['expected_error']!r}, got {str(e)!r}")
        return Outcome(sid, source, "error", f"{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001 - report crashes as errors
        return Outcome(sid, source, "error", f"CRASH {type(e).__name__}: {e}")
    if case.expects_error:
        return Outcome(sid, source, "fail",
                       f"expected error {scenario['expected_error']!r} but got a result",
                       [scenario["expected_error"]], [actual])
    expected = scenario["expected"]
    if actual == expected:
        return Outcome(sid, source, "exact", "", [expected], [actual])
    if case.output_format in ("yaml", "json") and _same_data(expected, actual, case.output_format,
                                                             options):
        return Outcome(sid, source, "semantic", "", [expected], [actual])
    return Outcome(sid, source, "fail", "", [expected], [actual])


def _same_data(expected: str, actual: str, output_format: str, options: Options) -> bool:
    """Both texts hold the same data and the same comments (only quotes and spacing differ)."""
    try:
        if output_format == "json":
            return json.loads(expected) == json.loads(actual)
        if sorted(_COMMENT_RE.findall(expected)) != sorted(_COMMENT_RE.findall(actual)):
            return False
        decoder = YamlDecoder(options)
        exp = [to_python(d) for d in decoder.decode_documents(expected, process_leading=False)]
        act = [to_python(d) for d in decoder.decode_documents(actual, process_leading=False)]
        return exp == act
    except Exception:  # noqa: BLE001
        return False


def summarize_formats(outcomes: list[Outcome]) -> dict[str, Any]:
    """Counts and pass rate per format file plus the total."""

    def bucket(items: list[Outcome]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for o in items:
            counts[o.status] = counts.get(o.status, 0) + 1
        applicable = [o for o in items if o.status in ("exact", "semantic", "fail", "error")]
        passed = sum(1 for o in applicable if o.status in ("exact", "semantic"))
        return {
            "total": len(items),
            "counts": counts,
            "pass_rate": (passed / len(applicable)) if applicable else None,
        }

    result: dict[str, Any] = {"all": bucket(outcomes)}
    for name in FORMAT_FILES:
        result[name] = bucket([o for o in outcomes if o.source == f"{name}_test.go"])
    return result
