"""SQLite connections and the Movie Seats database schema."""

import os
import sqlite3
from pathlib import Path

DATABASE_ENV = "MOVIE_SEATS_DATABASE"
DEFAULT_DATABASE = Path("instance") / "movie-seats.sqlite3"
LOCK_TIMEOUT_SECONDS = 5.0
SCHEMA_VERSION = 1

_SCHEMA_V1 = (
    """
    CREATE TABLE reservations (
        reservation_id TEXT PRIMARY KEY,
        screening_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE reservation_seats (
        reservation_id TEXT NOT NULL REFERENCES reservations (reservation_id),
        screening_id TEXT NOT NULL,
        seat_id TEXT NOT NULL,
        PRIMARY KEY (reservation_id, seat_id),
        UNIQUE (screening_id, seat_id)
    )
    """,
)


class SchemaVersionError(RuntimeError):
    """The database file was written by a newer version of Movie Seats."""


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
    """Create the schema in a new file, or confirm that an existing file is current."""
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
            if version == 0:
                for statement in _SCHEMA_V1:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
