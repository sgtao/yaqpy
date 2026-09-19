"""flet を実際に起動する層。ここから先だけが flet に依存する。"""

from __future__ import annotations

import flet as ft

from yaqpy.gui import texts
from yaqpy.gui._di import make_presenter
from yaqpy.gui.pages.main_page import MainPage
from yaqpy.gui.state import GuiState


def _main(page: ft.Page) -> None:
    page.title = texts.APP_TITLE
    page.padding = 12
    page.window.width = 1180
    page.window.height = 820
    page.window.min_width = 820
    page.window.min_height = 560

    state = GuiState()
    presenter = make_presenter(state)

    picker = ft.FilePicker()
    page.services.append(picker)           # Flet 1.0: overlay ではなく services

    main_page = MainPage(page=page, presenter=presenter, state=state, picker=picker)
    page.add(main_page.control)


def run_app() -> None:
    ft.run(_main)
