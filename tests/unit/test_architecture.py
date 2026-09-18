"""Dependency-direction and zero-dependency checks (design doc 4-2, 16-5)."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "yaqpy"

# module prefix -> prefixes it must not import
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "yaqpy.core.model": ("yaqpy.core.lang", "yaqpy.core.engine", "yaqpy.core.operators",
                        "yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.lang": ("yaqpy.core.engine", "yaqpy.core.operators", "yaqpy.formats", "yaqpy.app",
                       "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.engine": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.core.operators": ("yaqpy.formats", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.formats": ("yaqpy.core.engine", "yaqpy.app", "yaqpy.cli", "yaqpy.api"),
    "yaqpy.app": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web", "yaqpy.api"),
    "yaqpy.api": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web"),
    "yaqpy.cli": ("yaqpy.gui", "yaqpy.web"),
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
                    self.assertTrue(top == "yaqpy" or top in stdlib,
                                    f"{path.name} imports non-stdlib module {imported}")

    def test_no_removed_modules(self) -> None:
        removed = {"cgi", "cgitb", "pipes", "imp", "distutils", "asynchat", "asyncore", "smtpd"}
        for path in self.files:
            for imported in imports_of(path):
                self.assertNotIn(imported.split(".")[0], removed, f"{path.name} uses a removed module")


if __name__ == "__main__":
    unittest.main()
