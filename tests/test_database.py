"""Component checks for database setup in movie_seats.database.

Exercise schema creation, repeat preparation and refusal of a newer schema
against real SQLite files.
"""

import sqlite3

import pytest

from movie_seats.database import SCHEMA_VERSION, SchemaVersionError, prepare_database


def schema_version(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def test_new_file_gets_the_current_schema_version(tmp_path):
    path = tmp_path / "nested" / "movie-seats.sqlite3"

    prepare_database(path)

    assert schema_version(path) == SCHEMA_VERSION == 1


def test_preparing_again_keeps_existing_reservations(database_path):
    prepare_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO reservations VALUES ('r-1', 'screening-1', 'held', '2026-11-17T12:00:00Z')"
        )

    prepare_database(database_path)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT reservation_id FROM reservations").fetchall() == [("r-1",)]


def test_newer_schema_stops_startup_without_changes(database_path):
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(SchemaVersionError):
        prepare_database(database_path)

    assert schema_version(database_path) == 99
