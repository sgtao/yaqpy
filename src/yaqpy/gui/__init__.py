"""Desktop GUI (Flet). Optional: install with ``pip install "yaqpy[gui]"``."""

from __future__ import annotations

__all__ = ["main_entry"]


def main_entry() -> int:
    """Re-export so that ``python -m yaqpy.gui`` style use also works."""
    from yaqpy.gui.app import main_entry as _main_entry

    return _main_entry()
