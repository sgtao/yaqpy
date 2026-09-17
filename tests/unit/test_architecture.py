"""Dependency-direction and zero-dependency checks (design doc 4-2, 16-5)."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pyyq"

# module prefix -> prefixes it must not import
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "pyyq.core.model": ("pyyq.core.lang", "pyyq.core.engine", "pyyq.core.operators",
                        "pyyq.formats", "pyyq.app", "pyyq.cli", "pyyq.api"),
    "pyyq.core.lang": ("pyyq.core.engine", "pyyq.core.operators", "pyyq.formats", "pyyq.app",
                       "pyyq.cli", "pyyq.api"),
    "pyyq.core.engine": ("pyyq.formats", "pyyq.app", "pyyq.cli", "pyyq.api"),
    "pyyq.core.operators": ("pyyq.formats", "pyyq.app", "pyyq.cli", "pyyq.api"),
    "pyyq.formats": ("pyyq.core.engine", "pyyq.app", "pyyq.cli", "pyyq.api"),
    "pyyq.app": ("pyyq.cli", "pyyq.gui", "pyyq.web", "pyyq.api"),
    "pyyq.api": ("pyyq.cli", "pyyq.gui", "pyyq.web"),
    "pyyq.cli": ("pyyq.gui", "pyyq.web"),
}


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


class ArchitectureTests(unittest.TestCase):
    files = sorted(SRC.rglob("*.py"))

    def test_dependency_direction(self) -> None:
        for path in self.files:
            module = module_name(path)
            for prefix, forbidden in FORBIDDEN.items():
                if not module.startswith(prefix):
                    continue
                for imported in imports_of(path):
                    for bad in forbidden:
                        with self.subTest(module=module, imported=imported):
                            self.assertFalse(imported == bad or imported.startswith(bad + "."),
                                             f"{module} must not import {imported}")

    def test_only_standard_library(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            for imported in imports_of(path):
                top = imported.split(".")[0]
                with self.subTest(file=path.name, imported=imported):
                    self.assertTrue(top == "pyyq" or top in stdlib,
                                    f"{path.name} imports non-stdlib module {imported}")

    def test_no_removed_modules(self) -> None:
        removed = {"cgi", "cgitb", "pipes", "imp", "distutils", "asynchat", "asyncore", "smtpd"}
        for path in self.files:
            for imported in imports_of(path):
                self.assertNotIn(imported.split(".")[0], removed, f"{path.name} uses a removed module")


if __name__ == "__main__":
    unittest.main()
