"""SQLite connections and the Movie Seats database schema and its migrations."""

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

DATABASE_ENV = "MOVIE_SEATS_DATABASE"
DEFAULT_DATABASE = Path("instance") / "movie-seats.sqlite3"
LOCK_TIMEOUT_SECONDS = 5.0


class SchemaVersionError(RuntimeError):
    """The database file was written by a newer version of Movie Seats."""


def _create_version_1(connection: sqlite3.Connection) -> None:
    """Milestone 1: reservations and the seats they hold."""
    connection.execute(
        """
        CREATE TABLE reservations (
            reservation_id TEXT PRIMARY KEY,
            screening_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE reservation_seats (
            reservation_id TEXT NOT NULL REFERENCES reservations (reservation_id),
            screening_id TEXT NOT NULL,
            seat_id TEXT NOT NULL,
            PRIMARY KEY (reservation_id, seat_id),
            UNIQUE (screening_id, seat_id)
        )
        """
    )


def _upgrade_to_version_2(connection: sqlite3.Connection) -> None:
    """Milestone 2: hold keys, and seats that a cancellation releases."""
    connection.execute("ALTER TABLE reservations ADD COLUMN request_key TEXT")
    connection.execute(
        "CREATE UNIQUE INDEX reservations_request_key ON reservations (request_key) "
        "WHERE request_key IS NOT NULL"
    )
    # SQLite cannot drop the table-level UNIQUE constraint, so rebuild the table.
    connection.execute(
        """
        CREATE TABLE reservation_seats_v2 (
            reservation_id TEXT NOT NULL REFERENCES reservations (reservation_id),
            screening_id TEXT NOT NULL,
            seat_id TEXT NOT NULL,
            released INTEGER NOT NULL DEFAULT 0 CHECK (released IN (0, 1)),
            PRIMARY KEY (reservation_id, seat_id)
        )
        """
    )
    connection.execute(
        "INSERT INTO reservation_seats_v2 (reservation_id, screening_id, seat_id, released) "
        "SELECT reservation_id, screening_id, seat_id, 0 FROM reservation_seats"
    )
    connection.execute("DROP TABLE reservation_seats")
    connection.execute("ALTER TABLE reservation_seats_v2 RENAME TO reservation_seats")
    connection.execute(
        "CREATE UNIQUE INDEX reservation_seats_unreleased ON reservation_seats (screening_id, seat_id) "
        "WHERE released = 0"
    )


def _upgrade_to_version_3(connection: sqlite3.Connection) -> None:
    """Milestone 3: hold deadlines. Earlier holds get theirs when the reservation book starts."""
    connection.execute("ALTER TABLE reservations ADD COLUMN expires_at TEXT")
    connection.execute(
        "CREATE INDEX reservations_held_deadline ON reservations (expires_at) WHERE status = 'held'"
    )


# Each step upgrades the file from the previous version to the version it is keyed by.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_version_1,
    2: _upgrade_to_version_2,
    3: _upgrade_to_version_3,
}
SCHEMA_VERSION = max(MIGRATIONS)


def database_path_from_environment() -> Path:
    """Return the configured database file, defaulting to the local instance folder."""
    return Path(os.environ.get(DATABASE_ENV) or DEFAULT_DATABASE)


def connect(path: Path, lock_timeout: float = LOCK_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """Open a connection that manages its own transactions and waits for the write lock."""
    connection = sqlite3.connect(path, timeout=lock_timeout, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def prepare_database(path: Path) -> None:
    """Bring a new or older file to the current schema in one transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("BEGIN IMMEDIATE")
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"{path} uses schema version {version}; this build supports up to {SCHEMA_VERSION}."
                )
            for target in range(version + 1, SCHEMA_VERSION + 1):
                MIGRATIONS[target](connection)
            if version != SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
