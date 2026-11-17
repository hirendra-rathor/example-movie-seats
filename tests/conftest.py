"""Shared fixtures: a temporary database per test and a file written by the milestone 1 build."""

import sqlite3
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
