"""Web 版のドラッグ＆ドロップ用の静的ファイル（gui/web_assets.py。v0.7.0）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from yaqpy.gui import logo, web_assets

INDEX = """<!DOCTYPE html>
<html>
<head><base href="$FLUTTER_BASE_HREF"><!-- fletAppConfig --></head>
<body>
  <script src="flutter_bootstrap.js" async></script>
</body>
</html>
"""


class TestAddDropScript:
    def test_adds_the_tag_just_before_the_body_end(self) -> None:
        out = web_assets.add_drop_script(INDEX)
        assert out.index(web_assets.DROP_SCRIPT_TAG) < out.rindex("</body>")
        assert out.index("flutter_bootstrap.js") < out.index(web_assets.DROP_SCRIPT_TAG)
        assert "<!-- fletAppConfig -->" in out            # Flet が差し込む目印は残す

    def test_is_idempotent(self) -> None:
        once = web_assets.add_drop_script(INDEX)
        assert web_assets.add_drop_script(once) == once

    def test_refuses_an_index_without_body_end(self) -> None:
        with pytest.raises(ValueError):
            web_assets.add_drop_script("<html></html>")


class TestBuildAssetsDir:
    def test_contains_logo_script_and_patched_index(self, tmp_path: Path) -> None:
        index = tmp_path / "flet-index.html"
        index.write_text(INDEX, encoding="utf-8")
        dest = web_assets.build_assets_dir(tmp_path / "assets", flet_index=index)
        assert (dest / "favicon.png").read_bytes() == logo.FAVICON.read_bytes()
        assert (dest / "icons" / "loading-animation.png").is_file()
        assert (dest / web_assets.DROP_SCRIPT_NAME).is_file()
        assert web_assets.DROP_SCRIPT_TAG in (dest / "index.html").read_text(encoding="utf-8")

    def test_the_real_flet_index_can_be_patched(self, tmp_path: Path) -> None:
        """Flet の同梱の index.html に、足す場所と差し込みの目印があること（Flet の更新の検知）。"""
        spec = importlib.util.find_spec("flet_web")
        if spec is None or spec.origin is None:
            pytest.skip("the web extra (flet-web) is not installed")
        flet_index = Path(spec.origin).parent / "web" / "index.html"
        dest = web_assets.build_assets_dir(tmp_path / "assets", flet_index=flet_index)
        html = (dest / "index.html").read_text(encoding="utf-8")
        assert web_assets.DROP_SCRIPT_TAG in html
        assert "<!-- fletAppConfig -->" in html


class TestDropScript:
    def test_the_route_name_matches_the_python_side(self) -> None:
        source = (logo.WEB_ASSETS_DIR / web_assets.DROP_SCRIPT_NAME).read_text(encoding="utf-8")
        assert f'var DROP_ROUTE = "{web_assets.DROP_ROUTE}";' in source


class TestIsDropRoute:
    @pytest.mark.parametrize("route", ["/__yaqpy_drop", "__yaqpy_drop", "/app/__yaqpy_drop/"])
    def test_recognizes_the_notification(self, route: str) -> None:
        assert web_assets.is_drop_route(route)

    @pytest.mark.parametrize("route", ["/", "", None, "/store", "/__yaqpy_drop/x"])
    def test_ignores_other_routes(self, route: str | None) -> None:
        assert not web_assets.is_drop_route(route)
