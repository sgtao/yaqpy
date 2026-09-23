"""Dependency-direction and zero-dependency checks (design doc 4-2, 16-5)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "yaqpy"

# module prefix -> prefixes it must not import
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "yaqpy.core.model": ("yaqpy.core.lang", "yaqpy.core.engine", "yaqpy.core.operators",
                        "yaqpy.formats", "yaqpy.recipes", "yaqpy.app", "yaqpy.cli", "yaqpy.gui",
                        "yaqpy.api"),
    "yaqpy.core.lang": ("yaqpy.core.engine", "yaqpy.core.operators", "yaqpy.formats", "yaqpy.recipes",
                       "yaqpy.app", "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.core.engine": ("yaqpy.formats", "yaqpy.recipes", "yaqpy.app", "yaqpy.cli", "yaqpy.gui",
                         "yaqpy.api"),
    "yaqpy.core.operators": ("yaqpy.formats", "yaqpy.recipes", "yaqpy.app", "yaqpy.cli", "yaqpy.gui",
                            "yaqpy.api"),
    "yaqpy.formats": ("yaqpy.core.engine", "yaqpy.recipes", "yaqpy.app", "yaqpy.cli", "yaqpy.gui",
                     "yaqpy.api"),
    # recipes: data + checks on plain Python values. It reads formats (the YAML metadata), never the
    # engine, and knows nothing of the application layer that runs a recipe.
    "yaqpy.recipes": ("yaqpy.core.engine", "yaqpy.core.operators", "yaqpy.core.lang", "yaqpy.app",
                     "yaqpy.cli", "yaqpy.gui", "yaqpy.api"),
    "yaqpy.app": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web", "yaqpy.api"),
    "yaqpy.api": ("yaqpy.cli", "yaqpy.gui", "yaqpy.web"),
    "yaqpy.cli": ("yaqpy.gui", "yaqpy.web"),
}

GUI_PREFIX = "yaqpy.gui"
# gui が使ってよい外部パッケージ（G0 でドロップ拡張は見送りになったが、将来の再検討に備えて残す）。
# uvicorn は Web 版（[web] extra の flet-web が連れてくる）のサーバーを起動する gui/_web.py だけ。
GUI_ALLOWED_THIRD_PARTY = {"flet", "flet_dropzone", "flet_web", "uvicorn"}
GUI_UVICORN_MODULES = {"yaqpy.gui._web"}
# View から切り離してテストするため、flet を import してはいけないモジュール
GUI_FLET_FREE_MODULES = {
    "yaqpy.gui.presenter",
    "yaqpy.gui.state",
    "yaqpy.gui.paths",
    "yaqpy.gui.intake",
    "yaqpy.gui.errors_ja",
    "yaqpy.gui.texts",
    "yaqpy.gui._di",
    "yaqpy.gui.web_config",
    "yaqpy.gui.logo",
    "yaqpy.gui.web_assets",
    "yaqpy.gui.ask_ai",
    "yaqpy.gui.app",
}


# 例外：`yaqpy --gui` のためだけに、cli/main.py は gui を（関数の中で遅延して）import してよい。
# 「遅延している」ことは test_cli_reaches_gui_only_lazily が別途検査する。
ALLOWED_EXCEPTIONS: set[tuple[str, str]] = {("yaqpy.cli.main", "yaqpy.gui")}


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


class ArchitectureTests:
    files = sorted(SRC.rglob("*.py"))

    def test_dependency_direction(self) -> None:
        for path in self.files:
            module = module_name(path)
            for prefix, forbidden in FORBIDDEN.items():
                if not module.startswith(prefix):
                    continue
                for imported in imports_of(path):
                    for bad in forbidden:
                        if (module, bad) in ALLOWED_EXCEPTIONS:
                            continue
                        assert not (imported == bad or imported.startswith(bad + ".")), f"{module} must not import {imported}"

    def test_only_standard_library(self) -> None:
        """gui/ 以外は実行時依存ゼロ（README の約束）。"""
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            if module_name(path).startswith(GUI_PREFIX):
                continue                      # gui は flet を使ってよい（下の 2 つで別途検査）
            for imported in imports_of(path):
                top = imported.split(".")[0]
                assert top == "yaqpy" or top in stdlib, f"{path.name} imports non-stdlib module {imported}"

    def test_gui_third_party_whitelist(self) -> None:
        """gui/ が使ってよい外部パッケージは flet 系だけ。"""
        stdlib = set(sys.stdlib_module_names)
        for path in self.files:
            module = module_name(path)
            if not module.startswith(GUI_PREFIX):
                continue
            for imported in imports_of(path):
                top = imported.split(".")[0]
                assert top == "yaqpy" or top in stdlib or top in GUI_ALLOWED_THIRD_PARTY, f"{module} imports unexpected third-party module {imported}"

    def test_only_the_web_runner_uses_uvicorn(self) -> None:
        """デスクトップ版（[gui] extra）は uvicorn 無しで動くこと（v0.6.0）。"""
        for path in self.files:
            module = module_name(path)
            if module in GUI_UVICORN_MODULES:
                continue
            for imported in imports_of(path):
                assert imported.split(".")[0] != "uvicorn", f"{module} must not import uvicorn"

    def test_gui_logic_stays_flet_free(self) -> None:
        """Presenter 層は flet 抜きで単体テストできること（設計書 G-NFR-05）。"""
        for path in self.files:
            module = module_name(path)
            if module not in GUI_FLET_FREE_MODULES:
                continue
            for imported in imports_of(path):
                assert imported.split(".")[0] != "flet", f"{module} must not import flet"

    def test_cli_reaches_gui_only_lazily(self) -> None:
        """cli/main.py の gui import は関数の中だけ。モジュール先頭にあると、
        flet 未導入の環境や CLI 単体の起動が gui の import 副作用に巻き込まれる。"""
        tree = ast.parse((SRC / "cli" / "main.py").read_text(encoding="utf-8"))
        for node in tree.body:                      # 先頭（トップレベル）の文だけを見る
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                assert not (name == "yaqpy.gui" or name.startswith("yaqpy.gui.")), "cli/main.py must import yaqpy.gui lazily (inside a function)"

    def test_no_removed_modules(self) -> None:
        removed = {"cgi", "cgitb", "pipes", "imp", "distutils", "asynchat", "asyncore", "smtpd"}
        for path in self.files:
            for imported in imports_of(path):
                assert imported.split(".")[0] not in removed, f"{path.name} uses a removed module"
