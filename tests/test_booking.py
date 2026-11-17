"""Unit and SQLite integration checks for completion, replay identity and migration."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from movie_seats.db import SCHEMA_VERSION, Store
from movie_seats.domain import Problem, request_identity, transition


@pytest.mark.parametrize("state,target,expected", [
    ("held", "confirmed", "confirmed"), ("held", "cancelled", "cancelled"),
    ("confirmed", "confirmed", "confirmed"), ("cancelled", "cancelled", "cancelled"),
    ("confirmed", "cancelled", None), ("cancelled", "confirmed", None),
])
def test_completion_policy(state, target, expected):
    if expected is None:
        with pytest.raises(Problem) as caught:
            transition(state, target)
        assert caught.value.code == "reservation_final"
    else:
        assert transition(state, target) == expected


@pytest.mark.parametrize("key", ["", "a" * 129, " key", "a b", "é", 42, True, "a\n"])
def test_key_rejects_ambiguous_or_unbounded_values(key):
    with pytest.raises(Problem):
        request_identity(key)


def test_key_accepts_deliberate_ascii_identifiers():
    assert request_identity("a" * 128) == "a" * 128
    assert request_identity("Party_17:retry.1-x") == "Party_17:retry.1-x"
    assert request_identity(None) is None


def test_replay_recovers_across_instances_and_after_confirmation(store):
    first = store.hold(["A3", "A4"], "party-17")
    second = Store(store.path).hold(["A4", "A3"], "party-17")
    assert first.created and not second.created
    assert first.reservation == second.reservation
    confirmed = store.complete(first.reservation["id"], "confirmed")
    assert store.complete(confirmed["id"], "confirmed") == confirmed
    assert Store(store.path).hold(["A3", "A4"], "party-17").reservation == confirmed
    with pytest.raises(Problem) as caught:
        store.hold(["A1"], "party-17")
    assert caught.value.code == "request_key_conflict"


def test_cancelled_replay_and_repeated_cancel_cannot_release_a_new_owner(store):
    original = store.hold(["A3", "A4"], "old").reservation
    cancelled = store.complete(original["id"], "cancelled")
    new = store.hold(["A3", "A4"], "new").reservation
    assert store.complete(original["id"], "cancelled") == cancelled
    assert store.hold(["A4", "A3"], "old").reservation == cancelled
    assert store.get(new["id"]) == new
    with store.transaction() as connection:
        assert {row[0] for row in connection.execute("SELECT reservation_id FROM claims")} == {new["id"]}
    with pytest.raises(Problem):
        store.complete(original["id"], "confirmed")


def test_failed_request_does_not_consume_key(store):
    store.hold(["B1"])
    with pytest.raises(Problem):
        store.hold(["B1", "B2"], "retry")
    assert store.hold(["B2"], "retry").created


def test_key_write_failure_rolls_back_hold(store):
    with store.transaction(write=True) as connection:
        connection.execute("CREATE TRIGGER reject_key BEFORE INSERT ON requests BEGIN SELECT RAISE(ABORT, 'key failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.hold(["A1"], "key")
    assert all(s["status"] == "available" for s in store.screening()["seats"])
    with store.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM reservations").fetchone()[0] == 0


def test_cancel_write_failure_preserves_held_state_and_claims(store):
    held = store.hold(["A3", "A4"]).reservation
    with store.transaction(write=True) as connection:
        connection.execute("CREATE TRIGGER reject_release BEFORE DELETE ON claims BEGIN SELECT RAISE(ABORT, 'release failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.complete(held["id"], "cancelled")
    assert store.get(held["id"]) == held
    assert sum(s["status"] == "held" for s in store.screening()["seats"]) == 2


def race(functions):
    barrier = Barrier(len(functions))
    def attempt(fn):
        barrier.wait(timeout=5)
        try:
            return fn()
        except Problem as error:
            return error
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(attempt, functions))


def test_same_key_concurrent_requests_create_once(store):
    results = race([lambda: Store(store.path).hold(["C1"], "same") for _ in range(2)])
    assert sum(r.created for r in results) == 1
    assert len({r.reservation["id"] for r in results}) == 1


def test_conflicting_completion_race_has_one_terminal_winner(store):
    id = store.hold(["C2"]).reservation["id"]
    results = race([lambda: Store(store.path).complete(id, "confirmed"), lambda: Store(store.path).complete(id, "cancelled")])
    assert sum(isinstance(r, Problem) and r.status == 409 for r in results) == 1
    state = store.get(id)["status"]
    assert state in {"confirmed", "cancelled"}
    seat = next(s for s in store.screening()["seats"] if s["id"] == "C2")
    assert seat["status"] == ("confirmed" if state == "confirmed" else "available")


def legacy_database(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript((Path(__file__).parent / "fixtures/release_v1.sql").read_text())
        return connection.execute("SELECT id FROM reservations").fetchone()[0]


def test_version_one_upgrade_preserves_hold_and_allows_completion(tmp_path):
    path = tmp_path / "v1.sqlite3"
    id = legacy_database(path)
    store = Store(path)
    store.initialize()
    store.initialize()
    held = store.get(id)
    assert {key: held[key] for key in ("id", "status", "seats")} == {"id": id, "status": "held", "seats": ["A3", "A4"]}
    assert store.complete(id, "confirmed")["status"] == "confirmed"
    with store.transaction() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT count(*) FROM claims").fetchone()[0] == 2


def test_failed_upgrade_retains_previous_version_and_data(tmp_path):
    path = tmp_path / "failed.sqlite3"
    id = legacy_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE requests (unexpected TEXT)")
        connection.commit()
    before = path.read_bytes()
    with pytest.raises(sqlite3.OperationalError):
        Store(path).initialize()
    assert path.read_bytes() == before
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT id FROM reservations").fetchone()[0] == id
