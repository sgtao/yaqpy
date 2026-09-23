"""yaqpy のロゴ（v0.6.0 の要望：GUI と Web のアイコンに assets/images のロゴを使う）。

パッケージ内のロゴは、リポジトリの assets/images（原本）のコピー。内容が同じことを確かめる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yaqpy.gui import logo

ORIGINALS = Path(__file__).resolve().parents[2] / "assets" / "images"


@pytest.mark.parametrize("copy, original", [
    (logo.WINDOW_ICON, "yaqpy-logo.ico"),
    (logo.FAVICON, "yaqpy-logo.png"),
    (logo.LOADING_IMAGE, "yaqpy-logo.png"),
])
def test_packaged_logos_are_copies_of_the_originals(copy: Path, original: str) -> None:
    assert copy.is_file()
    assert copy.read_bytes() == (ORIGINALS / original).read_bytes()


def test_the_window_icon_is_an_ico() -> None:
    """Flet 1.0 の page.window.icon は .ico を求める（Windows でだけ効く）。"""
    assert logo.WINDOW_ICON.suffix == ".ico"
    assert logo.WINDOW_ICON.read_bytes()[:4] == b"\x00\x00\x01\x00"      # ICO のヘッダ


def test_the_web_assets_are_inside_the_package() -> None:
    """wheel に入る場所（src/yaqpy/gui/assets）にあること。"""
    assert logo.WEB_ASSETS_DIR.parent == Path(logo.__file__).resolve().parent / "assets"
