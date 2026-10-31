"""Every error leaves the service in one shape: RFC 9457 "problem details" (application/problem+json).

Callers get the status, a plain explanation and the request ID to quote. They never get a stack
trace or internal details; those go to the log.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ledgerlens.api.logs import request_id


def problem(status: int, detail: str, headers: dict[str, str] | None = None, **extensions: Any) -> JSONResponse:
    body = {
        "type": "about:blank",  # no custom error types yet: the status code says what kind of error it is
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "request_id": request_id.get(),
        **extensions,
    }
    return JSONResponse(body, status_code=status, headers=headers, media_type="application/problem+json")


def _describe(error: dict[str, Any]) -> dict[str, str]:
    # loc starts with where the value came from ("body"); the rest is the path inside it.
    # The input value is not echoed back: it can hold names and VAT numbers.
    where = ".".join(str(part) for part in error["loc"][1:])
    if error["type"] == "json_invalid":  # here loc holds a character position, not a field
        return {"field": "", "problem": f"Not valid JSON at character {where}: {error['ctx']['error']}",
                "type": error["type"]}
    return {"field": where, "problem": error["msg"], "type": error["type"]}


async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [_describe(e) for e in exc.errors()]
    return problem(422, f"The request doesn't match the contract: {len(errors)} problem(s).", errors=errors)


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return problem(exc.status_code, str(exc.detail), headers=exc.headers)


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
