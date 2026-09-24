"""Real conversions of the files in ``examples/`` (a smoke test for every supported Python).

The expected outputs were taken from a run on Python 3.13 and checked by hand. Because the same
tests run on 3.11, 3.12 and 3.13 (see "Supported Pythons" in DEVELOPMENT.md), a difference in
the standard library between those versions shows up here as a plain diff.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def yq(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "yaqpy", *args], capture_output=True, text=True,
        encoding="utf-8", env=ENV, cwd=EXAMPLES, timeout=120,
    )


CASES = [
    pytest.param(("sample.yaml", ".server.port"), "8080\n", id="yaml-value"),
    pytest.param(("sample.yaml", ".backup.enabled"), "true\n", id="yaml-merge-key-alias"),
    pytest.param(("sample.yaml", ".items[].name"), "pen\nbook\n", id="yaml-each"),
    pytest.param(("sample.yaml", "-o=json", ".server.hosts"), '[\n  "a",\n  "b"\n]\n', id="yaml-to-json"),
    pytest.param(
        ("sample.yaml", ".server.port = 9090"),
        (EXAMPLES / "sample.yaml").read_text(encoding="utf-8").replace("port: 8080", "port: 9090"),
        id="yaml-update-keeps-comments",
    ),
    pytest.param(("sample.yaml", "-o=toon", ".items"), "[2]{name,price}:\n  pen,120\n  book,980\n", id="yaml-to-toon"),
    pytest.param(
        ("sample.json", "-o=json", "-I0", "."),
        '{"name":"yaqpy","version":"0.1.0","tags":["yaml","json","cli"],"nested":{"ok":true,"ratio":1.50}}\n',
        id="json-compact-keeps-1.50",
    ),
    pytest.param(("sample.json", "-o=yaml", ".tags"), "- yaml\n- json\n- cli\n", id="json-to-yaml"),
    pytest.param(
        ("sample.csv", "-p=csv", "-o=json", ".[2]"),
        '{\n  "name": "note, A4",\n  "price": 250,\n  "in_stock": true\n}\n',
        id="csv-quoted-comma",
    ),
    pytest.param(("sample.xml", "-p=xml", "-o=json", ".shop.item[].name"), '"pen"\n"book"\n', id="xml-to-json"),
    pytest.param(("sample.xml", "-p=xml", "-o=yaml", ".shop.item[0].price"), "120\n", id="xml-value"),
    pytest.param(
        ("sample.properties", "-p=props", "-o=json", ".db"),
        '{\n  "host": "localhost",\n  "port": "5432"\n}\n',
        id="properties-to-json",
    ),
    pytest.param(("sample.toml", "-p=toml", "-o=toml", ".tool.build.mask"), "0xFF\n", id="toml-keeps-hex"),
    pytest.param(("sample.toml", "-p=toml", "-o=json", ".tool.hooks[].name"), '"lint"\n"test"\n', id="toml-array-of-tables"),
]


@pytest.mark.parametrize(("args", "expected"), CASES)
def test_example_conversion(args: tuple[str, ...], expected: str) -> None:
    file, *rest = args
    r = yq(*rest, file)
    assert (r.returncode, r.stdout) == (0, expected), r.stderr


def test_schema_of_json_example() -> None:
    r = yq("--schema", "sample.json")
    assert r.returncode == 0, r.stderr
    schema = json.loads(r.stdout)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    assert schema["properties"]["nested"]["properties"]["ratio"] == {"type": "number"}


def test_recipe_openai_to_anthropic() -> None:
    r = yq("--recipe", "openai-to-anthropic", "openai-request.json")
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["system"] == [{"type": "text", "text": "You are a weather assistant."}]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert "dropped .model" in r.stderr  # the report goes to stderr
