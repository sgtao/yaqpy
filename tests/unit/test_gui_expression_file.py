"""式のファイル（``.yaqpy``）の保存・読み込み（v0.7.0）。"""

from __future__ import annotations

from unittest import mock

try:
    import flet as ft
except ImportError:                        # pragma: no cover - flet は任意の依存
    ft = None

import pytest

from tests.unit.test_gui_main_page import make_page
from yaqpy.app.ports import InMemoryFileSystem, StaticEnvironment
from yaqpy.app.service import YqService
from yaqpy.gui import expression_file as ef
from yaqpy.gui import intake
from yaqpy.gui.presenter import MainPresenter
from yaqpy.gui.state import GuiState


class EncodeDecodeTests:
    def test_encode_ends_with_exactly_one_lf(self) -> None:
        assert ef.encode_expression(".a | .b") == ".a | .b\n"
        assert ef.encode_expression(".a\n\n\n") == ".a\n"

    def test_encode_normalizes_line_endings_to_lf(self) -> None:
        assert ef.encode_expression(".a\r\n| .b\r\n") == ".a\n| .b\n"
        assert ef.encode_expression(".a\r| .b") == ".a\n| .b\n"

    def test_decode_strips_bom_crlf_and_one_trailing_newline(self) -> None:
        assert ef.decode_expression(b"\xef\xbb\xbf.a\r\n| .b\r\n") == ".a\n| .b"
        assert ef.decode_expression("﻿.a\n") == ".a"
        assert ef.decode_expression(".a\n\n") == ".a\n"            # 取り除くのは 1 つだけ

    def test_decode_keeps_comments_and_blank_lines_of_the_body(self) -> None:
        assert ef.decode_expression("# note\n.a\n\n| .b\n") == "# note\n.a\n\n| .b"

    def test_a_round_trip_returns_the_same_expression(self) -> None:
        expression = '.items[]\n| select(.enabled)\n# 日本語のコメント\n| "a\\nb"'
        assert ef.decode_expression(ef.encode_expression(expression).encode("utf-8")) == expression

    def test_non_utf8_bytes_are_refused(self) -> None:
        with pytest.raises(ef.ExpressionFileError):
            ef.decode_expression("あ".encode("cp932"))

    def test_the_size_limit_is_one_mib(self) -> None:
        ef.ensure_size(ef.MAX_BYTES)
        with pytest.raises(ef.ExpressionFileError):
            ef.ensure_size(ef.MAX_BYTES + 1)


class FileNameTests:
    @pytest.mark.parametrize("document, expected", [
        ("sample.json", "sample.yaqpy"),
        ("a.b.yaml", "a.b.yaqpy"),
        ("", "expression.yaqpy"),
        ("noext", "noext.yaqpy"),
    ])
    def test_default_name(self, document: str, expected: str) -> None:
        assert ef.default_expression_file_name(document) == expected

    def test_an_extension_is_added_only_when_missing(self) -> None:
        assert ef.ensure_extension("/w/sel") == "/w/sel.yaqpy"
        assert ef.ensure_extension("/w/sel.yaqpy") == "/w/sel.yaqpy"
        assert ef.ensure_extension("/w/sel.yq") == "/w/sel.yq"

    def test_the_open_filter_takes_yaqpy_and_yq(self) -> None:
        assert ef.OPEN_EXTENSIONS == ("yaqpy", "yq")


def make_presenter(files: dict[str, str] | None = None) -> MainPresenter:
    fs = InMemoryFileSystem(dict(files or {}))
    return MainPresenter(service=YqService(fs, StaticEnvironment({})), fs=fs, state=GuiState(),
                         size_of=lambda p: len(fs.files[p].encode("utf-8")))


class PresenterTests:
    async def test_loading_a_file_sets_the_expression(self) -> None:
        p = make_presenter({"/w/sel.yaqpy": ".a\r\n| . + 1\r\n"})
        vm = await p.load_expression_file("/w/sel.yaqpy")
        assert vm.ok and (vm.name, vm.expression) == ("sel.yaqpy", ".a\n| . + 1")
        assert p.state.query.expression == ".a\n| . + 1"

    async def test_a_broken_expression_is_still_loaded(self) -> None:
        p = make_presenter({"/w/bad.yaqpy": ".a[\n"})
        vm = await p.load_expression_file("/w/bad.yaqpy")
        assert vm.ok and p.state.query.expression == ".a["
        assert not p.validate(p.state.query.expression).valid

    async def test_a_missing_file_is_an_error_and_keeps_the_expression(self) -> None:
        p = make_presenter()
        p.state.query.expression = ".keep"
        vm = await p.load_expression_file("/w/none.yaqpy")
        assert not vm.ok and p.state.query.expression == ".keep"

    async def test_a_too_large_file_is_refused_before_reading(self) -> None:
        big = "x" * (ef.MAX_BYTES + 1)
        p = make_presenter({"/w/big.yaqpy": big})
        p._fs.read_text = mock.MagicMock(side_effect=AssertionError("must not read"))
        vm = await p.load_expression_file("/w/big.yaqpy")
        assert not vm.ok and vm.error.code == "expression_file"

    async def test_saving_writes_the_expression_only(self) -> None:
        p = make_presenter()
        p.state.query.expression = ".items[]\n| .name"
        vm = await p.save_expression_file("/w/out.yaqpy")
        assert vm.ok and vm.path == "/w/out.yaqpy"
        assert p._fs.files["/w/out.yaqpy"] == ".items[]\n| .name\n"

    async def test_saving_adds_the_extension_when_missing(self) -> None:
        p = make_presenter()
        vm = await p.save_expression_file("/w/out")
        assert vm.path == "/w/out.yaqpy" and "/w/out.yaqpy" in p._fs.files

    async def test_a_saved_file_loads_back_and_is_the_same(self) -> None:
        p = make_presenter()
        p.state.query.expression = "# c\n.a | . + 1"
        await p.save_expression_file("/w/r.yaqpy")
        p.state.query.expression = "."
        await p.load_expression_file("/w/r.yaqpy")
        assert p.state.query.expression == "# c\n.a | . + 1"

    def test_the_default_name_follows_the_open_document(self) -> None:
        p = make_presenter({"/w/data.json": "{}"})
        assert p.default_expression_file_name() == "expression.yaqpy"
        p.open_text("a: 1\n", name="data.json")
        assert p.default_expression_file_name() == "data.yaqpy"

    def test_the_web_download_carries_the_bytes_and_the_name(self) -> None:
        p = make_presenter()
        p.state.query.expression = ".a"
        vm = p.expression_download()
        assert (vm.file_name, vm.data) == ("expression.yaqpy", b".a\n")

    def test_web_bytes_are_decoded_like_a_file(self) -> None:
        p = make_presenter()
        vm = p.load_expression_bytes("s.yaqpy", b"\xef\xbb\xbf.a\r\n")
        assert vm.ok and p.state.query.expression == ".a"
        assert not p.load_expression_bytes("s.yaqpy", "あ".encode("cp932")).ok
        assert p.check_expression_upload_size(ef.MAX_BYTES + 1) is not None
        assert p.check_expression_upload_size(ef.MAX_BYTES) is None

    async def test_an_expression_loaded_before_opening_survives_opening_a_document(self) -> None:
        """8-2 の要確認：文書を開くときに式を「.」へ戻さない（閉じたときは戻す）。"""
        p = make_presenter({"/w/a.json": '{"a": 1}\n'})
        p.state.query.expression = ".a"
        assert (await p.open_path("/w/a.json")).ok
        assert p.state.query.expression == ".a"
        p.close_document()
        assert p.state.query.expression == "."

    async def test_replacing_open_documents_still_starts_from_identity(self) -> None:
        p = make_presenter({"/w/a.json": '{"a": 1}\n'})
        p.open_text("x: 1\n")
        p.state.query.expression = ".x"
        p._accept(intake.from_text("y: 2\n"))
        assert p.state.query.expression == "."


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class PageTests:
    async def test_load_button_puts_the_file_into_the_expression_field(self) -> None:
        from yaqpy.gui import texts

        page, presenter, state = make_page()
        presenter._fs.files["/w/sel.yaqpy"] = ".a | . + 1\n"
        page._picker.pick_files = mock.AsyncMock(return_value=[mock.MagicMock(path="/w/sel.yaqpy")])
        await page._on_load_expression(mock.MagicMock())
        assert page._expr_field.value == state.query.expression == ".a | . + 1"
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_EXPR_LOADED.format(
            name="sel.yaqpy")
        kwargs = page._picker.pick_files.call_args.kwargs
        assert kwargs["allowed_extensions"] == ["yaqpy", "yq"] and kwargs["allow_multiple"] is False
        assert kwargs["file_type"] == ft.FilePickerFileType.CUSTOM

    async def test_loading_does_not_run(self) -> None:
        page, presenter, _ = make_page()
        presenter._fs.files["/w/sel.yaqpy"] = ".a\n"
        page._picker.pick_files = mock.AsyncMock(return_value=[mock.MagicMock(path="/w/sel.yaqpy")])
        page._run = mock.AsyncMock()
        await page._on_load_expression(mock.MagicMock())
        page._run.assert_not_called()

    async def test_a_cancelled_dialog_changes_nothing(self) -> None:
        page, _, state = make_page()
        state.query.expression = ".keep"
        page._picker.pick_files = mock.AsyncMock(return_value=[])
        await page._on_load_expression(mock.MagicMock())
        assert state.query.expression == ".keep"

    async def test_a_bad_file_shows_the_error_and_keeps_the_expression(self) -> None:
        page, _, state = make_page()
        state.query.expression = ".keep"
        page._picker.pick_files = mock.AsyncMock(return_value=[mock.MagicMock(path="/w/missing.yaqpy")])
        await page._on_load_expression(mock.MagicMock())
        assert state.query.expression == ".keep"
        assert page._status_text.value

    async def test_a_broken_expression_is_loaded_and_marked(self) -> None:
        page, presenter, _ = make_page()
        presenter._fs.files["/w/bad.yaqpy"] = ".a[\n"
        page._picker.pick_files = mock.AsyncMock(return_value=[mock.MagicMock(path="/w/bad.yaqpy")])
        await page._on_load_expression(mock.MagicMock())
        assert page._expr_field.value == ".a[" and page._expr_field.error

    async def test_save_button_writes_a_yaqpy_file(self) -> None:
        from yaqpy.gui import texts

        page, presenter, state = make_page()
        state.query.expression = ".a"
        page._expr_field.value = ".a"
        page._picker.save_file = mock.AsyncMock(return_value="/w/out")
        await page._on_save_expression(mock.MagicMock())
        assert presenter._fs.files["/w/out.yaqpy"] == ".a\n"
        assert page._page.show_dialog.call_args.args[0].content.value == texts.MSG_EXPR_SAVED.format(
            path="/w/out.yaqpy")
        kwargs = page._picker.save_file.call_args.kwargs
        assert kwargs["file_name"] == "expression.yaqpy" and kwargs["allowed_extensions"] == ["yaqpy"]

    async def test_a_cancelled_save_writes_nothing(self) -> None:
        page, presenter, _ = make_page()
        page._picker.save_file = mock.AsyncMock(return_value=None)
        await page._on_save_expression(mock.MagicMock())
        assert not any(name.endswith(".yaqpy") for name in presenter._fs.files)

    def test_save_is_enabled_only_for_a_non_empty_expression_and_load_always(self) -> None:
        page, _, _ = make_page()
        assert not page._save_expr_button.disabled            # 初期の式は「.」
        page._on_expr_clear(mock.MagicMock())
        assert page._save_expr_button.disabled
        load = page._expr_tools.controls[3]
        assert load.tooltip.startswith("式を読み込む") and not load.disabled
        page._on_expression_change(mock.MagicMock(control=mock.MagicMock(value=".a")))
        assert not page._save_expr_button.disabled

    async def test_a_loaded_expression_survives_opening_a_document(self) -> None:
        page, presenter, state = make_page()
        presenter._fs.files["/w/sel.yaqpy"] = ".db.port\n"
        page._picker.pick_files = mock.AsyncMock(return_value=[mock.MagicMock(path="/w/sel.yaqpy")])
        await page._on_load_expression(mock.MagicMock())
        await presenter.open_path("/w/app.toml")
        page._after_open()
        assert page._expr_field.value == ".db.port"
        vm = await presenter.run()
        assert vm.ok and "1" in vm.full_text


@pytest.mark.skipif(ft is None, reason="flet is not installed")
class WebPageTests:
    """Web 版：式ファイルはアップロード／ダウンロードで受け渡す。"""

    async def test_load_goes_through_the_uploader(self) -> None:
        from tests.unit.test_gui_main_page import make_web_page
        from yaqpy.gui._upload import Uploaded

        page, presenter, state = make_web_page(uploaded=[Uploaded(name="s.yaqpy", data=b".a\r\n")])
        await page._on_load_expression(mock.MagicMock())
        assert state.query.expression == ".a"
        kwargs = page._uploader.pick.call_args.kwargs
        assert kwargs["allowed_extensions"] == ["yaqpy", "yq"] and kwargs["allow_multiple"] is False
        assert kwargs["check_size"](ef.MAX_BYTES + 1) != ""       # 大きすぎるものは送らせない
        assert kwargs["check_size"](10) == ""

    async def test_a_failed_upload_shows_its_error(self) -> None:
        from tests.unit.test_gui_main_page import make_web_page
        from yaqpy.gui._upload import Uploaded

        page, _, state = make_web_page(uploaded=[Uploaded(name="s.yaqpy", error="upload failed")])
        state.query.expression = ".keep"
        await page._on_load_expression(mock.MagicMock())
        assert state.query.expression == ".keep" and "upload failed" in page._status_text.value

    async def test_save_downloads_and_writes_nothing_on_the_server(self) -> None:
        from tests.unit.test_gui_main_page import make_web_page

        page, presenter, state = make_web_page()
        state.query.expression = ".a"
        await page._on_save_expression(mock.MagicMock())
        kwargs = page._picker.save_file.call_args.kwargs
        assert (kwargs["file_name"], kwargs["src_bytes"]) == ("expression.yaqpy", b".a\n")
