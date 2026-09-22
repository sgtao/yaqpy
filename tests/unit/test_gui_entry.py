"""起動ガードのテスト（手動テスト M8 の自動化）。"""

from __future__ import annotations

import io
from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from yaqpy.gui import app


class EntryGuardTests:
    def test_missing_flet_gives_an_install_hint(self) -> None:
        err = io.StringIO()
        with mock.patch.object(app, "flet_available", return_value=False):
            code = app.main_entry(stderr=err)
        assert code == 1
        assert 'pip install "flet>=1.0,<2"' in err.getvalue()
        assert "uv sync --extra gui" in err.getvalue()
        assert "https://github.com/sgtao/yaqpy" in err.getvalue()   # リリースからの導入案内

    @pytest.mark.skipif(ft is None, reason="flet is not installed")
    def test_initial_path_reaches_run_app(self) -> None:
        """``yaqpy --gui a.yaml`` の a.yaml が run_app まで届くこと（U2）。"""
        with mock.patch("yaqpy.gui._run.run_app") as run_app:
            code = app.main_entry(initial_path="/w/a.yaml")
        assert code == 0
        run_app.assert_called_once_with(initial_path="/w/a.yaml")

    def test_app_module_imports_without_flet(self) -> None:
        """app.py が import 時点で flet を要求しないこと。"""
        import ast
        import pathlib

        source = pathlib.Path(app.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports: list[str] = []
        for node in tree.body:               # 関数の中の import は対象外
            if isinstance(node, ast.Import):
                top_level_imports += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.append(node.module)
        assert "flet" not in [m.split(".")[0] for m in top_level_imports]
