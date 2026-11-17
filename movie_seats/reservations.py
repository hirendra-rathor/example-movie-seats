"""The reservation book: availability, timed all-or-nothing holds, hold keys and settlement."""

import re
import sqlite3
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
EXPIRED = "expired"

DEFAULT_HOLD_DURATION = timedelta(seconds=600)
_HOLD_KEY = re.compile(r"[A-Za-z0-9._~-]{1,128}")


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    screening_id: str
    status: str
    seats: tuple[str, ...]
    created_at: str
    expires_at: str | None
    """The deadline of a held or expired reservation; None once it is confirmed or cancelled."""


@dataclass(frozen=True)
class HoldResult:
    reservation: Reservation
    replayed: bool


@dataclass(frozen=True)
class StartReport:
    deadlines_assigned: int
    holds_expired: int


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
    """UTC to the second; equal-width strings compare in time order."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_hold_key(key: str) -> str:
    if not _HOLD_KEY.fullmatch(key):
        raise InvalidHoldKey("A hold key is 1-128 letters, digits, '-', '_', '.' or '~'.")
    return key


class ReservationBook:
    """Decides holds, deadlines and status changes for one screening and records them in SQLite."""

    def __init__(
        self,
        database_path: Path,
        screening: Screening,
        *,
        clock: Callable[[], datetime] = _utc_now,
        lock_timeout: float = LOCK_TIMEOUT_SECONDS,
        hold_duration: timedelta = DEFAULT_HOLD_DURATION,
    ):
        if hold_duration <= timedelta(0):
            raise ValueError("The hold duration must be positive.")
        self._path = database_path
        self._screening = screening
        self._clock = clock
        self._lock_timeout = lock_timeout
        self._hold_duration = hold_duration

    @property
    def screening(self) -> Screening:
        return self._screening

    @property
    def hold_duration(self) -> timedelta:
        return self._hold_duration

    def start(self) -> StartReport:
        """Before serving: give earlier holds a deadline once, then expire holds that are due."""
        moment = self._now()
        with self._transaction(write=True) as connection:
            assigned = connection.execute(
                "UPDATE reservations SET expires_at = ? WHERE status = ? AND expires_at IS NULL",
                (_timestamp(moment + self._hold_duration), HELD),
            ).rowcount
            expired = self._expire_due(connection, _timestamp(moment))
        return StartReport(deadlines_assigned=assigned, holds_expired=expired)

    def seat_statuses(self) -> list[tuple[str, str]]:
        """Return every seat in layout order: available, held or booked."""
        now = _timestamp(self._now())
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT s.seat_id, r.status FROM reservation_seats AS s "
                "JOIN reservations AS r USING (reservation_id) "
                "WHERE s.screening_id = ? AND s.released = 0 "
                "AND (r.status = ? OR (r.status = ? AND (r.expires_at IS NULL OR r.expires_at > ?)))",
                (self._screening.screening_id, CONFIRMED, HELD, now),
            ).fetchall()
        occupied = {row["seat_id"]: (BOOKED if row["status"] == CONFIRMED else HELD) for row in rows}
        return [(seat, occupied.get(seat, AVAILABLE)) for seat in self._screening.seats]

    def place_hold(self, seats: Iterable[str], request_key: str | None = None) -> HoldResult:
        """Hold every requested seat until a deadline, or none; a recorded key returns its first hold."""
        selection = self._validate(list(seats))
        if request_key is not None:
            validate_hold_key(request_key)
        moment = self._now()
        now = _timestamp(moment)
        try:
            # A refusal is raised after the commit so that the expiry sweep is kept.
            with self._transaction(write=True) as connection:
                self._expire_due(connection, now)
                outcome = self._insert_hold(connection, selection, request_key, moment)
        except sqlite3.IntegrityError:
            # The unique indexes back up the checks above; report what they protected.
            with self._transaction() as connection:
                if request_key is not None:
                    earlier = self._replay(connection, request_key, selection, now)
                    if earlier is not None:
                        return HoldResult(earlier, replayed=True)
                taken = self._unreleased_seats(connection, selection)
            raise SeatsUnavailable(self._in_layout_order(taken)) from None
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _insert_hold(
        self,
        connection: sqlite3.Connection,
        selection: tuple[str, ...],
        request_key: str | None,
        moment: datetime,
    ) -> HoldResult | Exception:
        now = _timestamp(moment)
        if request_key is not None:
            try:
                earlier = self._replay(connection, request_key, selection, now)
            except HoldKeyReused as refusal:
                return refusal
            if earlier is not None:
                return HoldResult(earlier, replayed=True)
        taken = self._unreleased_seats(connection, selection)
        if taken:
            return SeatsUnavailable(self._in_layout_order(taken))
        reservation = Reservation(
            reservation_id=str(uuid.uuid4()),
            screening_id=self._screening.screening_id,
            status=HELD,
            seats=selection,
            created_at=now,
            expires_at=_timestamp(moment + self._hold_duration),
        )
        connection.execute(
            "INSERT INTO reservations "
            "(reservation_id, screening_id, status, created_at, request_key, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                reservation.reservation_id,
                reservation.screening_id,
                reservation.status,
                reservation.created_at,
                request_key,
                reservation.expires_at,
            ),
        )
        connection.executemany(
            "INSERT INTO reservation_seats (reservation_id, screening_id, seat_id) VALUES (?, ?, ?)",
            [(reservation.reservation_id, reservation.screening_id, seat) for seat in selection],
        )
        return HoldResult(reservation, replayed=False)

    def get_reservation(self, reservation_id: str) -> Reservation:
        """Return the reservation with this ID as it stands now."""
        now = _timestamp(self._now())
        with self._transaction() as connection:
            reservation = self._read(connection, "reservation_id", reservation_id, now)
        if reservation is None:
            raise ReservationNotFound(reservation_id)
        return reservation

    def find_by_key(self, request_key: str) -> Reservation:
        """Return the reservation a hold with this key created, as it stands now."""
        validate_hold_key(request_key)
        now = _timestamp(self._now())
        with self._transaction() as connection:
            reservation = self._read(connection, "request_key", request_key, now)
        if reservation is None:
            raise HoldKeyNotFound(request_key)
        return reservation

    def confirm(self, reservation_id: str) -> Reservation:
        """Turn a hold into a booking before its deadline; repeating it changes nothing."""
        return self._settle(reservation_id, CONFIRMED)

    def cancel(self, reservation_id: str) -> Reservation:
        """Cancel a hold and release its seats; repeating it changes nothing."""
        return self._settle(reservation_id, CANCELLED)

    def _settle(self, reservation_id: str, target: str) -> Reservation:
        now = _timestamp(self._now())
        # A refusal is raised after the commit so that the expiry sweep is kept.
        with self._transaction(write=True) as connection:
            self._expire_due(connection, now)
            outcome = self._apply(connection, reservation_id, target, now)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _apply(
        self, connection: sqlite3.Connection, reservation_id: str, target: str, now: str
    ) -> Reservation | Exception:
        current = self._read(connection, "reservation_id", reservation_id, now)
        if current is None:
            return ReservationNotFound(reservation_id)
        if current.status == target:
            return current
        if current.status != HELD:
            return TransitionRefused(current.status, target)
        connection.execute("UPDATE reservations SET status = ? WHERE reservation_id = ?", (target, reservation_id))
        if target == CANCELLED:
            connection.execute("UPDATE reservation_seats SET released = 1 WHERE reservation_id = ?", (reservation_id,))
        return self._read(connection, "reservation_id", reservation_id, now)

    def _expire_due(self, connection: sqlite3.Connection, now: str) -> int:
        """Mark holds whose deadline has arrived as expired and release their seats."""
        due = "SELECT reservation_id FROM reservations WHERE status = ? AND expires_at IS NOT NULL AND expires_at <= ?"
        connection.execute(
            f"UPDATE reservation_seats SET released = 1 WHERE released = 0 AND reservation_id IN ({due})",
            (HELD, now),
        )
        return connection.execute(
            "UPDATE reservations SET status = ? WHERE status = ? AND expires_at IS NOT NULL AND expires_at <= ?",
            (EXPIRED, HELD, now),
        ).rowcount

    def _replay(
        self, connection: sqlite3.Connection, request_key: str, selection: tuple[str, ...], now: str
    ) -> Reservation | None:
        earlier = self._read(connection, "request_key", request_key, now)
        if earlier is not None and earlier.seats != selection:
            raise HoldKeyReused(request_key)
        return earlier

    def _read(self, connection: sqlite3.Connection, column: str, value: str, now: str) -> Reservation | None:
        row = connection.execute(
            "SELECT reservation_id, screening_id, status, created_at, expires_at FROM reservations "
            f"WHERE {column} = ?",
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
        status, expires_at = row["status"], row["expires_at"]
        if status == HELD and expires_at is not None and expires_at <= now:
            status = EXPIRED  # Due but not yet swept by a write.
        return Reservation(
            reservation_id=row["reservation_id"],
            screening_id=row["screening_id"],
            status=status,
            seats=self._in_layout_order(seats),
            created_at=row["created_at"],
            expires_at=expires_at if status in (HELD, EXPIRED) else None,
        )

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC).replace(microsecond=0)

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
