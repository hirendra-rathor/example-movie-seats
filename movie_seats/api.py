"""Translate booking HTTP requests and reservation-service outcomes."""

import json

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from .db import Store
from .domain import Problem


class APIResponse(JSONResponse):
    """Keep terminal and browser JSON responses readable for this example."""

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seats: list[StrictStr] = Field(min_length=1, max_length=12)
    request_key: StrictStr | None = None


def register_api(app: FastAPI, store: Store) -> None:
    @app.exception_handler(Problem)
    async def problem_response(_request, error: Problem):
        headers = {"Retry-After": "1"} if error.status == 503 else None
        return JSONResponse({"error": {"code": error.code, "message": str(error)}}, status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        return JSONResponse({"error": {"code": "invalid_request", "message": "The request does not match the API schema."}}, status_code=422)

    @app.get("/screening")
    def screening():
        return store.screening()

    @app.post("/reservations", status_code=201)
    def hold(body: HoldRequest, response: Response):
        result = store.hold(body.seats, body.request_key)
        response.status_code = 201 if result.created else 200
        return result.reservation

    @app.get("/reservations/{reservation_id}")
    def reservation(reservation_id: str):
        return store.get(reservation_id)

    @app.post("/reservations/{reservation_id}/confirm")
    def confirm(reservation_id: str):
        return store.complete(reservation_id, "confirmed")

    @app.post("/reservations/{reservation_id}/cancel")
    def cancel(reservation_id: str):
        return store.complete(reservation_id, "cancelled")
