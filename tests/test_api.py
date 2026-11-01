"""The HTTP service, called through TestClient: the real app, in this process, with no server."""

import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ledgerlens.api.app import create_app
from ledgerlens.api.logs import JsonFormatter
from ledgerlens.api.settings import Settings

CHECK = "/v1/invoices/check"
JSON = {"Content-Type": "application/json"}


# --- Health -------------------------------------------------------------------------------------------

def test_live_always_but_ready_only_while_started(settings):
    app = create_app(settings)
    not_started = TestClient(app)  # no `with`, so the app's startup never runs
    assert not_started.get("/health/live").status_code == 200
    assert not_started.get("/health/ready").status_code == 503
    with TestClient(app) as started:
        assert started.get("/health/ready").json() == {"status": "ready"}
    assert not_started.get("/health/ready").status_code == 503  # shutdown ran when the `with` ended


# --- Checking invoices --------------------------------------------------------------------------------

def test_a_correct_invoice_gets_no_findings(client, invoice_data):
    response = client.post(CHECK, json=invoice_data)
    assert response.status_code == 200
    assert response.json() == {"invoice_number": "INV-2026-0001", "findings": []}


def test_wrong_numbers_are_findings_not_errors(client, invoice_with):
    response = client.post(CHECK, json=invoice_with({"vat_total": "70.00", "total": "499.00"}))
    assert response.status_code == 200
    assert [finding["code"] for finding in response.json()["findings"]] == ["vat_total_mismatch"]


def _unit_price_as_json_number(data: dict[str, Any], number: str) -> str:
    """The invoice as JSON text, with the first unit price written as a bare number instead of a string."""
    text = json.dumps(data)
    changed = text.replace('"unit_price": "25.00"', f'"unit_price": {number}')
    assert changed != text, "the sample invoice no longer has a unit_price of 25.00"
    return changed


def test_an_exact_json_number_is_accepted(client, invoice_data):
    response = client.post(CHECK, content=_unit_price_as_json_number(invoice_data, "25.00"), headers=JSON)
    assert response.status_code == 200
    assert response.json()["findings"] == []


def test_a_17_digit_json_number_is_refused_not_rounded(client, invoice_data):
    """ADR 0003. FastAPI's default JSON reading turns this into the float 25.0 and accepts it with no error."""
    text = _unit_price_as_json_number(invoice_data, "25.000000000000001")
    response = client.post(CHECK, content=text, headers=JSON)
    assert response.status_code == 422
    assert [(e["field"], e["type"]) for e in response.json()["errors"]] == [("lines.0.unit_price", "decimal_max_digits")]


# --- Errors -------------------------------------------------------------------------------------------

def test_a_wrong_shape_is_a_problem_document_without_the_value(client, invoice_with):
    response = client.post(CHECK, json=invoice_with({"seller.vat_number": "39999999990001"}))
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert [(e["field"], e["type"]) for e in body["errors"]] == [("seller.vat_number", "string_pattern_mismatch")]
    assert body["request_id"] == response.headers["x-request-id"]
    assert "39999999990001" not in response.text


def test_broken_json_says_where_it_breaks(client):
    response = client.post(CHECK, content='{"invoice_number": ', headers=JSON)
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "", "problem": "Not valid JSON at character 19: Expecting value", "type": "json_invalid"}]


def test_an_unknown_path_is_a_problem_document(client):
    response = client.get("/v1/nothing-here")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_a_crash_is_a_500_that_hides_the_internals(settings):
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


def test_a_body_over_the_limit_is_refused(invoice_data):
    small = Settings(_env_file=None, environment="test", max_body_bytes=100)
    with TestClient(create_app(small)) as client:
        response = client.post(CHECK, json=invoice_data)
    assert response.status_code == 413
    # ADR 0003: Starlette's size guard answers in plain text, not in our problem-details shape.
    assert response.headers["content-type"].startswith("text/plain")


# --- Request IDs and logs -----------------------------------------------------------------------------

@pytest.mark.parametrize("sent", ["demo-0001", "a" * 64], ids=["short", "64-chars"])
def test_a_plain_request_id_is_kept(client, sent):
    assert client.get("/health/live", headers={"X-Request-ID": sent}).headers["x-request-id"] == sent


@pytest.mark.parametrize("sent", ["a" * 65, "has spaces", "semi;colon"], ids=["65-chars", "spaces", "semicolon"])
def test_any_other_request_id_is_replaced_with_our_own(client, sent):
    returned = client.get("/health/live", headers={"X-Request-ID": sent}).headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", returned)


def test_log_lines_carry_the_request_id_and_no_invoice_contents(client, invoice_data, caplog):
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
def test_the_api_schema_is_hidden_in_prod(environment, status):
    with TestClient(create_app(Settings(_env_file=None, environment=environment))) as client:
        assert client.get("/openapi.json").status_code == status


@pytest.mark.parametrize(("variable", "value"), [
    ("LEDGERLENS_LOG_LEVEL", "LOUD"),
    ("LEDGERLENS_MAX_BODY_BYTES", "0"),
    ("LEDGERLENS_ENVIRONMENT", "staging"),
])
def test_a_bad_setting_stops_the_app_before_it_starts(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)  # monkeypatch undoes this when the test ends
    with pytest.raises(ValidationError, match=variable.removeprefix("LEDGERLENS_").lower()):
        create_app()
