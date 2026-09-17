"""Local implementations of the ports (pathlib / os.environ)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path


class LocalFileSystem:
    def read_text(self, path: str) -> str:
        data = Path(path).read_bytes()
        return data.decode("utf-8-sig")

    def read_stdin(self) -> str:
        data = sys.stdin.buffer.read()
        return data.decode("utf-8-sig")

    def atomic_write(self, path: str, text: str) -> None:
        target = Path(path)
        directory = target.parent if str(target.parent) else Path(".")
        fd, tmp_name = tempfile.mkstemp(prefix=".pyyq-", suffix=".tmp", dir=str(directory))
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            if target.exists():
                try:
                    shutil.copymode(str(target), str(tmp))
                except OSError:
                    pass
            os.replace(str(tmp), str(target))
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def exists_file(self, path: str) -> bool:
        p = Path(path)
        return p.exists() and not p.is_dir()


class LocalEnvironment:
    def environ(self) -> Mapping[str, str]:
        return os.environ
