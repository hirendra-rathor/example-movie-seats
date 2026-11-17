"""Component checks for database setup and migrations in movie_seats.database.

Exercise schema creation, repeat preparation, refusal of a newer schema, the
upgrade of files written by the milestone 1 and milestone 2 builds, and the
deadline those builds' holds receive at startup, against real SQLite files.
"""

import sqlite3

import pytest

from movie_seats import database
from movie_seats.database import SCHEMA_VERSION, SchemaVersionError, prepare_database
from movie_seats.reservations import CANCELLED, CONFIRMED, EXPIRED, HELD, ReservationBook
from movie_seats.screening import SCREENING


def schema_version(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def test_new_file_gets_the_current_schema_version(tmp_path):
    path = tmp_path / "nested" / "movie-seats.sqlite3"

    prepare_database(path)

    assert schema_version(path) == SCHEMA_VERSION == 3


def test_preparing_again_keeps_existing_reservations(database_path):
    prepare_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO reservations (reservation_id, screening_id, status, created_at) "
            "VALUES ('r-1', 'screening-1', 'held', '2026-11-17T12:00:00Z')"
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


def test_version_1_file_upgrades_and_keeps_its_hold(version_1_file):
    prepare_database(version_1_file)

    book = ReservationBook(version_1_file, SCREENING)
    reservation = book.get_reservation("v1-hold")
    assert schema_version(version_1_file) == 3
    assert reservation.status == HELD
    assert reservation.seats == ("A3", "A4")
    assert reservation.created_at == "2026-11-17T19:20:43Z"
    assert dict(book.seat_statuses())["A4"] == HELD


@pytest.mark.parametrize(("action", "status"), [("confirm", CONFIRMED), ("cancel", CANCELLED)])
def test_upgraded_hold_can_be_settled(version_1_file, action, status):
    prepare_database(version_1_file)
    book = ReservationBook(version_1_file, SCREENING)

    settled = getattr(book, action)("v1-hold")

    assert settled.status == status
    if status == CANCELLED:
        assert book.place_hold(["A4", "B1"]).reservation.seats == ("A4", "B1")


def test_failed_upgrade_leaves_the_version_1_file_unchanged(version_1_file, monkeypatch):
    def upgrade_then_fail(connection):
        database._upgrade_to_version_2(connection)
        raise RuntimeError("simulated failure during the upgrade")

    monkeypatch.setitem(database.MIGRATIONS, 2, upgrade_then_fail)

    with pytest.raises(RuntimeError):
        prepare_database(version_1_file)

    assert schema_version(version_1_file) == 1
    with sqlite3.connect(version_1_file) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(reservations)")]
        seats = connection.execute("SELECT seat_id FROM reservation_seats ORDER BY seat_id").fetchall()
    assert "request_key" not in columns
    assert seats == [("A3",), ("A4",)]


def test_version_2_file_upgrades_and_keeps_every_reservation(version_2_file):
    prepare_database(version_2_file)

    book = ReservationBook(version_2_file, SCREENING)
    assert schema_version(version_2_file) == 3
    assert book.get_reservation("v2-hold").status == HELD
    assert book.find_by_key("key-v2").reservation_id == "v2-hold"
    assert book.get_reservation("v2-booking").status == CONFIRMED
    assert book.get_reservation("v2-cancelled").status == CANCELLED
    assert dict(book.seat_statuses()) == {
        **{seat: "available" for seat in SCREENING.seats},
        "A3": "held",
        "A4": "held",
        "B1": "booked",
    }


def test_earlier_holds_get_one_hold_time_from_the_first_start(version_2_file, clock):
    prepare_database(version_2_file)
    book = ReservationBook(version_2_file, SCREENING, clock=clock)

    report = book.start()
    clock.advance(300)
    again = book.start()

    assert (report.deadlines_assigned, again.deadlines_assigned) == (1, 0)
    assert book.get_reservation("v2-hold").expires_at == "2026-11-17T12:10:00Z"
    assert book.get_reservation("v2-booking").expires_at is None
    clock.advance(300)
    assert book.get_reservation("v2-hold").status == EXPIRED
    assert book.get_reservation("v2-booking").status == CONFIRMED


def test_version_1_file_upgrades_through_every_step(version_1_file, clock):
    prepare_database(version_1_file)
    book = ReservationBook(version_1_file, SCREENING, clock=clock)
    book.start()

    reservation = book.get_reservation("v1-hold")
    assert schema_version(version_1_file) == 3
    assert (reservation.status, reservation.expires_at) == (HELD, "2026-11-17T12:10:00Z")
