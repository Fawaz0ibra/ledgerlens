"""Fixtures every test file can use. pytest loads this file first and hands a fixture to any test that names it."""

import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ledgerlens.api.app import create_app
from ledgerlens.api.settings import Settings

# The synthetic invoice the demo scripts use: right shape, right numbers.
_SAMPLE = json.loads((Path(__file__).parents[1] / "scripts" / "sample_invoice.json").read_text(encoding="utf-8"))


@pytest.fixture
def invoice_data() -> dict[str, Any]:
    """The sample invoice as JSON data. Each test gets its own copy, so one test's edits can't leak into the next."""
    return copy.deepcopy(_SAMPLE)


@pytest.fixture
def invoice_with() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """invoice_with({"lines.0.unit_price": "26.00"}): a fresh copy of the sample with those fields set."""

    def build(changes: dict[str, Any]) -> dict[str, Any]:
        data = copy.deepcopy(_SAMPLE)
        for path, value in changes.items():
            *parents, last = (int(key) if key.isdigit() else key for key in path.split("."))
            target = data
            for key in parents:
                target = target[key]
            target[last] = value
        return data

    return build


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: a .env file on the developer's machine can't change what the tests see.
    return Settings(_env_file=None, environment="test")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """Calls the app directly, in this process: no server, no port, no network.

    `with` runs the app's startup before the test and its shutdown after it, as Uvicorn would.
    """
    with TestClient(create_app(settings)) as client:
        yield client
