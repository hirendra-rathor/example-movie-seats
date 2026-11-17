"""Unit, HTTP and real-SQLite checks for deadlines, clock ordering and upgrade preservation."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import Event

from fastapi.testclient import TestClient
import pytest

from movie_seats.app import create_app
from movie_seats.clock import EPOCH, timestamp
from movie_seats.db import Store
from movie_seats.domain import Problem


class Clock:
    def __init__(self):
        self.now = 1_000_000_000_000_000

    def __call__(self):
        return self.now


@pytest.fixture
def timed(tmp_path):
    clock = Clock()
    store = Store(tmp_path / "time.sqlite3", hold_seconds=10, clock=clock)
    store.initialize()
    return store, clock


@pytest.mark.parametrize("offset,state", [(-1, "held"), (0, "expired"), (1, "expired")])
def test_deadline_boundary_is_exact(timed, offset, state):
    store, clock = timed
    held = store.hold(["A3", "A4"], "party").reservation
    expected = clock.now + 10_000_000
    assert held["expires_at"] == timestamp(expected)
    clock.now = expected + offset
    current = store.get(held["id"])
    assert current["status"] == state
    assert current["expires_at"] == held["expires_at"]
    states = {s["id"]: s["status"] for s in store.screening()["seats"]}
    assert states["A3"] == states["A4"] == ("held" if state == "held" else "available")


def test_timestamp_preserves_microseconds():
    value = 1_000_000_000_123_456
    parsed = datetime.fromisoformat(timestamp(value))
    difference = parsed - EPOCH
    assert (difference.days * 86400 + difference.seconds) * 1_000_000 + difference.microseconds == value
    assert parsed.tzinfo == timezone.utc
    assert timestamp(None) is None


def test_confirmation_before_deadline_survives_later_expiration(timed):
    store, clock = timed
    held = store.hold(["B1", "B2"], "booked").reservation
    clock.now += 10_000_000 - 1
    confirmed = store.complete(held["id"], "confirmed")
    clock.now += 99_000_000
    assert store.get(held["id"]) == confirmed
    assert store.complete(held["id"], "confirmed") == confirmed
    assert store.hold(["B2", "B1"], "booked").reservation == confirmed
    with pytest.raises(Problem):
        store.hold(["B1"])


@pytest.mark.parametrize("operation", ["confirm", "cancel", "missing", "mismatch"])
def test_expiry_is_committed_even_when_request_rejects(timed, operation):
    store, clock = timed
    held = store.hold(["A3", "A4"], "old").reservation
    clock.now += 10_000_000
    with pytest.raises(Problem) as caught:
        if operation in {"confirm", "cancel"}:
            store.complete(held["id"], "confirmed" if operation == "confirm" else "cancelled")
        elif operation == "missing":
            store.get("missing")
        else:
            store.hold(["A1"], "old")
    assert caught.value.status == (404 if operation == "missing" else 409)
    # Read raw storage, so the assertion cannot cause the cleanup it claims to observe.
    with store.transaction() as connection:
        assert connection.execute("SELECT status FROM reservations").fetchone()[0] == "expired"
        assert connection.execute("SELECT count(*) FROM claims").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 1


def test_replay_restart_and_new_duration_do_not_renew_deadline(timed):
    store, clock = timed
    held = store.hold(["A3", "A4"], "old").reservation
    clock.now += 5_000_000
    reopened = Store(store.path, hold_seconds=100, clock=clock)
    reopened.initialize()
    assert reopened.hold(["A4", "A3"], "old").reservation == held
    clock.now += 5_000_000
    expired = reopened.hold(["A3", "A4"], "old")
    assert not expired.created and expired.reservation["status"] == "expired"
    assert expired.reservation["expires_at"] == held["expires_at"]
    new = reopened.hold(["A3", "A4"], "new").reservation
    assert new["id"] != held["id"]
    assert new["expires_at"] == timestamp(clock.now + 100_000_000)


def test_expired_state_does_not_reverse_when_clock_moves_back(timed):
    store, clock = timed
    held = store.hold(["A1"]).reservation
    clock.now += 10_000_000
    assert store.get(held["id"])["status"] == "expired"
    clock.now -= 20_000_000
    assert store.get(held["id"])["status"] == "expired"


def test_failed_expiry_is_atomic_and_recovers_on_next_request(timed):
    store, clock = timed
    held = store.hold(["A3", "A4"]).reservation
    with store.transaction(write=True) as connection:
        connection.execute("CREATE TRIGGER reject_expiry BEFORE DELETE ON claims WHEN OLD.seat='A4' BEGIN SELECT RAISE(ABORT, 'expiry failure'); END")
    clock.now += 10_000_000
    with pytest.raises(sqlite3.IntegrityError):
        store.screening()
    with store.transaction(write=True) as connection:
        assert connection.execute("SELECT status FROM reservations").fetchone()[0] == "held"
        assert connection.execute("SELECT count(*) FROM claims").fetchone()[0] == 2
        connection.execute("DROP TRIGGER reject_expiry")
    assert store.get(held["id"])["status"] == "expired"


def test_request_savepoint_preserves_cleanup_without_partial_action(timed):
    store, clock = timed
    store.hold(["A1"])
    clock.now += 10_000_000
    with pytest.raises(Problem):
        with store.operation() as (connection, now):
            connection.execute("INSERT INTO reservations VALUES ('partial', 'held', ?)", (now + 1_000_000,))
            raise Problem(409, "rejected", "Reject the request after its first write.")
    with store.transaction() as connection:
        assert connection.execute("SELECT id FROM reservations WHERE id='partial'").fetchone() is None
        assert connection.execute("SELECT status FROM reservations").fetchone()[0] == "expired"


def test_confirmation_samples_time_after_waiting_for_write_lock(timed):
    store, clock = timed
    held = store.hold(["A3", "A4"]).reservation
    attempting = Event()
    class WaitingStore(Store):
        @contextmanager
        def transaction(self, *, write=False):
            attempting.set()
            with super().transaction(write=write) as connection:
                yield connection
    waiter = WaitingStore(store.path, clock=clock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.transaction(write=True):
            future = pool.submit(waiter.complete, held["id"], "confirmed")
            assert attempting.wait(timeout=5)
            clock.now += 10_000_000
        with pytest.raises(Problem) as caught:
            future.result(timeout=5)
    assert caught.value.code == "reservation_expired"
    assert store.get(held["id"])["status"] == "expired"


@pytest.mark.parametrize("seconds", [0, -1, 86401, 1.5, True])
def test_store_rejects_invalid_duration(tmp_path, seconds):
    with pytest.raises(ValueError, match="1 to 86400"):
        Store(tmp_path / "invalid.sqlite3", hold_seconds=seconds)


@pytest.mark.parametrize("value", ["0", "-1", "86401", "1.5", "invalid"])
def test_app_rejects_invalid_environment_duration(tmp_path, monkeypatch, value):
    monkeypatch.setenv("MOVIE_SEATS_HOLD_SECONDS", value)
    with pytest.raises(ValueError, match="MOVIE_SEATS_HOLD_SECONDS"):
        create_app(tmp_path / "invalid.sqlite3")


def load_fixture(path, version):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript((Path(__file__).parent / f"fixtures/release_v{version}.sql").read_text())
        return dict(connection.execute("SELECT id, status FROM reservations"))


@pytest.mark.parametrize("version", [1, 2])
def test_upgrade_assigns_grace_once_and_preserves_all_previous_data(tmp_path, version):
    path = tmp_path / "upgrade.sqlite3"
    original = load_fixture(path, version)
    clock = Clock()
    store = Store(path, hold_seconds=10, clock=clock)
    store.initialize()
    held_deadline = timestamp(clock.now + 10_000_000)
    for id, state in original.items():
        record = store.get(id)
        assert record["status"] == state
        assert record["expires_at"] == (held_deadline if state == "held" else None)
    clock.now += 5_000_000
    reopened = Store(path, hold_seconds=90, clock=clock)
    reopened.initialize()
    for id, state in original.items():
        assert reopened.get(id)["expires_at"] == (held_deadline if state == "held" else None)
    clock.now += 5_000_000
    reopened.initialize()
    for id, state in original.items():
        assert reopened.get(id)["status"] == ("expired" if state == "held" else state)
    if version == 2:
        assert reopened.hold(["A3", "A4"], "legacy-held").reservation["status"] == "expired"
        assert reopened.hold(["B1", "B2"], "legacy-confirmed").reservation["status"] == "confirmed"
        assert reopened.hold(["C1", "C2"], "legacy-cancelled").reservation["status"] == "cancelled"


def test_failed_version_three_migration_rolls_back_schema_and_deadlines(tmp_path):
    path = tmp_path / "failed.sqlite3"
    original = load_fixture(path, 2)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE due_holds (conflicting_name TEXT)")
        connection.commit()
    with pytest.raises(sqlite3.OperationalError):
        Store(path).initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert 'expires_at_us' not in {r[1] for r in connection.execute('PRAGMA table_info(reservations)')}
        assert dict(connection.execute("SELECT id, status FROM reservations")) == original


def test_http_expiry_contract_and_startup_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "api.sqlite3"
    clock = Clock()
    monkeypatch.setenv("MOVIE_SEATS_HOLD_SECONDS", "10")
    with TestClient(create_app(path, clock=clock)) as client:
        body = {"seats": ["A3", "A4"], "request_key": "party"}
        held = client.post('/reservations', json=body).json()
    clock.now += 10_000_000
    with TestClient(create_app(path, clock=clock)) as client:
        # Startup itself must have cleaned up before the first application request.
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT status FROM reservations").fetchone()[0] == "expired"
        response = client.post(f'/reservations/{held["id"]}/confirm')
        assert response.status_code == 409 and response.json()['error']['code'] == 'reservation_expired'
        replay = client.post('/reservations', json=body)
        assert replay.status_code == 200 and replay.json()['status'] == 'expired'
        assert replay.json()['expires_at'] == held['expires_at']
        assert client.post('/reservations', json={**body, 'request_key': 'next'}).status_code == 201
