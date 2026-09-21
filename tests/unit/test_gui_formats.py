"""GUI の Presenter が、追加した形式（XML・CSV/TSV・TOML・properties）をそのまま扱えること。
実際にウィンドウは開かない。形式は登録表から自動で選べるので、GUI 側の対応表は要らない。"""

from __future__ import annotations

import json
import unittest

from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

FILES = {
    "/w/shop.xml": '<shop name="s"><item id="1">pen</item></shop>\n',
    "/w/items.csv": "name,price\npen,120\n",
    "/w/items.tsv": "name\tprice\npen\t120\n",
    "/w/app.toml": '[db]\nport = 5432\n',
    "/w/app.properties": "db.port = 5432\n",
    "/w/broken.toml": "a = \n",
    "/w/broken.csv": "a,b\n1\n",
}


def make_presenter() -> MainPresenter:
    fs = InMemoryFileSystem(dict(FILES))
    service = YqService(fs, StaticEnvironment({}))
    return MainPresenter(service=service, fs=fs, state=GuiState(),
                         size_of=lambda p: len(fs.files[p].encode("utf-8")))


class OpenAndRunTests(unittest.IsolatedAsyncioTestCase):
    async def check(self, path: str, expected_format: str, extension: str) -> None:
        p = make_presenter()
        opened = await p.open_path(path)
        self.assertTrue(opened.ok, opened.error)
        vm = await p.run()
        self.assertTrue(vm.ok, vm.error)
        self.assertEqual((vm.input_format, vm.output_format), (expected_format, expected_format))
        self.assertTrue(vm.full_text.strip())
        self.assertTrue(p.default_save_name().endswith("." + extension), p.default_save_name())

    async def test_each_format_is_detected_from_the_extension(self) -> None:
        await self.check("/w/shop.xml", "xml", "xml")
        await self.check("/w/items.csv", "csv", "csv")
        await self.check("/w/items.tsv", "tsv", "tsv")
        await self.check("/w/app.toml", "toml", "toml")
        await self.check("/w/app.properties", "props", "properties")

    async def test_the_output_format_can_be_changed(self) -> None:
        p = make_presenter()
        await p.open_path("/w/shop.xml")
        p.state.query.output_format = "json"
        vm = await p.run()
        self.assertEqual(json.loads(vm.full_text), {"shop": {"+@name": "s", "item": {
            "+content": "pen", "+@id": "1"}}})
        self.assertEqual(vm.output_format, "json")
        self.assertEqual(p.default_save_name(), "shop.json")

    async def test_the_schema_operator_runs_in_the_gui(self) -> None:
        p = make_presenter()
        await p.open_path("/w/items.csv")
        p.state.query.expression = "schema"
        p.state.query.output_format = "json"
        vm = await p.run()
        self.assertTrue(vm.ok, vm.error)
        schema = json.loads(vm.full_text)
        self.assertEqual(schema["items"]["properties"]["price"], {"type": "integer"})

    async def test_a_broken_file_is_reported_and_the_original_is_kept(self) -> None:
        for path in ("/w/broken.toml", "/w/broken.csv"):
            p = make_presenter()
            opened = await p.open_path(path)
            self.assertTrue(opened.ok)
            vm = await p.run()
            self.assertFalse(vm.ok)
            self.assertEqual(vm.error.code, "format")
            self.assertEqual(p.state.document.original_text, FILES[path])


if __name__ == "__main__":
    unittest.main()
