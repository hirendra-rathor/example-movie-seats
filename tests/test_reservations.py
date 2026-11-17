"""Component checks for the reservation book in movie_seats.reservations.

Exercise availability, all-or-nothing holds, selection rules, lookups and the
race between overlapping holds against a real SQLite file, without HTTP.
"""

import threading
import time

import pytest

from movie_seats.database import connect, prepare_database
from movie_seats.reservations import (
    AVAILABLE,
    HELD,
    InvalidSelection,
    Reservation,
    ReservationBook,
    ReservationBookBusy,
    ReservationNotFound,
    SeatsUnavailable,
)
from movie_seats.screening import SCREENING


@pytest.fixture
def book(database_path):
    prepare_database(database_path)
    return ReservationBook(database_path, SCREENING)


def held_seats(book):
    return [seat for seat, status in book.seat_statuses() if status == HELD]


def test_new_screening_lists_twelve_available_seats_in_layout_order(book):
    statuses = book.seat_statuses()

    assert [seat for seat, _ in statuses] == [
        "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4",
    ]
    assert {status for _, status in statuses} == {AVAILABLE}


def test_hold_claims_every_requested_seat_and_can_be_looked_up(book):
    reservation = book.place_hold(["A4", "A3"])

    assert reservation.status == HELD
    assert reservation.seats == ("A3", "A4")
    assert held_seats(book) == ["A3", "A4"]
    assert book.get_reservation(reservation.reservation_id) == reservation


def test_overlapping_hold_claims_nothing_and_names_the_taken_seat(book):
    book.place_hold(["A3", "A4"])

    with pytest.raises(SeatsUnavailable) as raised:
        book.place_hold(["A4", "B1"])

    assert raised.value.seats == ("A4",)
    assert held_seats(book) == ["A3", "A4"]


@pytest.mark.parametrize(
    ("seats", "invalid"),
    [
        ([], ()),
        (["D1"], ("D1",)),
        (["a3"], ("a3",)),
        (["A3", "A3"], ("A3",)),
        (["B1", "Z9", "B2"], ("Z9",)),
    ],
)
def test_invalid_selection_holds_nothing(book, seats, invalid):
    with pytest.raises(InvalidSelection) as raised:
        book.place_hold(seats)

    assert raised.value.seats == invalid
    assert held_seats(book) == []


def test_unknown_reservation_id_is_not_found(book):
    with pytest.raises(ReservationNotFound):
        book.get_reservation("no-such-reservation")


def test_reservation_is_read_back_by_a_new_book_on_the_same_file(book, database_path):
    reservation = book.place_hold(["C1"])

    reopened = ReservationBook(database_path, SCREENING)

    assert reopened.get_reservation(reservation.reservation_id) == reservation
    assert held_seats(reopened) == ["C1"]


def test_overlapping_holds_started_together_give_one_caller_every_seat(book, database_path):
    gate = connect(database_path)
    gate.execute("BEGIN IMMEDIATE")  # Both calls must wait for this write lock.
    outcomes: dict[str, object] = {}

    def attempt(name, seats):
        try:
            outcomes[name] = book.place_hold(seats)
        except SeatsUnavailable as error:
            outcomes[name] = error

    threads = [
        threading.Thread(target=attempt, args=("first", ["A3", "A4"])),
        threading.Thread(target=attempt, args=("second", ["A4", "B1"])),
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.3)
    gate.execute("ROLLBACK")
    gate.close()
    for thread in threads:
        thread.join(timeout=10)

    winners = [outcome for outcome in outcomes.values() if isinstance(outcome, Reservation)]
    losers = [outcome for outcome in outcomes.values() if isinstance(outcome, SeatsUnavailable)]
    assert len(winners) == 1 and len(losers) == 1
    assert losers[0].seats == ("A4",)
    assert held_seats(book) == list(winners[0].seats)


def test_hold_reports_busy_when_the_write_lock_stays_taken(database_path):
    prepare_database(database_path)
    impatient = ReservationBook(database_path, SCREENING, lock_timeout=0.1)
    gate = connect(database_path)
    gate.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ReservationBookBusy):
            impatient.place_hold(["A1"])
    finally:
        gate.execute("ROLLBACK")
        gate.close()

    assert held_seats(impatient) == []
