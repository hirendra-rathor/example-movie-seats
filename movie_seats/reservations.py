"""The reservation book: seat availability, all-or-nothing holds and lookups."""

import sqlite3
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from movie_seats.database import LOCK_TIMEOUT_SECONDS, connect
from movie_seats.screening import Screening

AVAILABLE = "available"
HELD = "held"


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    screening_id: str
    status: str
    seats: tuple[str, ...]
    created_at: str


class InvalidSelection(ValueError):
    """The requested seats are not a non-empty set of seats in the layout."""

    def __init__(self, message: str, seats: Sequence[str] = ()):
        super().__init__(message)
        self.message = message
        self.seats = tuple(seats)


class SeatsUnavailable(Exception):
    """Some requested seats already belong to another reservation; nothing was held."""

    def __init__(self, seats: Sequence[str]):
        super().__init__(f"Seats not available: {', '.join(seats)}")
        self.seats = tuple(seats)


class ReservationNotFound(LookupError):
    """No reservation has the requested ID."""


class ReservationBookBusy(Exception):
    """The database write lock was not available in time; nothing was held."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReservationBook:
    """Decides holds for one screening and records them in the SQLite database."""

    def __init__(
        self,
        database_path: Path,
        screening: Screening,
        *,
        clock: Callable[[], datetime] = _utc_now,
        lock_timeout: float = LOCK_TIMEOUT_SECONDS,
    ):
        self._path = database_path
        self._screening = screening
        self._clock = clock
        self._lock_timeout = lock_timeout

    @property
    def screening(self) -> Screening:
        return self._screening

    def seat_statuses(self) -> list[tuple[str, str]]:
        """Return every seat in layout order with its current status."""
        connection = connect(self._path, self._lock_timeout)
        try:
            held = self._reserved_seats(connection, self._screening.seats)
        finally:
            connection.close()
        return [(seat, HELD if seat in held else AVAILABLE) for seat in self._screening.seats]

    def place_hold(self, seats: Iterable[str]) -> Reservation:
        """Hold every requested seat in one transaction, or hold none of them."""
        selection = self._validate(list(seats))
        connection = connect(self._path, self._lock_timeout)
        try:
            self._begin_write(connection)
            try:
                taken = self._reserved_seats(connection, selection)
                if taken:
                    raise SeatsUnavailable(self._in_layout_order(taken))
                reservation = Reservation(
                    reservation_id=str(uuid.uuid4()),
                    screening_id=self._screening.screening_id,
                    status=HELD,
                    seats=selection,
                    created_at=_timestamp(self._clock()),
                )
                connection.execute(
                    "INSERT INTO reservations (reservation_id, screening_id, status, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (reservation.reservation_id, reservation.screening_id, reservation.status, reservation.created_at),
                )
                connection.executemany(
                    "INSERT INTO reservation_seats (reservation_id, screening_id, seat_id) VALUES (?, ?, ?)",
                    [(reservation.reservation_id, reservation.screening_id, seat) for seat in selection],
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError:
                # The unique seat constraint is a backstop for the check above.
                _rollback(connection)
                raise SeatsUnavailable(self._in_layout_order(self._reserved_seats(connection, selection))) from None
            except BaseException:
                _rollback(connection)
                raise
        finally:
            connection.close()
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation:
        """Return the stored reservation with this ID."""
        connection = connect(self._path, self._lock_timeout)
        try:
            connection.execute("BEGIN")
            try:
                row = connection.execute(
                    "SELECT reservation_id, screening_id, status, created_at FROM reservations "
                    "WHERE reservation_id = ?",
                    (reservation_id,),
                ).fetchone()
                seats = [
                    seat_row["seat_id"]
                    for seat_row in connection.execute(
                        "SELECT seat_id FROM reservation_seats WHERE reservation_id = ?", (reservation_id,)
                    )
                ]
            finally:
                connection.execute("COMMIT")
        finally:
            connection.close()
        if row is None:
            raise ReservationNotFound(reservation_id)
        return Reservation(
            reservation_id=row["reservation_id"],
            screening_id=row["screening_id"],
            status=row["status"],
            seats=self._in_layout_order(seats),
            created_at=row["created_at"],
        )

    def _validate(self, seats: list[str]) -> tuple[str, ...]:
        if not seats:
            raise InvalidSelection("Select at least one seat.")
        unknown = [seat for seat in dict.fromkeys(seats) if not self._screening.has_seat(seat)]
        if unknown:
            raise InvalidSelection(f"Unknown seats: {', '.join(unknown)}.", unknown)
        repeated = [seat for seat, count in Counter(seats).items() if count > 1]
        if repeated:
            raise InvalidSelection(f"Each seat may be requested once: {', '.join(repeated)}.", repeated)
        return self._in_layout_order(seats)

    def _in_layout_order(self, seats: Iterable[str]) -> tuple[str, ...]:
        wanted = set(seats)
        return tuple(seat for seat in self._screening.seats if seat in wanted)

    def _reserved_seats(self, connection: sqlite3.Connection, seats: Sequence[str]) -> set[str]:
        placeholders = ", ".join("?" for _ in seats)
        rows = connection.execute(
            f"SELECT seat_id FROM reservation_seats WHERE screening_id = ? AND seat_id IN ({placeholders})",
            (self._screening.screening_id, *seats),
        )
        return {row["seat_id"] for row in rows}

    @staticmethod
    def _begin_write(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise ReservationBookBusy() from error
            raise
