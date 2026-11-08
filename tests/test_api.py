"""The HTTP service, called through TestClient: the real app, in this process, with no server."""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from ledgerlens.api.app import create_app
from ledgerlens.api.logs import JsonFormatter
from ledgerlens.api.settings import Settings

CHECK = "/v1/invoices/check"
JSON = {"Content-Type": "application/json"}

# Nothing listens on port 1, so every connection attempt is refused at once. Not a real password.
PASSWORD = "not-a-real-password"
UNREACHABLE = f"postgresql://ledgerlens:{PASSWORD}@127.0.0.1:1/ledgerlens"


# --- Health -------------------------------------------------------------------------------------------


def test_live_always_but_ready_only_while_started(settings: Settings) -> None:
    app = create_app(settings)
    not_started = TestClient(app)  # no `with`, so the app's startup never runs
    assert not_started.get("/health/live").status_code == 200
    assert not_started.get("/health/ready").status_code == 503
    with TestClient(app) as started:
        assert started.get("/health/ready").json() == {"status": "ready"}
    assert not_started.get("/health/ready").status_code == 503  # shutdown ran when the `with` ended


@pytest.fixture
def client_without_database() -> Iterator[TestClient]:
    """The app with a database URL that nothing answers.

    Built in a fixture, not in the test: create_app sets up logging, which replaces every log handler,
    including the one caplog collects with. pytest adds caplog's back when the test itself starts.
    """
    settings = Settings(_env_file=None, environment="test", database_url=SecretStr(UNREACHABLE))
    with TestClient(create_app(settings)) as client:
        yield client


def test_ready_needs_the_database_but_live_does_not(
    client_without_database: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.handler.setFormatter(JsonFormatter())  # as the service writes them, extra fields included
    assert client_without_database.get("/health/live").status_code == 200
    assert client_without_database.get("/health/ready").status_code == 503
    # The first check proves caplog collected lines, so the second can't pass just because it saw none.
    assert "database not answering" in caplog.messages
    assert PASSWORD not in caplog.text


def test_settings_never_print_the_database_password() -> None:
    assert PASSWORD not in repr(Settings(_env_file=None, database_url=SecretStr(UNREACHABLE)))


# --- Checking invoices --------------------------------------------------------------------------------


def test_a_correct_invoice_gets_no_findings(client: TestClient, invoice_data: dict[str, Any]) -> None:
    response = client.post(CHECK, json=invoice_data)
    assert response.status_code == 200
    assert response.json() == {"invoice_number": "INV-2026-0001", "findings": []}


def test_wrong_numbers_are_findings_not_errors(
    client: TestClient, invoice_with: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    response = client.post(CHECK, json=invoice_with({"vat_total": "70.00", "total": "499.00"}))
    assert response.status_code == 200
    assert [finding["code"] for finding in response.json()["findings"]] == ["vat_total_mismatch"]


def _unit_price_as_json_number(data: dict[str, Any], number: str) -> str:
    """The invoice as JSON text, with the first unit price written as a bare number instead of a string."""
    text = json.dumps(data)
    changed = text.replace('"unit_price": "25.00"', f'"unit_price": {number}')
    assert changed != text, "the sample invoice no longer has a unit_price of 25.00"
    return changed


def test_an_exact_json_number_is_accepted(client: TestClient, invoice_data: dict[str, Any]) -> None:
    response = client.post(CHECK, content=_unit_price_as_json_number(invoice_data, "25.00"), headers=JSON)
    assert response.status_code == 200
    assert response.json()["findings"] == []


def test_a_17_digit_json_number_is_refused_not_rounded(client: TestClient, invoice_data: dict[str, Any]) -> None:
    """ADR 0003. FastAPI's default JSON reading turns this into the float 25.0 and accepts it with no error."""
    text = _unit_price_as_json_number(invoice_data, "25.000000000000001")
    response = client.post(CHECK, content=text, headers=JSON)
    assert response.status_code == 422
    assert [(e["field"], e["type"]) for e in response.json()["errors"]] == [
        ("lines.0.unit_price", "decimal_max_digits")
    ]


# --- Errors -------------------------------------------------------------------------------------------


def test_a_wrong_shape_is_a_problem_document_without_the_value(
    client: TestClient, invoice_with: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    response = client.post(CHECK, json=invoice_with({"seller.vat_number": "39999999990001"}))
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert [(e["field"], e["type"]) for e in body["errors"]] == [("seller.vat_number", "string_pattern_mismatch")]
    assert body["request_id"] == response.headers["x-request-id"]
    assert "39999999990001" not in response.text


def test_broken_json_says_where_it_breaks(client: TestClient) -> None:
    response = client.post(CHECK, content='{"invoice_number": ', headers=JSON)
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "", "problem": "Not valid JSON at character 19: Expecting value", "type": "json_invalid"}
    ]


def test_an_unknown_path_is_a_problem_document(client: TestClient) -> None:
    response = client.get("/v1/nothing-here")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_a_crash_is_a_500_that_hides_the_internals(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("internal detail: table invoices_v2 is locked")

    with TestClient(app) as client:
        response = client.get("/crash")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert "invoices_v2" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_a_body_over_the_limit_is_refused(database_url: str, invoice_data: dict[str, Any]) -> None:
    small = Settings(_env_file=None, environment="test", database_url=SecretStr(database_url), max_body_bytes=100)
    with TestClient(create_app(small)) as client:
        response = client.post(CHECK, json=invoice_data)
    assert response.status_code == 413
    # ADR 0003: Starlette's size guard answers in plain text, not in our problem-details shape.
    assert response.headers["content-type"].startswith("text/plain")


# --- Request IDs and logs -----------------------------------------------------------------------------


@pytest.mark.parametrize("sent", ["demo-0001", "a" * 64], ids=["short", "64-chars"])
def test_a_plain_request_id_is_kept(client: TestClient, sent: str) -> None:
    assert client.get("/health/live", headers={"X-Request-ID": sent}).headers["x-request-id"] == sent


@pytest.mark.parametrize("sent", ["a" * 65, "has spaces", "semi;colon"], ids=["65-chars", "spaces", "semicolon"])
def test_any_other_request_id_is_replaced_with_our_own(client: TestClient, sent: str) -> None:
    returned = client.get("/health/live", headers={"X-Request-ID": sent}).headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", returned)


def test_log_lines_carry_the_request_id_and_no_invoice_contents(
    client: TestClient, invoice_data: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    # caplog collects every log line written during the test. Format them as the service does, as they are written.
    caplog.handler.setFormatter(JsonFormatter())
    client.post(CHECK, json=invoice_data, headers={"X-Request-ID": "test-0001"})
    lines = [json.loads(line) for line in caplog.text.splitlines()]
    ours = [line for line in lines if line["logger"].startswith("ledgerlens")]
    assert [line["message"] for line in ours] == ["invoice checked", "request"]
    assert {line["request_id"] for line in ours} == {"test-0001"}
    for contents in ("Example Trading Co.", "399999999900013", "493.35"):
        assert contents not in caplog.text


# --- Settings -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("environment", "status"), [("dev", 200), ("prod", 404)])
def test_the_api_schema_is_hidden_in_prod(database_url: str, environment: Literal["dev", "prod"], status: int) -> None:
    settings = Settings(_env_file=None, environment=environment, database_url=SecretStr(database_url))
    with TestClient(create_app(settings)) as client:
        assert client.get("/openapi.json").status_code == status


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("LEDGERLENS_LOG_LEVEL", "LOUD"),
        ("LEDGERLENS_MAX_BODY_BYTES", "0"),
        ("LEDGERLENS_ENVIRONMENT", "staging"),
    ],
)
def test_a_bad_setting_stops_the_app_before_it_starts(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    # monkeypatch undoes both when the test ends. A valid URL, so the bad setting is the only problem.
    monkeypatch.setenv("LEDGERLENS_DATABASE_URL", UNREACHABLE)
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError, match=variable.removeprefix("LEDGERLENS_").lower()) as caught:
        create_app()
    assert caught.value.error_count() == 1


def test_a_missing_database_url_stops_the_app_before_it_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGERLENS_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url") as caught:
        Settings(_env_file=None)
    assert caught.value.error_count() == 1
