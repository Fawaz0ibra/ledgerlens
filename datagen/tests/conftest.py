"""Fixtures shared by the generator's tests."""

from collections.abc import Iterator

import pytest

from ledgerlens_datagen.render import Renderer, open_renderer


@pytest.fixture(scope="module")
def renderer() -> Iterator[Renderer]:
    """A headless Chromium, started once per test file and closed when that file's tests are done.

    Once per file, not once for the whole run: Playwright allows one browser session per process, and
    test_cli.py starts its own through the command.
    """
    with open_renderer() as renderer:
        yield renderer
