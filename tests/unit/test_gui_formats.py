"""GUI の Presenter が、追加した形式（XML・CSV/TSV・TOML・properties）をそのまま扱えること。
実際にウィンドウは開かない。形式は登録表から自動で選べるので、GUI 側の対応表は要らない。"""

from __future__ import annotations

import json

import pytest
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


class OpenAndRunTests:
    async def check(self, path: str, expected_format: str, extension: str) -> None:
        p = make_presenter()
        opened = await p.open_path(path)
        assert opened.ok, opened.error
        vm = await p.run()
        assert vm.ok, vm.error
        assert (vm.input_format, vm.output_format) == (expected_format, expected_format)
        assert vm.full_text.strip()
        assert p.default_save_name().endswith("." + extension), p.default_save_name()

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
        assert json.loads(vm.full_text) == {"shop": {"+@name": "s", "item": {
        "+content": "pen", "+@id": "1"}}}
        assert vm.output_format == "json"
        assert p.default_save_name() == "shop.json"

    async def test_the_schema_operator_runs_in_the_gui(self) -> None:
        p = make_presenter()
        await p.open_path("/w/items.csv")
        p.state.query.expression = "schema"
        p.state.query.output_format = "json"
        vm = await p.run()
        assert vm.ok, vm.error
        schema = json.loads(vm.full_text)
        assert schema["items"]["properties"]["price"] == {"type": "integer"}

    async def test_a_broken_file_is_reported_and_the_original_is_kept(self) -> None:
        for path in ("/w/broken.toml", "/w/broken.csv"):
            p = make_presenter()
            opened = await p.open_path(path)
            assert opened.ok
            vm = await p.run()
            assert not vm.ok
            assert vm.error.code == "format"
            assert p.state.document.original_text == FILES[path]


class AdoptedFormatsTests:
    """画面の見出しの横に出す「実際に採る形式」。auto でも指定でも同じ規則で決まる。"""

    async def test_no_document_means_no_format(self) -> None:
        assert make_presenter().adopted_formats() == ("", "")

    @pytest.mark.parametrize("path, expected", (("/w/shop.xml", "xml"), ("/w/items.csv", "csv"),
                           ("/w/items.tsv", "tsv"), ("/w/app.toml", "toml"),
                           ("/w/app.properties", "props")))
    async def test_auto_is_resolved_from_the_extension(self, path, expected) -> None:
        p = make_presenter()
        await p.open_path(path)
        assert p.adopted_formats() == (expected, expected)

    async def test_output_auto_follows_a_specified_input(self) -> None:
        p = make_presenter()
        await p.open_path("/w/shop.xml")
        p.state.query.input_format = "yaml"
        assert p.adopted_formats() == ("yaml", "yaml")

    async def test_a_specified_output_is_shown_as_it_is(self) -> None:
        p = make_presenter()
        await p.open_path("/w/shop.xml")
        p.state.query.output_format = "toon"
        assert p.adopted_formats() == ("xml", "toon")
        p.state.query.input_format = "xml"
        p.state.query.output_format = "json"
        assert p.adopted_formats() == ("xml", "json")

    async def test_pasted_text_is_yaml(self) -> None:
        p = make_presenter()
        p.open_text("a: 1\n")
        assert p.adopted_formats() == ("yaml", "yaml")

    async def test_it_does_not_need_a_successful_run(self) -> None:
        p = make_presenter()
        await p.open_path("/w/broken.toml")
        vm = await p.run()
        assert not vm.ok
        assert p.adopted_formats() == ("toml", "toml")

    @pytest.mark.parametrize("output", ("auto", "json", "yaml", "toon"))
    async def test_it_agrees_with_what_the_run_really_used(self, output) -> None:
        p = make_presenter()
        await p.open_path("/w/shop.xml")
        p.state.query.output_format = output
        vm = await p.run()
        assert p.adopted_formats() == (vm.input_format, vm.output_format)

    async def test_a_closed_document_has_none(self) -> None:
        p = make_presenter()
        await p.open_path("/w/shop.xml")
        p.close_document()
        assert p.adopted_formats() == ("", "")
