"""Shared fixtures: a temporary database per test, a controllable clock, and files written by the
milestone 1 and milestone 2 builds."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from movie_seats.database import DATABASE_ENV


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "movie-seats.sqlite3"


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, database_path: Path) -> Path:
    """Point the default database at a temporary file so no test writes to instance/."""
    monkeypatch.setenv(DATABASE_ENV, str(database_path))
    return database_path


# The schema exactly as the milestone 1 build created it.
VERSION_1_SCHEMA = """
CREATE TABLE reservations (
    reservation_id TEXT PRIMARY KEY,
    screening_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE reservation_seats (
    reservation_id TEXT NOT NULL REFERENCES reservations (reservation_id),
    screening_id TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    PRIMARY KEY (reservation_id, seat_id),
    UNIQUE (screening_id, seat_id)
);
PRAGMA user_version = 1;
"""


@pytest.fixture
def version_1_file(database_path):
    """A milestone 1 database holding A3 and A4 under one reservation."""
    connection = sqlite3.connect(database_path)
    connection.executescript(VERSION_1_SCHEMA)
    connection.execute("INSERT INTO reservations VALUES ('v1-hold', 'screening-1', 'held', '2026-11-17T19:20:43Z')")
    connection.executemany(
        "INSERT INTO reservation_seats VALUES ('v1-hold', 'screening-1', ?)", [("A3",), ("A4",)]
    )
    connection.commit()
    connection.close()
    return database_path


# The schema exactly as the milestone 2 build left it after its migration.
VERSION_2_SCHEMA = """
CREATE TABLE reservations (
    reservation_id TEXT PRIMARY KEY,
    screening_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    request_key TEXT
);
CREATE UNIQUE INDEX reservations_request_key ON reservations (request_key) WHERE request_key IS NOT NULL;
CREATE TABLE reservation_seats (
    reservation_id TEXT NOT NULL REFERENCES reservations (reservation_id),
    screening_id TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    released INTEGER NOT NULL DEFAULT 0 CHECK (released IN (0, 1)),
    PRIMARY KEY (reservation_id, seat_id)
);
CREATE UNIQUE INDEX reservation_seats_unreleased ON reservation_seats (screening_id, seat_id) WHERE released = 0;
PRAGMA user_version = 2;
"""


@pytest.fixture
def version_2_file(database_path):
    """A milestone 2 database: a keyed hold on A3, A4, a booking on B1 and a cancelled hold on C1."""
    connection = sqlite3.connect(database_path)
    connection.executescript(VERSION_2_SCHEMA)
    connection.executemany(
        "INSERT INTO reservations VALUES (?, 'screening-1', ?, ?, ?)",
        [
            ("v2-hold", "held", "2026-11-17T11:00:00Z", "key-v2"),
            ("v2-booking", "confirmed", "2026-11-17T11:05:00Z", None),
            ("v2-cancelled", "cancelled", "2026-11-17T11:10:00Z", None),
        ],
    )
    connection.executemany(
        "INSERT INTO reservation_seats VALUES (?, 'screening-1', ?, ?)",
        [("v2-hold", "A3", 0), ("v2-hold", "A4", 0), ("v2-booking", "B1", 0), ("v2-cancelled", "C1", 1)],
    )
    connection.commit()
    connection.close()
    return database_path


class FakeClock:
    """A clock the test moves forward by hand."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC))
