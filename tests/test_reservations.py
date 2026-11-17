"""Component checks for the reservation book in movie_seats.reservations.

Exercise availability, all-or-nothing holds, selection rules, lookups, hold
keys, confirmation and cancellation, and the races between overlapping
requests against a real SQLite file, without HTTP.
"""

import threading
import time

import pytest

from movie_seats.database import connect, prepare_database
from movie_seats.reservations import (
    AVAILABLE,
    BOOKED,
    CANCELLED,
    CONFIRMED,
    HELD,
    HoldKeyNotFound,
    HoldKeyReused,
    HoldResult,
    InvalidHoldKey,
    InvalidSelection,
    Reservation,
    ReservationBook,
    ReservationBookBusy,
    ReservationNotFound,
    SeatsUnavailable,
    TransitionRefused,
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
    result = book.place_hold(["A4", "A3"])
    reservation = result.reservation

    assert result.replayed is False
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
    reservation = book.place_hold(["C1"]).reservation

    reopened = ReservationBook(database_path, SCREENING)

    assert reopened.get_reservation(reservation.reservation_id) == reservation
    assert held_seats(reopened) == ["C1"]


def test_overlapping_holds_started_together_give_one_caller_every_seat(book, database_path):
    gate = connect(database_path)
    gate.execute("BEGIN IMMEDIATE")  # Both calls must wait for this write lock.
    outcomes: dict[str, object] = {}

    def attempt(name, seats):
        try:
            outcomes[name] = book.place_hold(seats).reservation
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


def reservation_count(database_path):
    connection = connect(database_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("before", "action", "after"),
    [
        (HELD, "confirm", CONFIRMED),
        (HELD, "cancel", CANCELLED),
        (CONFIRMED, "confirm", CONFIRMED),
        (CANCELLED, "cancel", CANCELLED),
    ],
)
def test_allowed_transitions_and_repeats(book, before, action, after):
    reservation = book.place_hold(["A3", "A4"]).reservation
    if before != HELD:
        getattr(book, action)(reservation.reservation_id)

    settled = getattr(book, action)(reservation.reservation_id)

    assert settled.status == after
    assert settled.seats == ("A3", "A4")
    assert book.get_reservation(reservation.reservation_id) == settled


@pytest.mark.parametrize(("first", "second"), [("confirm", "cancel"), ("cancel", "confirm")])
def test_settled_reservation_refuses_the_other_change(book, first, second):
    reservation = book.place_hold(["B2"]).reservation
    settled = getattr(book, first)(reservation.reservation_id)

    with pytest.raises(TransitionRefused) as refused:
        getattr(book, second)(reservation.reservation_id)

    assert refused.value.status == settled.status
    assert book.get_reservation(reservation.reservation_id).status == settled.status


def test_cancelling_releases_seats_for_another_hold(book):
    first = book.place_hold(["A3", "A4"]).reservation

    book.cancel(first.reservation_id)
    second = book.place_hold(["A4", "B1"]).reservation

    assert held_seats(book) == ["A4", "B1"]
    assert book.get_reservation(first.reservation_id).seats == ("A3", "A4")
    assert second.status == HELD


def test_confirmed_booking_keeps_its_seats(book):
    reservation = book.place_hold(["C3", "C4"]).reservation

    book.confirm(reservation.reservation_id)

    statuses = dict(book.seat_statuses())
    assert statuses["C3"] == statuses["C4"] == BOOKED
    with pytest.raises(SeatsUnavailable):
        book.place_hold(["C4"])


@pytest.mark.parametrize("action", ["confirm", "cancel"])
def test_settling_an_unknown_reservation_is_not_found(book, action):
    with pytest.raises(ReservationNotFound):
        getattr(book, action)("no-such-reservation")


def test_retried_key_returns_the_first_hold(book, database_path):
    first = book.place_hold(["A3", "A4"], request_key="key-1")

    retried = book.place_hold(["A4", "A3"], request_key="key-1")

    assert retried == HoldResult(first.reservation, replayed=True)
    assert book.find_by_key("key-1") == first.reservation
    assert reservation_count(database_path) == 1


def test_retried_key_returns_the_current_status(book):
    first = book.place_hold(["A1"], request_key="key-1").reservation
    book.cancel(first.reservation_id)

    retried = book.place_hold(["A1"], request_key="key-1")

    assert retried.replayed is True
    assert retried.reservation.status == CANCELLED
    assert held_seats(book) == []


def test_key_reused_for_other_seats_is_refused(book):
    book.place_hold(["A3", "A4"], request_key="key-1")

    with pytest.raises(HoldKeyReused):
        book.place_hold(["A3"], request_key="key-1")

    assert held_seats(book) == ["A3", "A4"]


def test_failed_hold_leaves_no_record_under_its_key(book):
    blocker = book.place_hold(["A4"]).reservation
    with pytest.raises(SeatsUnavailable):
        book.place_hold(["A3", "A4"], request_key="key-1")
    with pytest.raises(HoldKeyNotFound):
        book.find_by_key("key-1")

    book.cancel(blocker.reservation_id)
    retried = book.place_hold(["A3", "A4"], request_key="key-1")

    assert retried.replayed is False
    assert book.find_by_key("key-1") == retried.reservation


@pytest.mark.parametrize("key", ["", "has space", "slash/inside", "x" * 129])
def test_invalid_hold_key_is_rejected(book, key):
    with pytest.raises(InvalidHoldKey):
        book.place_hold(["A1"], request_key=key)

    assert held_seats(book) == []


def run_together(database_path, calls):
    """Start every call while the test holds the write lock, then release it."""
    gate = connect(database_path)
    gate.execute("BEGIN IMMEDIATE")
    outcomes: list[object] = [None] * len(calls)

    def attempt(index, call):
        try:
            outcomes[index] = call()
        except Exception as error:  # noqa: BLE001 - the outcome is what the test inspects
            outcomes[index] = error

    threads = [threading.Thread(target=attempt, args=(index, call)) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    time.sleep(0.3)
    gate.execute("ROLLBACK")
    gate.close()
    for thread in threads:
        thread.join(timeout=10)
    return outcomes


def test_simultaneous_retries_with_one_key_make_one_hold(book, database_path):
    outcomes = run_together(
        database_path,
        [lambda: book.place_hold(["B1", "B2"], request_key="key-1")] * 2,
    )

    assert all(isinstance(outcome, HoldResult) for outcome in outcomes)
    assert sorted(outcome.replayed for outcome in outcomes) == [False, True]
    assert outcomes[0].reservation == outcomes[1].reservation
    assert reservation_count(database_path) == 1


def test_simultaneous_confirm_and_cancel_apply_one_change(book, database_path):
    reservation = book.place_hold(["C1"]).reservation

    outcomes = run_together(
        database_path,
        [lambda: book.confirm(reservation.reservation_id), lambda: book.cancel(reservation.reservation_id)],
    )

    applied = [outcome for outcome in outcomes if isinstance(outcome, Reservation)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, TransitionRefused)]
    assert len(applied) == 1 and len(refused) == 1
    assert book.get_reservation(reservation.reservation_id).status == applied[0].status
