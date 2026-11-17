"""SQLite owns durable reservations and the atomic allocation of complete groups."""

from contextlib import contextmanager
from collections.abc import Callable
from pathlib import Path
import sqlite3
from uuid import uuid4

from .clock import timestamp, utc_now_us
from .domain import Creation, Problem, SEATS, request_identity, selection, transition

SCHEMA_VERSION = 3
SCHEMA = (
    "CREATE TABLE seats (id TEXT PRIMARY KEY)",
    "CREATE TABLE reservations (id TEXT PRIMARY KEY, status TEXT NOT NULL)",
    """CREATE TABLE reservation_seats (
        reservation_id TEXT NOT NULL REFERENCES reservations(id),
        seat TEXT NOT NULL REFERENCES seats(id),
        PRIMARY KEY (reservation_id, seat))""",
    """CREATE TABLE claims (
        seat TEXT PRIMARY KEY REFERENCES seats(id),
        reservation_id TEXT NOT NULL REFERENCES reservations(id))""",
)


class Store:
    """Use short-lived connections so independent workers share only the file."""

    def __init__(self, path: str | Path, *, timeout: float = 5.0,
                 hold_seconds: int = 300, clock: Callable[[], int] = utc_now_us):
        if type(hold_seconds) is not int or not 1 <= hold_seconds <= 86400:
            raise ValueError("MOVIE_SEATS_HOLD_SECONDS must be an integer from 1 to 86400.")
        self.path = Path(path)
        self.timeout = timeout
        self.hold_seconds = hold_seconds
        self.clock = clock

    @contextmanager
    def transaction(self, *, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except sqlite3.OperationalError as error:
            connection.rollback()
            if getattr(error, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise Problem(503, "database_busy", "The database is busy; try again shortly.") from error
            raise
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(write=True) as connection:
            now = self.clock()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in range(SCHEMA_VERSION + 1):
                raise RuntimeError(f"Unsupported database schema version: {version}")
            if version == 0:
                if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise RuntimeError("Refusing to replace an unversioned database.")
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.executemany("INSERT INTO seats VALUES (?)", [(seat,) for seat in SEATS])
                version = 1
            if version == 1:
                connection.execute("""CREATE TABLE requests (
                    request_key TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL UNIQUE REFERENCES reservations(id))""")
                version = 2
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"seats", "reservations", "reservation_seats", "claims", "requests"} <= tables:
                raise RuntimeError("Database schema is incomplete.")
            if tuple(row[0] for row in connection.execute("SELECT id FROM seats ORDER BY id")) != SEATS:
                raise RuntimeError("Database screening inventory does not match this service.")
            if version == 2:
                connection.execute("ALTER TABLE reservations ADD COLUMN expires_at_us INTEGER")
                connection.execute("CREATE INDEX due_holds ON reservations(status, expires_at_us)")
                connection.execute("UPDATE reservations SET expires_at_us=? WHERE status='held'",
                                   (now + self.hold_seconds * 1_000_000,))
            if connection.execute("SELECT id FROM reservations WHERE status='held' AND expires_at_us IS NULL").fetchone():
                raise RuntimeError("A held reservation is missing its deadline.")
            self._expire(connection, now)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _expire(self, connection, now: int) -> None:
        connection.execute("""DELETE FROM claims WHERE reservation_id IN (
            SELECT id FROM reservations WHERE status='held' AND expires_at_us <= ?)""", (now,))
        connection.execute("UPDATE reservations SET status='expired' WHERE status='held' AND expires_at_us <= ?", (now,))

    @contextmanager
    def operation(self):
        """Commit due expiry even when request work rejects, without partial action effects."""
        rejected = None
        with self.transaction(write=True) as connection:
            now = self.clock()  # Eligibility is evaluated after acquiring the write lock.
            self._expire(connection, now)
            connection.execute("SAVEPOINT request_work")
            try:
                yield connection, now
            except Problem as error:
                connection.execute("ROLLBACK TO request_work")
                rejected = error
            finally:
                connection.execute("RELEASE request_work")
        if rejected is not None:
            raise rejected

    def _reservation(self, connection, reservation_id: str) -> dict:
        row = connection.execute("SELECT id, status, expires_at_us FROM reservations WHERE id=?", (reservation_id,)).fetchone()
        if row is None:
            raise Problem(404, "reservation_not_found", "No reservation has that identifier.")
        seats = [item[0] for item in connection.execute(
            "SELECT seat FROM reservation_seats WHERE reservation_id=? ORDER BY seat", (reservation_id,)
        )]
        return {"id": row["id"], "status": row["status"], "seats": seats, "expires_at": timestamp(row["expires_at_us"])}

    def get(self, reservation_id: str) -> dict:
        with self.operation() as (connection, _now):
            return self._reservation(connection, reservation_id)

    def screening(self) -> dict:
        with self.operation() as (connection, _now):
            rows = connection.execute("""SELECT seats.id, COALESCE(reservations.status, 'available') AS status
                FROM seats LEFT JOIN claims ON claims.seat=seats.id
                LEFT JOIN reservations ON reservations.id=claims.reservation_id ORDER BY seats.id""")
            return {"id": "screening-1", "seats": [dict(row) for row in rows]}

    def hold(self, seats: list[str] | tuple[str, ...], request_key: str | None = None) -> Creation:
        chosen = selection(seats)
        key = request_identity(request_key)
        with self.operation() as (connection, now):
            if key is not None:
                existing = connection.execute("SELECT reservation_id FROM requests WHERE request_key=?", (key,)).fetchone()
                if existing is not None:
                    reservation = self._reservation(connection, existing[0])
                    if tuple(reservation["seats"]) != chosen:
                        raise Problem(409, "request_key_conflict", "That request key belongs to a different seat selection.")
                    return Creation(reservation, created=False)
            placeholders = ",".join("?" for _ in chosen)
            occupied = connection.execute(f"SELECT seat FROM claims WHERE seat IN ({placeholders})", chosen).fetchall()
            if occupied:
                raise Problem(409, "seats_unavailable", "The complete selection is not available.")
            reservation_id = str(uuid4())
            connection.execute("INSERT INTO reservations (id, status, expires_at_us) VALUES (?, 'held', ?)",
                               (reservation_id, now + self.hold_seconds * 1_000_000))
            connection.executemany("INSERT INTO reservation_seats VALUES (?, ?)", [(reservation_id, s) for s in chosen])
            connection.executemany("INSERT INTO claims VALUES (?, ?)", [(s, reservation_id) for s in chosen])
            if key is not None:
                connection.execute("INSERT INTO requests VALUES (?, ?)", (key, reservation_id))
            return Creation(self._reservation(connection, reservation_id), created=True)

    def complete(self, reservation_id: str, target: str) -> dict:
        with self.operation() as (connection, _now):
            reservation = self._reservation(connection, reservation_id)
            state = transition(reservation["status"], target)
            if state != reservation["status"]:
                connection.execute("UPDATE reservations SET status=? WHERE id=?", (state, reservation_id))
                if state == "cancelled":
                    connection.execute("DELETE FROM claims WHERE reservation_id=?", (reservation_id,))
            return self._reservation(connection, reservation_id)
