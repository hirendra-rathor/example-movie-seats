"""Create the Movie Seats HTTP application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from movie_seats.database import LOCK_TIMEOUT_SECONDS, database_path_from_environment, prepare_database
from movie_seats.reservations import (
    AVAILABLE,
    InvalidSelection,
    Reservation,
    ReservationBook,
    ReservationBookBusy,
    ReservationNotFound,
    SeatsUnavailable,
)
from movie_seats.screening import SCREENING


class HoldRequest(BaseModel):
    seats: list[str] = Field(description="Seat labels to hold together.", examples=[["A3", "A4"]])


class SeatStatus(BaseModel):
    seat: str
    status: str = Field(description="`available` or `held`.")


class SeatMap(BaseModel):
    screening_id: str
    seats: list[SeatStatus]


class ReservationBody(BaseModel):
    reservation_id: str
    screening_id: str
    status: str
    seats: list[str]
    created_at: str


class Problem(BaseModel):
    detail: str


class UnavailableProblem(Problem):
    unavailable_seats: list[str]


class InvalidSelectionProblem(Problem):
    invalid_seats: list[str]


def _reservation_body(reservation: Reservation) -> ReservationBody:
    return ReservationBody(
        reservation_id=reservation.reservation_id,
        screening_id=reservation.screening_id,
        status=reservation.status,
        seats=list(reservation.seats),
        created_at=reservation.created_at,
    )


def create_app(
    database_path: str | os.PathLike[str] | None = None,
    *,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
) -> FastAPI:
    """Build the application around the reservation book stored at `database_path`."""
    path = Path(database_path) if database_path is not None else database_path_from_environment()
    book = ReservationBook(path, SCREENING, lock_timeout=lock_timeout)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        prepare_database(path)
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

    @app.exception_handler(ReservationNotFound)
    def reservation_not_found(_: Request, __: ReservationNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Reservation not found."})

    @app.exception_handler(ReservationBookBusy)
    def reservation_book_busy(_: Request, __: ReservationBookBusy) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "The reservation book is busy. Nothing was held; retry the request."},
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
            409: {"model": UnavailableProblem, "description": "Some seats are taken; nothing was held."},
            422: {"model": InvalidSelectionProblem, "description": "The selection is empty, repeated or unknown."},
            503: {"model": Problem, "description": "The write lock was busy; nothing was held."},
        },
    )
    def place_hold(request: HoldRequest, response: Response) -> ReservationBody:
        """Hold every requested seat together, or none of them."""
        reservation = book.place_hold(request.seats)
        response.headers["Location"] = f"/reservations/{reservation.reservation_id}"
        return _reservation_body(reservation)

    @app.get(
        "/reservations/{reservation_id}",
        response_model=ReservationBody,
        responses={404: {"model": Problem, "description": "No reservation has this ID."}},
    )
    def get_reservation(reservation_id: str) -> ReservationBody:
        """Look up a reservation by the ID returned when it was held."""
        return _reservation_body(book.get_reservation(reservation_id))

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
        .seat.held {{ background: #1c3347; border-color: #1c3347; color: #ffe0aa; }}
        code {{ background: #fffcf5; padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
    </style>
</head>
<body>
    <main>
        <h1>Movie Seats</h1>
        <p>Screening <code>{escape(book.screening.screening_id)}</code>: {available} of {len(statuses)} seats available.</p>
        <div class="screen">SCREEN</div>
{rows}
        <p>Hold seats with the JSON API: <code>GET /seats</code>, <code>POST /holds</code> and
        <code>GET /reservations/{{reservation_id}}</code>.</p>
        <p><a href="/docs">API documentation</a></p>
    </main>
</body>
</html>
"""
