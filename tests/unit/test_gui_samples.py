"""GUI の［サンプル］（v0.7.2）：examples/ のコピーが原本と同じことと、開き方。

パッケージ内のサンプルは、リポジトリの examples/（原本）のコピー。wheel に入れるため。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui import samples, texts
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState

ORIGINALS = Path(__file__).resolve().parents[2] / "examples"


class PackagedCopyTests:
    def test_the_packaged_samples_are_exactly_the_files_of_examples(self) -> None:
        """examples/ に足した・直したものは、assets/examples/ にも同じに写す（忘れるとここで落ちる）。"""
        original = sorted(p.name for p in ORIGINALS.iterdir() if p.is_file())
        assert samples.list_samples() == original

    def test_each_copy_has_the_same_content(self) -> None:
        for name in samples.list_samples():
            assert samples.read_sample(name) == (ORIGINALS / name).read_bytes(), name

    def test_the_folder_is_inside_the_package(self) -> None:
        assert samples.SAMPLES_DIR.parent == Path(samples.__file__).resolve().parent / "assets"

    def test_the_api_request_bodies_are_among_them(self) -> None:
        names = samples.list_samples()
        assert {"api-openai-request.json", "api-gemini-request.json",
                "api-anthropic-request.json", "sample.yaml"} <= set(names)


class ReadSampleTests:
    @pytest.mark.parametrize("name", ["nope.yaml", "../sample.yaml", "..\\sample.yaml",
                                      "/etc/passwd", "", "assets/examples/sample.yaml"])
    def test_only_a_listed_name_is_read_never_a_path(self, name: str) -> None:
        with pytest.raises(ValueError):
            samples.read_sample(name)

    def test_no_samples_when_the_folder_is_missing(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(samples, "SAMPLES_DIR", tmp_path / "missing")
        assert samples.list_samples() == []


def make_presenter():
    fs = InMemoryFileSystem({})
    state = GuiState()
    return MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=state,
                         size_of=lambda p: 0), state


class OpenSampleTests:
    async def test_the_first_sample_becomes_the_document(self) -> None:
        presenter, state = make_presenter()
        vm = await presenter.open_sample("sample.yaml")
        assert vm.ok and vm.name == "sample.yaml" and vm.path is None
        assert [d.name for d in state.documents] == ["sample.yaml"]
        assert "server:" in state.documents[0].original_text

    async def test_a_second_sample_is_added_not_replacing(self) -> None:
        presenter, state = make_presenter()
        await presenter.open_sample("sample.yaml")
        await presenter.open_sample("api-gemini-request.json")
        assert [d.name for d in state.documents] == ["sample.yaml", "api-gemini-request.json"]
        assert state.active_index == 1

    async def test_the_input_format_is_set_to_auto(self) -> None:
        presenter, state = make_presenter()
        state.query.input_format = "yaml"
        await presenter.open_sample("sample.json")
        assert state.query.input_format == "auto"

    async def test_an_unknown_name_is_an_error_and_changes_nothing(self) -> None:
        presenter, state = make_presenter()
        state.query.input_format = "json"
        vm = await presenter.open_sample("../sample.yaml")
        assert not vm.ok and vm.error.message == texts.ERR_SAMPLE_NOT_FOUND
        assert state.documents == [] and state.query.input_format == "json"


def make_page():
    from yaqpy.gui.pages.main_page import MainPage

    presenter, state = make_presenter()
    page = MainPage(page=mock.MagicMock(), presenter=presenter, state=state, picker=mock.MagicMock())
    return page, state


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class SamplesMenuTests:
    def test_the_menu_lists_every_sample_by_file_name(self) -> None:
        page, _ = make_page()
        assert [item.content for item in page._samples_menu.items] == samples.list_samples()

    def test_the_button_sits_next_to_the_add_file_button(self) -> None:
        page, _ = make_page()
        row = page._build().controls[0]
        assert row.controls[1] is page._add_file_button
        assert row.controls[2] is page._samples_menu

    async def test_choosing_a_sample_opens_it_and_runs(self) -> None:
        page, state = make_page()
        await page._on_open_sample("sample.yaml")
        assert [d.name for d in state.documents] == ["sample.yaml"]
        assert page._original.value == state.documents[0].original_text
        assert page._run_button.disabled is False
        assert page._converted.value            # `.` を実行した結果が出ている

    async def test_the_input_format_dropdown_goes_back_to_auto(self) -> None:
        page, state = make_page()
        state.query.input_format = "xml"
        page._input_dd.value = "xml"
        await page._on_open_sample("api-openai-request.json")
        assert page._input_dd.value == "auto"
        assert page._original_format.value == "json"

    async def test_a_sample_is_added_when_a_document_is_already_open(self) -> None:
        page, state = make_page()
        await page._on_open_sample("sample.yaml")
        await page._on_open_sample("sample.toml")
        assert [d.name for d in state.documents] == ["sample.yaml", "sample.toml"]

    async def test_a_menu_item_starts_the_open_task(self) -> None:
        page, _ = make_page()
        page._samples_menu.items[0].on_click(mock.MagicMock())
        page._page.run_task.assert_called_once_with(page._on_open_sample, samples.list_samples()[0])
