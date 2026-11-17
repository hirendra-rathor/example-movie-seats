"""SQLite owns durable reservations and the atomic allocation of complete groups."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from uuid import uuid4

from .domain import Creation, Problem, SEATS, request_identity, selection, transition

SCHEMA_VERSION = 2
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

    def __init__(self, path: str | Path, *, timeout: float = 5.0):
        self.path = Path(path)
        self.timeout = timeout

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
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"seats", "reservations", "reservation_seats", "claims", "requests"} <= tables:
                raise RuntimeError("Database schema is incomplete.")
            if tuple(row[0] for row in connection.execute("SELECT id FROM seats ORDER BY id")) != SEATS:
                raise RuntimeError("Database screening inventory does not match this service.")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _reservation(self, connection, reservation_id: str) -> dict:
        row = connection.execute("SELECT id, status FROM reservations WHERE id=?", (reservation_id,)).fetchone()
        if row is None:
            raise Problem(404, "reservation_not_found", "No reservation has that identifier.")
        seats = [item[0] for item in connection.execute(
            "SELECT seat FROM reservation_seats WHERE reservation_id=? ORDER BY seat", (reservation_id,)
        )]
        return {"id": row["id"], "status": row["status"], "seats": seats}

    def get(self, reservation_id: str) -> dict:
        with self.transaction() as connection:
            return self._reservation(connection, reservation_id)

    def screening(self) -> dict:
        with self.transaction() as connection:
            rows = connection.execute("""SELECT seats.id, COALESCE(reservations.status, 'available') AS status
                FROM seats LEFT JOIN claims ON claims.seat=seats.id
                LEFT JOIN reservations ON reservations.id=claims.reservation_id ORDER BY seats.id""")
            return {"id": "screening-1", "seats": [dict(row) for row in rows]}

    def hold(self, seats: list[str] | tuple[str, ...], request_key: str | None = None) -> Creation:
        chosen = selection(seats)
        key = request_identity(request_key)
        with self.transaction(write=True) as connection:
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
            connection.execute("INSERT INTO reservations VALUES (?, 'held')", (reservation_id,))
            connection.executemany("INSERT INTO reservation_seats VALUES (?, ?)", [(reservation_id, s) for s in chosen])
            connection.executemany("INSERT INTO claims VALUES (?, ?)", [(s, reservation_id) for s in chosen])
            if key is not None:
                connection.execute("INSERT INTO requests VALUES (?, ?)", (key, reservation_id))
            return Creation(self._reservation(connection, reservation_id), created=True)

    def complete(self, reservation_id: str, target: str) -> dict:
        with self.transaction(write=True) as connection:
            reservation = self._reservation(connection, reservation_id)
            state = transition(reservation["status"], target)
            if state != reservation["status"]:
                connection.execute("UPDATE reservations SET status=? WHERE id=?", (state, reservation_id))
                if state == "cancelled":
                    connection.execute("DELETE FROM claims WHERE reservation_id=?", (reservation_id,))
            return self._reservation(connection, reservation_id)
