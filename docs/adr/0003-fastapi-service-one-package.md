# 0003. Serve the API with FastAPI on Uvicorn, from one package

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

LedgerLens needs an HTTP service in front of the invoice contract. Later it will call model servers
and Postgres, so most of its time will be spent waiting on other services. Its callers (other
services, the review agents, a UI) need a machine-readable description of the API, and Kubernetes
(Module 7) needs health and readiness endpoints. Today the API is the only component. Later ones bring
heavy dependencies: PyTorch for vision and a rendering stack for the invoice generator.

## Decision

FastAPI 0.162.0 on Uvicorn 0.54.0, with settings read by pydantic-settings 2.16.2. All code stays in
one Python package, `ledgerlens` (src layout, uv_build, one `uv.lock`), and the API is the subpackage
`ledgerlens.api`. Invoice routes read JSON numbers as Decimal, not float. Each container runs one
Uvicorn process; we scale by running more containers.

## Rejected options

- **Flask:** it doesn't check requests against Pydantic models or generate an API schema without
  extensions, and it is synchronous by default while our future calls are mostly waiting.
- **Django with Django REST Framework:** it brings a database layer, an admin site and templates we
  don't need, and its serializers would duplicate the Pydantic contract.
- **Litestar:** similar features to FastAPI (typed, async, generated schema), but a smaller ecosystem
  and less common in the jobs this project targets.
- **Plain Starlette:** FastAPI is built on it. We would rebuild request checking and the schema ourselves.
- **Several packages now (a uv workspace, one per component):** there is no second component yet.
- **Gunicorn running several Uvicorn workers per container:** Kubernetes already runs and restarts
  copies. One process per container keeps resource limits and health checks simple.

## Measurements

The framework choice was not measured: we didn't build the service in each framework, and a
hello-world benchmark wouldn't decide it. We did measure how each way of reading JSON treats an amount
sent as a JSON number with 17 significant digits:

| `sample_invoice.json` with `"unit_price": 25.000000000000001` | Exact reading (chosen) | FastAPI's default reading |
|---|---|---|
| Response | 422, `decimal_max_digits` on `lines.0.unit_price` | 200, no findings |
| What reached the contract | `Decimal('25.000000000000001')` | the float `25.0`, already rounded |

FastAPI's default reads the body with `json.loads`, which turns every JSON number with a decimal point
into a float. The amount was changed without any error.

For reference, single requests in the log took 0.2–2.8 ms. That is not a benchmark; load testing comes
in Module 9.

Runs on 2026-10-31: FastAPI 0.162.0, Starlette 1.10.0, Uvicorn 0.54.0, Pydantic 2.14.2,
Python 3.12.15, WSL2 Ubuntu 24.04 on a Ryzen 5 3600X. The code is the commit that adds this record;
the default-reading run is the same code with `route_class` removed from the invoices router.

## Consequences

- The invoice contract is the API's input check with no extra code. `/docs` and `/openapi.json` are
  generated from it, and they are turned off when `LEDGERLENS_ENVIRONMENT=prod`.
- The exact reading depends on FastAPI calling `request.json()` to read bodies. A test (lesson 1.3) must
  pin that the 17-digit case gets a 422, so an upgrade that changes this fails loudly.
- Starlette's size guard answers 413 in plain text, not in our problem-details shape.
- Everything installs together. A heavy dependency added for one component would land in the API's
  environment too, until we split the package.

## Revisit when

- A component needs dependencies the API shouldn't carry (PyTorch in Module 4, the invoice renderer in
  lesson 1.6): split into a uv workspace.
- FastAPI starts reading JSON bodies with Pydantic's own parser, which would make the exact reading
  unnecessary. Check on each FastAPI upgrade.
- Load tests in Module 9 show the service can't meet its latency target.
