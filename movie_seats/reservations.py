"""The reservation book: availability, all-or-nothing holds, hold keys and settlement."""

import re
import sqlite3
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from movie_seats.database import LOCK_TIMEOUT_SECONDS, connect
from movie_seats.screening import Screening

# Seat statuses
AVAILABLE = "available"
BOOKED = "booked"
# Reservation statuses; HELD is also the status of a held seat.
HELD = "held"
CONFIRMED = "confirmed"
CANCELLED = "cancelled"

_HOLD_KEY = re.compile(r"[A-Za-z0-9._~-]{1,128}")


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    screening_id: str
    status: str
    seats: tuple[str, ...]
    created_at: str


@dataclass(frozen=True)
class HoldResult:
    reservation: Reservation
    replayed: bool


class InvalidSelection(ValueError):
    """The requested seats are not a non-empty set of seats in the layout."""

    def __init__(self, message: str, seats: Sequence[str] = ()):
        super().__init__(message)
        self.message = message
        self.seats = tuple(seats)


class InvalidHoldKey(ValueError):
    """The hold key is not 1-128 URL-safe characters."""


class HoldKeyReused(Exception):
    """The hold key already belongs to a hold for a different selection."""


class SeatsUnavailable(Exception):
    """Some requested seats already belong to another reservation; nothing was held."""

    def __init__(self, seats: Sequence[str]):
        super().__init__(f"Seats not available: {', '.join(seats)}")
        self.seats = tuple(seats)


class ReservationNotFound(LookupError):
    """No reservation has the requested ID."""


class HoldKeyNotFound(LookupError):
    """No hold was recorded under the requested key."""


class TransitionRefused(Exception):
    """The reservation's status does not allow the requested change."""

    def __init__(self, status: str, target: str):
        super().__init__(f"A {status} reservation cannot become {target}.")
        self.status = status
        self.target = target


class ReservationBookBusy(Exception):
    """The database write lock was not available in time; nothing changed."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_hold_key(key: str) -> str:
    if not _HOLD_KEY.fullmatch(key):
        raise InvalidHoldKey("A hold key is 1-128 letters, digits, '-', '_', '.' or '~'.")
    return key


class ReservationBook:
    """Decides holds and status changes for one screening and records them in SQLite."""

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
        """Return every seat in layout order: available, held or booked."""
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT s.seat_id, r.status FROM reservation_seats AS s "
                "JOIN reservations AS r USING (reservation_id) "
                "WHERE s.screening_id = ? AND s.released = 0",
                (self._screening.screening_id,),
            ).fetchall()
        occupied = {row["seat_id"]: (BOOKED if row["status"] == CONFIRMED else HELD) for row in rows}
        return [(seat, occupied.get(seat, AVAILABLE)) for seat in self._screening.seats]

    def place_hold(self, seats: Iterable[str], request_key: str | None = None) -> HoldResult:
        """Hold every requested seat or none; a recorded key returns its first hold instead."""
        selection = self._validate(list(seats))
        if request_key is not None:
            validate_hold_key(request_key)
        try:
            with self._transaction(write=True) as connection:
                if request_key is not None:
                    earlier = self._replay(connection, request_key, selection)
                    if earlier is not None:
                        return HoldResult(earlier, replayed=True)
                taken = self._unreleased_seats(connection, selection)
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
                    "INSERT INTO reservations (reservation_id, screening_id, status, created_at, request_key) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        reservation.reservation_id,
                        reservation.screening_id,
                        reservation.status,
                        reservation.created_at,
                        request_key,
                    ),
                )
                connection.executemany(
                    "INSERT INTO reservation_seats (reservation_id, screening_id, seat_id) VALUES (?, ?, ?)",
                    [(reservation.reservation_id, reservation.screening_id, seat) for seat in selection],
                )
            return HoldResult(reservation, replayed=False)
        except sqlite3.IntegrityError:
            # The unique indexes back up the checks above; report what they protected.
            with self._transaction() as connection:
                if request_key is not None:
                    earlier = self._replay(connection, request_key, selection)
                    if earlier is not None:
                        return HoldResult(earlier, replayed=True)
                taken = self._unreleased_seats(connection, selection)
            raise SeatsUnavailable(self._in_layout_order(taken)) from None

    def get_reservation(self, reservation_id: str) -> Reservation:
        """Return the stored reservation with this ID."""
        with self._transaction() as connection:
            reservation = self._read(connection, "reservation_id", reservation_id)
        if reservation is None:
            raise ReservationNotFound(reservation_id)
        return reservation

    def find_by_key(self, request_key: str) -> Reservation:
        """Return the reservation a hold with this key created."""
        validate_hold_key(request_key)
        with self._transaction() as connection:
            reservation = self._read(connection, "request_key", request_key)
        if reservation is None:
            raise HoldKeyNotFound(request_key)
        return reservation

    def confirm(self, reservation_id: str) -> Reservation:
        """Turn a hold into a booking; repeating it changes nothing."""
        return self._settle(reservation_id, CONFIRMED)

    def cancel(self, reservation_id: str) -> Reservation:
        """Cancel a hold and release its seats; repeating it changes nothing."""
        return self._settle(reservation_id, CANCELLED)

    def _settle(self, reservation_id: str, target: str) -> Reservation:
        with self._transaction(write=True) as connection:
            current = self._read(connection, "reservation_id", reservation_id)
            if current is None:
                raise ReservationNotFound(reservation_id)
            if current.status == target:
                return current
            if current.status != HELD:
                raise TransitionRefused(current.status, target)
            connection.execute(
                "UPDATE reservations SET status = ? WHERE reservation_id = ?", (target, reservation_id)
            )
            if target == CANCELLED:
                connection.execute(
                    "UPDATE reservation_seats SET released = 1 WHERE reservation_id = ?", (reservation_id,)
                )
            return self._read(connection, "reservation_id", reservation_id)

    def _replay(
        self, connection: sqlite3.Connection, request_key: str, selection: tuple[str, ...]
    ) -> Reservation | None:
        earlier = self._read(connection, "request_key", request_key)
        if earlier is not None and earlier.seats != selection:
            raise HoldKeyReused(request_key)
        return earlier

    def _read(self, connection: sqlite3.Connection, column: str, value: str) -> Reservation | None:
        row = connection.execute(
            f"SELECT reservation_id, screening_id, status, created_at FROM reservations WHERE {column} = ?",
            (value,),
        ).fetchone()
        if row is None:
            return None
        seats = [
            seat_row["seat_id"]
            for seat_row in connection.execute(
                "SELECT seat_id FROM reservation_seats WHERE reservation_id = ?", (row["reservation_id"],)
            )
        ]
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

    def _unreleased_seats(self, connection: sqlite3.Connection, seats: Sequence[str]) -> set[str]:
        placeholders = ", ".join("?" for _ in seats)
        rows = connection.execute(
            "SELECT seat_id FROM reservation_seats "
            f"WHERE screening_id = ? AND released = 0 AND seat_id IN ({placeholders})",
            (self._screening.screening_id, *seats),
        )
        return {row["seat_id"] for row in rows}

    @contextmanager
    def _transaction(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Run a block in one transaction; writes take SQLite's write lock up front."""
        connection = connect(self._path, self._lock_timeout)
        try:
            try:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            except sqlite3.OperationalError as error:
                if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise ReservationBookBusy() from error
                raise
            try:
                yield connection
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
        finally:
            connection.close()
