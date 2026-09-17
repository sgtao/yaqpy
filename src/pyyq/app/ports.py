"""Ports: the abstract I/O the application layer needs (design doc 11-2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pyyq.errors import SecurityError


class FileSystemPort(Protocol):
    def read_text(self, path: str) -> str: ...
    def read_stdin(self) -> str: ...
    def atomic_write(self, path: str, text: str) -> None: ...
    def exists_file(self, path: str) -> bool: ...


class EnvironmentPort(Protocol):
    def environ(self) -> Mapping[str, str]: ...


class SandboxFileSystem:
    """Refuses every file access (used by the API service)."""

    def read_text(self, path: str) -> str:
        raise SecurityError(f"file access is not allowed: {path}", capability="file")

    def read_stdin(self) -> str:
        raise SecurityError("stdin is not available", capability="file")

    def atomic_write(self, path: str, text: str) -> None:
        raise SecurityError(f"file access is not allowed: {path}", capability="file")

    def exists_file(self, path: str) -> bool:
        return False


class InMemoryFileSystem:
    """Test double."""

    def __init__(self, files: dict[str, str] | None = None, stdin: str = "") -> None:
        self.files = dict(files or {})
        self.stdin = stdin
        self.written: dict[str, str] = {}

    def read_text(self, path: str) -> str:
        try:
            return self.files[path]
        except KeyError:
            raise FileNotFoundError(path) from None

    def read_stdin(self) -> str:
        return self.stdin

    def atomic_write(self, path: str, text: str) -> None:
        self.files[path] = text
        self.written[path] = text

    def exists_file(self, path: str) -> bool:
        return path in self.files


class StaticEnvironment:
    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def environ(self) -> Mapping[str, str]:
        return self._values
