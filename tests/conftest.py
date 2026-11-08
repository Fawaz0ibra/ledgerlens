"""Fixtures every test file can use. pytest loads this file first and hands a fixture to any test that names it."""

import copy
import json
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from testcontainers.community.postgres import PostgresContainer

from ledgerlens.api.app import create_app
from ledgerlens.api.settings import Settings

# The synthetic invoice the demo scripts use: right shape, right numbers. json.loads can return anything,
# so the hint says what this file holds; without it, every copy below would be unchecked (Any).
_SAMPLE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "scripts" / "sample_invoice.json").read_text(encoding="utf-8")
)

# The same Postgres image as compose.yaml. Change both together.
POSTGRES_IMAGE = "postgres:18.6-trixie@sha256:3a4264520e121176619f54ff867d12774bc81e95e7b84db58d63bccdb6144b81"


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
            target: Any = data  # steps through both dicts and lists, so no single type fits
            for key in parents:
                target = target[key]
            target[last] = value
        return data

    return build


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A real Postgres in a throwaway container: started once for the whole run, removed at the end.

    Needs Docker running. The port is opened on 127.0.0.1 only, and the password is new each run.
    """
    postgres = PostgresContainer(POSTGRES_IMAGE, password=secrets.token_hex(16), driver=None)
    # A random free port on 127.0.0.1, not on every network interface. testcontainers has no option for
    # this, so we set Docker's own form of the binding (address, no port) directly. testcontainers' type
    # hint allows only a port number here, so mypy is told to accept this one line.
    postgres.ports["5432"] = ("127.0.0.1",)  # type: ignore[assignment]
    with postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def settings(database_url: str) -> Settings:
    # _env_file=None: a .env file on the developer's machine can't change what the tests see.
    return Settings(_env_file=None, environment="test", database_url=SecretStr(database_url))


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """Calls the app directly, in this process: no server, no port, no network.

    `with` runs the app's startup before the test and its shutdown after it, as Uvicorn would.
    """
    with TestClient(create_app(settings)) as client:
        yield client
