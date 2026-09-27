"""GUI の［サンプル］メニューに出す入力データ（v0.7.2）。Flet 非依存。

原本はリポジトリの ``examples/``。wheel に入れるため、そのままこのパッケージの
``assets/examples/`` にコピーしている（内容が原本と同じことは ``tests/unit/test_gui_samples.py``
が確かめる。``examples/`` を直したら、コピーも同じに直す）。

メニューに出す名前は、コピーの置き場にあるファイル名そのもの（並びは名前順）。読み込むときは
その一覧にある名前だけを受け付け、パスは受け付けない。
"""

from __future__ import annotations

from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "assets" / "examples"


def list_samples() -> list[str]:
    """メニューに出すサンプルのファイル名（名前順）。置き場が無ければ空。"""
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(p.name for p in SAMPLES_DIR.iterdir() if p.is_file())


def read_sample(name: str) -> bytes:
    """サンプル 1 件の中身。一覧にない名前（パスを含む）は ``ValueError``。"""
    if name not in list_samples():
        raise ValueError(f"unknown sample: {name!r}")
    return (SAMPLES_DIR / name).read_bytes()
