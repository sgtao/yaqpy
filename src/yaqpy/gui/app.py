"""``yaqpy-gui`` のエントリポイント。

**このモジュールは flet 未導入でも import できること。**
flet に触れるのは ``yaqpy.gui._run`` 側だけにして、導入案内を出せるようにする。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import TextIO

from yaqpy.gui import texts


def flet_available() -> bool:
    return importlib.util.find_spec("flet") is not None


def main_entry(*, stderr: TextIO | None = None) -> int:
    err = stderr or sys.stderr
    if not flet_available():
        err.write(texts.INSTALL_HINT)
        return 1
    from yaqpy.gui._run import run_app

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main_entry())
