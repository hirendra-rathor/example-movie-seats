"""Create the Movie Seats HTTP application."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from typing import Annotated

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from movie_seats.database import LOCK_TIMEOUT_SECONDS, database_path_from_environment, prepare_database
from movie_seats.reservations import (
    AVAILABLE,
    DEFAULT_HOLD_DURATION,
    HoldKeyNotFound,
    HoldKeyReused,
    InvalidHoldKey,
    InvalidSelection,
    Reservation,
    ReservationBook,
    ReservationBookBusy,
    ReservationNotFound,
    SeatsUnavailable,
    TransitionRefused,
)
from movie_seats.screening import SCREENING

HOLD_SECONDS_ENV = "MOVIE_SEATS_HOLD_SECONDS"


def hold_seconds_from_environment() -> int:
    """Read the hold time in seconds; an invalid value stops startup."""
    raw = os.environ.get(HOLD_SECONDS_ENV)
    if raw is None or raw.strip() == "":
        return int(DEFAULT_HOLD_DURATION.total_seconds())
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise ValueError(f"{HOLD_SECONDS_ENV} must be a positive whole number of seconds, not {raw!r}.")
    return seconds


class HoldRequest(BaseModel):
    seats: list[str] = Field(description="Seat labels to hold together.", examples=[["A3", "A4"]])


class SeatStatus(BaseModel):
    seat: str
    status: str = Field(description="`available`, `held` or `booked`.")


class SeatMap(BaseModel):
    screening_id: str
    seats: list[SeatStatus]


class ReservationBody(BaseModel):
    reservation_id: str
    screening_id: str
    status: str = Field(description="`held`, `confirmed`, `cancelled` or `expired`.")
    seats: list[str]
    created_at: str
    expires_at: str | None = Field(
        description="When a held reservation expires, or expired; null once it is confirmed or cancelled."
    )


class Problem(BaseModel):
    detail: str


class UnavailableProblem(Problem):
    unavailable_seats: list[str]


class InvalidSelectionProblem(Problem):
    invalid_seats: list[str]


class StatusProblem(Problem):
    status: str


def _reservation_body(reservation: Reservation) -> ReservationBody:
    return ReservationBody(
        reservation_id=reservation.reservation_id,
        screening_id=reservation.screening_id,
        status=reservation.status,
        seats=list(reservation.seats),
        created_at=reservation.created_at,
        expires_at=reservation.expires_at,
    )


def create_app(
    database_path: str | os.PathLike[str] | None = None,
    *,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
    hold_seconds: int | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Build the application around the reservation book stored at `database_path`."""
    path = Path(database_path) if database_path is not None else database_path_from_environment()
    seconds = hold_seconds if hold_seconds is not None else hold_seconds_from_environment()
    options = {"clock": clock} if clock is not None else {}
    book = ReservationBook(
        path, SCREENING, lock_timeout=lock_timeout, hold_duration=timedelta(seconds=seconds), **options
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Upgrade the file, then expire holds whose deadline passed while the service was stopped,
        # before uvicorn accepts the first request.
        prepare_database(path)
        book.start()
        yield

    app = FastAPI(title="Movie Seats", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(InvalidSelection)
    def invalid_selection(_: Request, error: InvalidSelection) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": error.message, "invalid_seats": list(error.seats)})

    @app.exception_handler(SeatsUnavailable)
    def seats_unavailable(_: Request, error: SeatsUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Some requested seats are not available.", "unavailable_seats": list(error.seats)},
        )

    @app.exception_handler(InvalidHoldKey)
    def invalid_hold_key(_: Request, error: InvalidHoldKey) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(HoldKeyReused)
    def hold_key_reused(_: Request, __: HoldKeyReused) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "This Idempotency-Key was already used for a different selection."},
        )

    @app.exception_handler(ReservationNotFound)
    def reservation_not_found(_: Request, __: ReservationNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Reservation not found."})

    @app.exception_handler(HoldKeyNotFound)
    def hold_key_not_found(_: Request, __: HoldKeyNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "No hold was recorded under this key."})

    @app.exception_handler(TransitionRefused)
    def transition_refused(_: Request, error: TransitionRefused) -> JSONResponse:
        action = "confirmed" if error.target == "confirmed" else "cancelled"
        return JSONResponse(
            status_code=409,
            content={"detail": f"This reservation is {error.status}; it can't be {action}.", "status": error.status},
        )

    @app.exception_handler(ReservationBookBusy)
    def reservation_book_busy(_: Request, __: ReservationBookBusy) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "The reservation book is busy. Nothing changed; retry the request."},
            headers={"Retry-After": "1"},
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _seat_map_page(book)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "movie-seats"}

    @app.get("/seats", response_model=SeatMap)
    def list_seats() -> SeatMap:
        """List every seat of the screening with its current status."""
        return SeatMap(
            screening_id=book.screening.screening_id,
            seats=[SeatStatus(seat=seat, status=status) for seat, status in book.seat_statuses()],
        )

    @app.post(
        "/holds",
        status_code=201,
        response_model=ReservationBody,
        responses={
            200: {"model": ReservationBody, "description": "This key already made a hold; it is returned as it stands."},
            409: {"model": UnavailableProblem, "description": "Some seats are taken; nothing was held."},
            422: {
                "model": InvalidSelectionProblem,
                "description": "The selection is empty, repeated or unknown, or the key is invalid or reused.",
            },
            503: {"model": Problem, "description": "The write lock was busy; nothing was held."},
        },
    )
    def place_hold(
        request: HoldRequest,
        response: Response,
        idempotency_key: Annotated[
            str | None,
            Header(
                alias="Idempotency-Key",
                description="A client-generated key, such as a UUID, repeated on every retry of this hold.",
            ),
        ] = None,
    ) -> ReservationBody:
        """Hold every requested seat together until `expires_at`, or none of them.

        A retried key returns its first hold.
        """
        result = book.place_hold(request.seats, request_key=idempotency_key)
        if result.replayed:
            response.status_code = 200
        response.headers["Location"] = f"/reservations/{result.reservation.reservation_id}"
        return _reservation_body(result.reservation)

    @app.get(
        "/holds/{key}",
        response_model=ReservationBody,
        responses={404: {"model": Problem, "description": "No hold was recorded under this key."}},
    )
    def find_hold(key: str) -> ReservationBody:
        """Find the reservation that a hold with this Idempotency-Key created."""
        return _reservation_body(book.find_by_key(key))

    @app.get(
        "/reservations/{reservation_id}",
        response_model=ReservationBody,
        responses={404: {"model": Problem, "description": "No reservation has this ID."}},
    )
    def get_reservation(reservation_id: str) -> ReservationBody:
        """Look up a reservation by the ID returned when it was held."""
        return _reservation_body(book.get_reservation(reservation_id))

    settle_responses = {
        404: {"model": Problem, "description": "No reservation has this ID."},
        409: {"model": StatusProblem, "description": "The reservation's status does not allow this change."},
        503: {"model": Problem, "description": "The write lock was busy; nothing changed."},
    }

    @app.post("/reservations/{reservation_id}/confirm", response_model=ReservationBody, responses=settle_responses)
    def confirm(reservation_id: str) -> ReservationBody:
        """Confirm a held reservation as a booking before it expires. Repeating the request changes nothing."""
        return _reservation_body(book.confirm(reservation_id))

    @app.post("/reservations/{reservation_id}/cancel", response_model=ReservationBody, responses=settle_responses)
    def cancel(reservation_id: str) -> ReservationBody:
        """Cancel a held reservation and release its seats. Repeating the request changes nothing."""
        return _reservation_body(book.cancel(reservation_id))

    return app


def _seat_map_page(book: ReservationBook) -> str:
    statuses = dict(book.seat_statuses())
    available = sum(1 for status in statuses.values() if status == AVAILABLE)
    rows = "\n".join(
        '        <div class="row">'
        + "".join(
            f'<div class="seat {escape(statuses[seat])}" data-seat="{escape(seat)}">'
            f'<strong>{escape(seat)}</strong><span>{escape(statuses[seat])}</span></div>'
            for seat in row
        )
        + "</div>"
        for row in book.screening.rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Movie Seats</title>
    <style>
        body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1c3347; background: #f5f0e5; }}
        main {{ max-width: 36rem; margin: 0 auto; padding: 2rem 1rem; }}
        h1 {{ margin-bottom: 0.25rem; }}
        .screen {{ margin: 2rem auto 1.5rem; width: 80%; border-top: 4px solid #62818a; border-radius: 50% 50% 0 0;
            text-align: center; font-size: 0.8rem; font-weight: bold; letter-spacing: 0.3em; padding-top: 0.4rem; }}
        .row {{ display: flex; justify-content: center; gap: 0.75rem; margin-bottom: 0.75rem; }}
        .seat {{ width: 4.5rem; padding: 0.6rem 0; border: 2px solid #7b9093; border-radius: 0.6rem;
            background: #fffcf5; text-align: center; }}
        .seat strong {{ display: block; font-size: 1.15rem; }}
        .seat span {{ font-size: 0.75rem; }}
        .seat.held {{ background: #ffe0aa; border-color: #d7ad74; }}
        .seat.booked {{ background: #1c3347; border-color: #1c3347; color: #ffe0aa; }}
        code {{ background: #fffcf5; padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
    </style>
</head>
<body>
    <main>
        <h1>Movie Seats</h1>
        <p>Screening <code>{escape(book.screening.screening_id)}</code>: {available} of {len(statuses)} seats available.</p>
        <div class="screen">SCREEN</div>
{rows}
        <p>Hold seats with <code>POST /holds</code>, then confirm or cancel the hold with
        <code>POST /reservations/{{reservation_id}}/confirm</code> or <code>/cancel</code>.
        A client that loses a reply can find its hold again with <code>GET /holds/{{key}}</code>.
        Unconfirmed holds expire {int(book.hold_duration.total_seconds())} seconds after they are made.</p>
        <p><a href="/docs">API documentation</a></p>
    </main>
</body>
</html>
"""
