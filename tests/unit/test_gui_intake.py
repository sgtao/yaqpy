"""取り込み口のテスト（GUI 設計書 6-1-3）。"""

from __future__ import annotations

import unittest

from yaqpy.app.ports import InMemoryFileSystem
from yaqpy.gui.intake import IntakeError, from_path, from_text

SAMPLE = "server:\n  port: 8080\n"
MB = 1024 * 1024


def _fs() -> InMemoryFileSystem:
    return InMemoryFileSystem({"/w/sample.yaml": SAMPLE, "/w/big.json": "x" * 4096})


def _size_of(fs: InMemoryFileSystem):
    return lambda path: len(fs.files[path].encode("utf-8"))


class FromPathTests(unittest.TestCase):
    def test_reads_a_file(self) -> None:
        fs = _fs()
        item = from_path(fs, "/w/sample.yaml", max_bytes=50 * MB, size_of=_size_of(fs))
        self.assertEqual(item.text, SAMPLE)
        self.assertEqual(item.name, "sample.yaml")
        self.assertEqual(item.path, "/w/sample.yaml")
        self.assertEqual(item.byte_size, len(SAMPLE.encode()))
        self.assertEqual(item.origin, "dialog")

    def test_missing_file_is_rejected(self) -> None:
        fs = _fs()
        with self.assertRaises(IntakeError):
            from_path(fs, "/w/nope.yaml", max_bytes=50 * MB, size_of=_size_of(fs))

    def test_directory_is_rejected(self) -> None:
        fs = _fs()                       # InMemoryFileSystem は登録外を「ファイルでない」とみなす
        with self.assertRaises(IntakeError) as ctx:
            from_path(fs, "/w", max_bytes=50 * MB, size_of=_size_of(fs))
        self.assertIn("フォルダ", str(ctx.exception))

    def test_too_large_is_rejected_before_reading(self) -> None:
        fs = _fs()
        calls: list[str] = []
        original = fs.read_text

        def spy(path: str) -> str:
            calls.append(path)
            return original(path)

        fs.read_text = spy          # type: ignore[method-assign]
        with self.assertRaises(IntakeError) as ctx:
            from_path(fs, "/w/big.json", max_bytes=1024, size_of=_size_of(fs))
        self.assertIn("大きすぎます", str(ctx.exception))
        self.assertEqual(calls, [], "上限超過のファイルは読んではいけない")

    def test_size_probe_failure_falls_back_to_reading(self) -> None:
        fs = _fs()

        def broken(path: str) -> int:
            raise OSError("cannot stat")

        item = from_path(fs, "/w/sample.yaml", max_bytes=50 * MB, size_of=broken)
        self.assertEqual(item.text, SAMPLE)


class FromTextTests(unittest.TestCase):
    def test_paste(self) -> None:
        item = from_text(SAMPLE)
        self.assertEqual(item.origin, "paste")
        self.assertEqual(item.name, "")
        self.assertIsNone(item.path)
        self.assertEqual(item.byte_size, len(SAMPLE.encode()))


if __name__ == "__main__":
    unittest.main()
