"""Integration checks for Store atomicity, durable reads and real SQLite contention."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
from threading import Barrier

import pytest

from movie_seats.db import Store
from movie_seats.domain import Problem, SEATS


def test_hold_is_durable_and_initialization_is_repeatable(store):
    held = store.hold(["A4", "A3"])
    other = Store(store.path)
    other.initialize()
    assert other.get(held["id"]) == held
    assert held["status"] == "held"
    assert held["seats"] == ["A3", "A4"]
    assert len(held["id"]) == 36
    states = {s["id"]: s["status"] for s in other.screening()["seats"]}
    assert set(states) == set(SEATS)
    assert states["A3"] == states["A4"] == "held"


def test_overlap_leaves_the_other_seat_free(store):
    original = store.hold(["A3", "A4"])
    with pytest.raises(Problem, match="complete selection"):
        store.hold(["A2", "A3"])
    assert store.get(original["id"]) == original
    assert store.hold(["A2"])["seats"] == ["A2"]
    with store.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM reservations").fetchone()[0] == 2


def test_sql_failure_rolls_back_every_write(store):
    with store.transaction(write=True) as connection:
        connection.execute("""CREATE TRIGGER fail_claim BEFORE INSERT ON claims WHEN NEW.seat='B4'
            BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected write failure"):
        store.hold(["B3", "B4"])
    with store.transaction() as connection:
        for table in ("reservations", "reservation_seats", "claims"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_independent_writers_have_one_winner(store):
    barrier = Barrier(2)
    def attempt(_):
        other = Store(store.path)
        barrier.wait(timeout=5)
        try:
            return other.hold(["B1"])
        except Problem as error:
            return error.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count(409) == 1


def test_lock_timeout_is_a_busy_error(store):
    impatient = Store(store.path, timeout=0.01)
    with store.transaction(write=True):
        with pytest.raises(Problem) as caught:
            impatient.hold(["C1"])
    assert caught.value.status == 503
    assert impatient.hold(["C1"])["status"] == "held"


def test_unknown_identifier_has_no_effect(store):
    with pytest.raises(Problem) as caught:
        store.get("missing")
    assert caught.value.status == 404
    assert all(seat["status"] == "available" for seat in store.screening()["seats"])


@pytest.mark.parametrize("kind", ["unversioned", "newer", "incomplete", "inventory"])
def test_initialization_refuses_unrecognized_data(tmp_path, kind):
    path = tmp_path / "unknown.sqlite3"
    if kind == "inventory":
        Store(path).initialize()
    with closing(sqlite3.connect(path)) as connection:
        if kind == "unversioned":
            connection.execute("CREATE TABLE important_data (value TEXT)")
        elif kind == "newer":
            connection.execute("PRAGMA user_version=999")
        elif kind == "incomplete":
            connection.execute("PRAGMA user_version=1")
        else:
            connection.execute("DELETE FROM seats WHERE id='A1'")
        connection.commit()
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        Store(path).initialize()
    assert path.read_bytes() == before
