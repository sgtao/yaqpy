"""Shared pytest configuration for the whole test suite.

* ``async def`` tests are run with ``asyncio.run`` (no plugin needed: the GUI presenter is async and
  that is all that has to be supported).
* Tests get a marker from where they live (``tests/golden`` -> ``golden``, ``tests/acceptance`` ->
  ``acceptance``, ``test_gui_*`` -> ``gui``), so ``pytest -m "not acceptance"`` and the like work
  without decorating every class.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

_DIRECTORY_MARKERS = {"golden": "golden", "acceptance": "acceptance"}


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        arguments = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(pyfuncitem.obj(**arguments))
        return True
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.fspath))
        for directory, marker in _DIRECTORY_MARKERS.items():
            if directory in path.parts:
                item.add_marker(getattr(pytest.mark, marker))
        if path.name.startswith("test_gui_"):
            item.add_marker(pytest.mark.gui)
