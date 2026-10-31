"""Send example requests to a running LedgerLens API and print what comes back.

Start the API in one terminal:  uv run uvicorn ledgerlens.api.app:create_app --factory
Then, in a second terminal:     uv run scripts/api_demo.py
"""

import http.client
import json
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000
GOOD = Path(__file__).with_name("sample_invoice.json").read_text(encoding="utf-8")


def show(status: int, headers: Message, text: str) -> None:
    print(f"{status}  {headers['Content-Type']}  X-Request-ID: {headers['X-Request-ID']}")
    is_json = "json" in headers["Content-Type"]
    print(json.dumps(json.loads(text), indent=2, ensure_ascii=False) if is_json else text)


def send(title: str, method: str, path: str, body: str | None = None, request_id: str | None = None) -> None:
    print(f"\n=== {title} ===")
    headers = {"Content-Type": "application/json"}
    if request_id:
        headers["X-Request-ID"] = request_id
    data = body.encode() if body is not None else None
    request = urllib.request.Request(f"http://{HOST}:{PORT}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            show(response.status, response.headers, response.read().decode())
    except urllib.error.HTTPError as err:  # urllib raises on 4xx and 5xx; the reply is still in the error
        show(err.code, err.headers, err.read().decode())


def announce_only(title: str, path: str, size: int) -> None:
    """Send the headers of a big request but not its body: the service can refuse on the declared size."""
    print(f"\n=== {title} ===")
    connection = http.client.HTTPConnection(HOST, PORT, timeout=5)
    connection.putrequest("POST", path)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", str(size))
    connection.endheaders()
    response = connection.getresponse()
    show(response.status, response.headers, response.read().decode())
    connection.close()


def main() -> None:
    send("1. Liveness", "GET", "/health/live")
    send("2. Readiness", "GET", "/health/ready")
    send("3. A good invoice, sent with our own request ID", "POST", "/v1/invoices/check", GOOD, request_id="demo-0001")

    bad = json.loads(GOOD)
    bad["seller"]["vat_number"] = "39999999990001"  # 14 digits
    bad["discount"] = "5.00"  # not a field in the contract
    send("4. Wrong shape", "POST", "/v1/invoices/check", json.dumps(bad))

    inflated = json.loads(GOOD)
    inflated["vat_total"], inflated["total"] = "70.00", "499.00"
    send("5. Right shape, wrong numbers", "POST", "/v1/invoices/check", json.dumps(inflated))

    # A JSON number (not a string) with 17 significant digits, more than a float can hold.
    exact = GOOD.replace('"unit_price": "25.00"', '"unit_price": 25.000000000000001')
    assert exact != GOOD
    send("6. An amount sent as a JSON number with 17 digits", "POST", "/v1/invoices/check", exact)

    send("7. Broken JSON", "POST", "/v1/invoices/check", '{"invoice_number": ')
    send("8. A path that doesn't exist", "GET", "/v1/nothing-here")
    announce_only("9. A request that says its body is 2 MB", "/v1/invoices/check", 2_000_000)


if __name__ == "__main__":
    main()
