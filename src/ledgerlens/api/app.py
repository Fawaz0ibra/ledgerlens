"""The LedgerLens API. Run from the repo root:

    uv run uvicorn ledgerlens.api.app:create_app --factory
"""

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from importlib.metadata import version
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from ledgerlens.api import errors, logs
from ledgerlens.api.settings import Settings
from ledgerlens.contracts import Finding, Invoice, check_invoice

log = logging.getLogger("ledgerlens.api")

# A request ID from a caller or gateway is kept only if it is short and plain; otherwise we make our own.
_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class _ExactJSONRequest(Request):
    """Reads JSON numbers as Decimal. FastAPI's default reads them as float, which can change an amount."""

    async def json(self) -> Any:
        return json.loads(await self.body(), parse_float=Decimal)


class _ExactJSONRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def exact_json_handler(request: Request) -> Response:
            return await handler(_ExactJSONRequest(request.scope, request.receive))

        return exact_json_handler


class CheckResult(BaseModel):
    invoice_number: str
    findings: list[Finding]


health = APIRouter(prefix="/health", tags=["health"])
invoices = APIRouter(prefix="/v1/invoices", tags=["invoices"], route_class=_ExactJSONRoute)


@health.get("/live")
async def live() -> dict[str, str]:
    """The process is up and answering. If this fails, restart it."""
    return {"status": "alive"}


@health.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """The service can take traffic now. If this fails, send traffic elsewhere until it passes."""
    if not request.app.state.ready:
        return JSONResponse({"status": "not ready"}, status_code=503)
    return JSONResponse({"status": "ready"})


@invoices.post("/check")
async def check(invoice: Invoice) -> CheckResult:
    """Check a well-formed invoice's arithmetic and VAT. A malformed one gets a 422 listing every problem."""
    findings = check_invoice(invoice)
    log.info("invoice checked", extra={"fields": {"lines": len(invoice.lines), "findings": [f.code for f in findings]}})
    return CheckResult(invoice_number=invoice.invoice_number, findings=findings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logs.configure(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Later lessons connect to Postgres and the model server here. Until then, started means ready.
        app.state.ready = True
        log.info("ready", extra={"fields": {"environment": settings.environment}})
        yield
        app.state.ready = False
        log.info("stopped")

    app = FastAPI(
        title="LedgerLens",
        version=version("ledgerlens"),
        lifespan=lifespan,
        # No interactive docs or schema in prod: callers there get the schema from us, not from the service.
        openapi_url=None if settings.environment == "prod" else "/openapi.json",
    )
    app.state.ready = False
    app.include_router(health)
    app.include_router(invoices)
    errors.install(app)
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.max_body_bytes)

    @app.middleware("http")  # added last, so it runs first: it sees every request and every crash
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        given = request.headers.get("x-request-id", "")
        rid = given if _REQUEST_ID.fullmatch(given) else uuid.uuid4().hex
        token = logs.request_id.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error")
            response = errors.problem(500, "Something went wrong on our side. Quote the request_id if you report it.")
        response.headers["X-Request-ID"] = rid
        log.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }})
        logs.request_id.reset(token)
        return response

    return app
