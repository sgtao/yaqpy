"""Extract ``expressionScenario{...}`` and ``formatScenario{...}`` literals from the Go yq test files.

Usage:
    python tools/extract_go_scenarios.py <path/to/yq/pkg/yqlib> <tests/golden/operators> [<tests/golden/formats>]

The operator scenarios (``expressionScenario``) go to the first output directory. When the
optional second directory is given, the format scenarios (``formatScenario`` of the XML, CSV/TSV,
TOML and properties tests, see ``FORMAT_TEST_FILES``) are written there as well.

Standard library only. The Go source is tokenised just enough to recover
struct literals, string literals (raw and interpreted), string concatenation
and file-level ``var x = "..."`` (format tests: also ``const``) declarations that scenarios reference.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ----------------------------------------------------------------------------- tokenizer

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<line_comment>//[^\n]*)
  | (?P<block_comment>/\*.*?\*/)
  | (?P<raw>`[^`]*`)
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<char>'(?:[^'\\\n]|\\.)*')
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<number>[0-9][0-9A-Za-z_.]*)
  | (?P<punct>\[\]|[{}()\[\],:+=.;&*!<>/%-])
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(slots=True)
class Tok:
    kind: str
    text: str
    pos: int


def tokenize(source: str) -> list[Tok]:
    out: list[Tok] = []
    pos = 0
    n = len(source)
    while pos < n:
        m = _TOKEN_RE.match(source, pos)
        if m is None:
            pos += 1
            continue
        kind = m.lastgroup or ""
        if kind not in ("ws", "line_comment", "block_comment"):
            out.append(Tok(kind, m.group(0), pos))
        pos = m.end()
    return out


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'", "a": "\a", "b": "\b",
            "f": "\f", "v": "\v", "0": "\0"}


def decode_go_string(tok: Tok) -> str:
    text = tok.text
    if tok.kind == "raw":
        return text[1:-1]
    body = text[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        elif nxt == "x":
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        elif nxt == "u":
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
        elif nxt == "U":
            out.append(chr(int(body[i + 2:i + 10], 16)))
            i += 10
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


# ----------------------------------------------------------------------------- value parsing

class Unresolved(Exception):
    pass


@dataclass(frozen=True)
class ScenarioSchema:
    """Which Go struct to look for, its Go field names -> JSON keys, and the JSON defaults."""

    type_name: str
    fields: dict[str, str]
    defaults: dict[str, Any]
    doc_only: frozenset[str] = frozenset()    # Go fields that only feed the generated docs


EXPRESSION_SCHEMA = ScenarioSchema(
    "expressionScenario",
    {
        "description": "description", "document": "document", "document2": "document2",
        "expression": "expression", "expected": "expected", "expectedError": "expected_error",
        "skipDoc": "skip_doc", "environmentVariables": "environment",
        "requiresFormat": "requires_format",
    },
    {
        "description": "", "document": "", "document2": "", "expression": "", "expected": [],
        "expected_error": "", "skip_doc": False, "environment": {}, "requires_format": "",
    },
)

FORMAT_SCHEMA = ScenarioSchema(
    "formatScenario",
    {
        "input": "input", "indent": "indent", "expression": "expression", "expected": "expected",
        "description": "description", "subdescription": "subdescription", "skipDoc": "skip_doc",
        "scenarioType": "scenario_type", "expectedError": "expected_error",
    },
    {
        "input": "", "indent": 0, "expression": "", "expected": "", "description": "",
        "subdescription": "", "skip_doc": False, "scenario_type": "", "expected_error": "",
    },
    frozenset({"subdescription"}),
)

# Format tests whose scenarios are extracted (design: v0.2.0 F0). Other formats (INI, HCL, Lua ...)
# are out of scope for now.
FORMAT_TEST_FILES = ("xml_test.go", "csv_test.go", "toml_test.go", "properties_test.go")


@dataclass
class Extractor:
    tokens: list[Tok]
    variables: dict[str, str] = field(default_factory=dict)
    declarations: tuple[str, ...] = ("var",)

    def collect_variables(self) -> None:
        """``var name = "..."`` (and ``const`` when enabled) at any depth (strings only)."""
        toks = self.tokens
        for i, tok in enumerate(toks):
            if tok.kind == "ident" and tok.text in self.declarations and i + 2 < len(toks) \
                    and toks[i + 1].kind == "ident" and toks[i + 2].text == "=":
                try:
                    value, _ = self.parse_string_expr(i + 3)
                except Unresolved:
                    continue
                self.variables[toks[i + 1].text] = value

    def parse_string_expr(self, i: int) -> tuple[str, int]:
        """Parse ``"a" + b + `c```. Returns (value, next index)."""
        parts: list[str] = []
        toks = self.tokens
        while True:
            tok = toks[i]
            if tok.kind in ("raw", "str"):
                parts.append(decode_go_string(tok))
                i += 1
            elif tok.kind == "ident":
                if tok.text in self.variables:
                    parts.append(self.variables[tok.text])
                    i += 1
                else:
                    raise Unresolved(f"identifier {tok.text}")
            else:
                raise Unresolved(f"unexpected token {tok.text}")
            if i < len(toks) and toks[i].text == "+":
                i += 1
                continue
            return "".join(parts), i

    def parse_value(self, i: int) -> tuple[Any, int]:
        toks = self.tokens
        tok = toks[i]
        if tok.kind in ("raw", "str") or (tok.kind == "ident" and tok.text in self.variables):
            return self.parse_string_expr(i)
        if tok.kind == "ident" and tok.text in ("true", "false"):
            return tok.text == "true", i + 1
        if tok.kind == "number" and tok.text.isdigit():
            return int(tok.text), i + 1
        if tok.text == "[]" and toks[i + 1].text == "string" and toks[i + 2].text == "{":
            i += 3
            items: list[str] = []
            while toks[i].text != "}":
                value, i = self.parse_string_expr(i)
                items.append(value)
                if toks[i].text == ",":
                    i += 1
            return items, i + 1
        if tok.kind == "ident" and tok.text == "map" and toks[i + 1].text == "[":
            # map[string]string{ "k": "v", ... }
            j = i
            while toks[j].text != "{":
                j += 1
            j += 1
            mapping: dict[str, str] = {}
            while toks[j].text != "}":
                key, j = self.parse_string_expr(j)
                assert toks[j].text == ":"
                value, j = self.parse_string_expr(j + 1)
                mapping[key] = value
                if toks[j].text == ",":
                    j += 1
            return mapping, j + 1
        raise Unresolved(f"unsupported value starting with {tok.text!r}")

    def skip_value(self, i: int) -> int:
        """Skip a value we cannot interpret (balanced braces)."""
        toks = self.tokens
        depth = 0
        while i < len(toks):
            t = toks[i].text
            if t in ("{", "(", "["):
                depth += 1
            elif t in ("}", ")", "]"):
                if depth == 0:
                    return i
                depth -= 1
            elif t == "," and depth == 0:
                return i
            i += 1
        return i

    def extract(self, source_name: str,
                schema: ScenarioSchema = EXPRESSION_SCHEMA) -> list[dict[str, Any]]:
        type_name = schema.type_name
        toks = self.tokens
        scenarios: list[dict[str, Any]] = []
        i = 0
        while i < len(toks) - 1:
            if (toks[i].text == "[]" and toks[i + 1].kind == "ident"
                    and toks[i + 1].text == type_name and toks[i + 2].text == "{"):
                # var NAME = []<type>{ {...}, {...}, <type>{...} }
                group = ""
                if i >= 2 and toks[i - 1].text == "=" and toks[i - 2].kind == "ident":
                    group = toks[i - 2].text
                i += 3
                while i < len(toks) and toks[i].text != "}":
                    if toks[i].text == "{":
                        scenario, i = self.parse_scenario(i + 1, source_name, schema)
                        scenario["group"] = group
                        scenarios.append(scenario)
                    elif toks[i].kind == "ident" and toks[i].text == type_name \
                            and toks[i + 1].text == "{":
                        scenario, i = self.parse_scenario(i + 2, source_name, schema)
                        scenario["group"] = group
                        scenarios.append(scenario)
                    else:
                        i += 1
                i += 1
            elif toks[i].kind == "ident" and toks[i].text == type_name and toks[i + 1].text == "{":
                scenario, i = self.parse_scenario(i + 2, source_name, schema)
                scenarios.append(scenario)
            else:
                i += 1
        return scenarios

    def parse_scenario(self, i: int, source_name: str,
                       schema: ScenarioSchema = EXPRESSION_SCHEMA) -> tuple[dict[str, Any], int]:
        toks = self.tokens
        scenario: dict[str, Any] = {"source": source_name, **schema.defaults,
                                    "unresolved": [], "group": ""}
        while toks[i].text != "}":
            if toks[i].kind != "ident" or toks[i + 1].text != ":":
                i += 1
                continue
            name = toks[i].text
            try:
                value, i = self.parse_value(i + 2)
            except Unresolved as e:
                if name not in schema.doc_only:
                    scenario["unresolved"].append(f"{name}: {e}")
                i = self.skip_value(i + 2)
                if toks[i].text == ",":
                    i += 1
                continue
            key = schema.fields.get(name)
            if key is not None:
                scenario[key] = value
            if toks[i].text == ",":
                i += 1
        return scenario, i + 1


def extract_file(path: Path, variables: dict[str, str] | None = None,
                 schema: ScenarioSchema = EXPRESSION_SCHEMA,
                 declarations: tuple[str, ...] = ("var",)) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    ex = Extractor(tokenize(source), dict(variables or {}), declarations)
    ex.collect_variables()
    return ex.extract(path.name, schema)


def collect_package_variables(src_dir: Path,
                              declarations: tuple[str, ...] = ("var",)) -> dict[str, str]:
    """Go package-level string variables are visible from every file of the package."""
    variables: dict[str, str] = {}
    for path in sorted(src_dir.glob("*_test.go")):
        ex = Extractor(tokenize(path.read_text(encoding="utf-8")), variables, declarations)
        ex.collect_variables()
        variables.update(ex.variables)
    return variables


def write_scenarios(src_dir: Path, out_dir: Path, schema: ScenarioSchema,
                    declarations: tuple[str, ...],
                    only: tuple[str, ...] | None = None) -> tuple[int, int, int]:
    """Extract every (or only the listed) ``*_test.go`` into ``out_dir``.

    Returns (scenario count, unresolved count, file count).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    unresolved_total = 0
    manifest: dict[str, Any] = {}
    variables = collect_package_variables(src_dir, declarations)
    for path in sorted(src_dir.glob("*_test.go")):
        if only is not None and path.name not in only:
            continue
        scenarios = extract_file(path, variables, schema, declarations)
        if not scenarios:
            continue
        name = path.name[:-len("_test.go")]
        for index, s in enumerate(scenarios):
            s["id"] = f"{name}#{index}"
        unresolved = sum(1 for s in scenarios if s["unresolved"])
        total += len(scenarios)
        unresolved_total += unresolved
        (out_dir / f"{name}.json").write_text(
            json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest[name] = {"count": len(scenarios), "unresolved": unresolved}
    (out_dir / "extracted.json").write_text(
        json.dumps({"total": total, "unresolved": unresolved_total, "files": manifest},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return total, unresolved_total, len(manifest)


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    src_dir = Path(argv[1])
    total, unresolved, files = write_scenarios(src_dir, Path(argv[2]), EXPRESSION_SCHEMA, ("var",))
    print(f"extracted {total} scenarios from {files} files ({unresolved} with unresolved fields)")
    if len(argv) == 4:
        total, unresolved, files = write_scenarios(src_dir, Path(argv[3]), FORMAT_SCHEMA,
                                                   ("var", "const"), FORMAT_TEST_FILES)
        print(f"extracted {total} format scenarios from {files} files "
              f"({unresolved} with unresolved fields)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
