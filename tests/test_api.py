"""Integration checks for the Movie Seats JSON API and seat map in movie_seats.app.

Exercise holds, hold keys, confirmation, cancellation, hold deadlines and the
hold-time setting through the real ASGI application and SQLite file with
FastAPI's test client, including a second application instance on the same
database file.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from movie_seats.app import HOLD_SECONDS_ENV, create_app
from movie_seats.database import connect


def statuses(client):
    body = client.get("/seats").json()
    return {seat["seat"]: seat["status"] for seat in body["seats"]}


def test_new_screening_lists_twelve_available_seats():
    with TestClient(create_app()) as client:
        response = client.get("/seats")

    assert response.status_code == 200
    body = response.json()
    assert body["screening_id"] == "screening-1"
    assert [seat["seat"] for seat in body["seats"]] == [
        "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4",
    ]
    assert {seat["status"] for seat in body["seats"]} == {"available"}


def test_hold_returns_reservation_id_and_location():
    with TestClient(create_app()) as client:
        response = client.post("/holds", json={"seats": ["A3", "A4"]})
        seats = statuses(client)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "held"
    assert body["seats"] == ["A3", "A4"]
    assert body["screening_id"] == "screening-1"
    assert response.headers["location"] == f"/reservations/{body['reservation_id']}"
    assert seats["A3"] == seats["A4"] == "held"
    assert [seat for seat, status in seats.items() if status == "held"] == ["A3", "A4"]


def test_overlapping_hold_is_refused_and_holds_nothing():
    with TestClient(create_app()) as client:
        client.post("/holds", json={"seats": ["A3", "A4"]})
        response = client.post("/holds", json={"seats": ["A4", "B1"]})
        seats = statuses(client)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Some requested seats are not available.",
        "unavailable_seats": ["A4"],
    }
    assert seats["B1"] == "available"


def test_invalid_selection_is_rejected_with_the_offending_seats():
    with TestClient(create_app()) as client:
        unknown = client.post("/holds", json={"seats": ["A1", "D1"]})
        repeated = client.post("/holds", json={"seats": ["A1", "A1"]})
        empty = client.post("/holds", json={"seats": []})
        malformed = client.post("/holds", json={"seats": "A1"})
        seats = statuses(client)

    assert (unknown.status_code, unknown.json()["invalid_seats"]) == (422, ["D1"])
    assert (repeated.status_code, repeated.json()["invalid_seats"]) == (422, ["A1"])
    assert (empty.status_code, empty.json()["invalid_seats"]) == (422, [])
    assert malformed.status_code == 422
    assert set(seats.values()) == {"available"}


def test_reservation_lookup_and_unknown_id():
    with TestClient(create_app()) as client:
        held = client.post("/holds", json={"seats": ["B2"]}).json()
        found = client.get(f"/reservations/{held['reservation_id']}")
        missing = client.get("/reservations/does-not-exist")

    assert found.status_code == 200
    assert found.json() == held
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Reservation not found."}


def test_reservation_survives_a_new_application_on_the_same_file(database_path):
    with TestClient(create_app(database_path)) as client:
        held = client.post("/holds", json={"seats": ["C3", "C4"]}).json()

    with TestClient(create_app(database_path)) as restarted:
        found = restarted.get(f"/reservations/{held['reservation_id']}")
        seats = statuses(restarted)

    assert found.status_code == 200
    assert found.json() == held
    assert seats["C3"] == seats["C4"] == "held"


def test_busy_write_lock_returns_503_and_holds_nothing(database_path):
    with TestClient(create_app(database_path, lock_timeout=0.1)) as client:
        gate = connect(database_path)
        gate.execute("BEGIN IMMEDIATE")
        try:
            response = client.post("/holds", json={"seats": ["A1"]})
        finally:
            gate.execute("ROLLBACK")
            gate.close()
        seats = statuses(client)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert seats["A1"] == "available"


def test_seat_map_page_marks_held_seats():
    with TestClient(create_app()) as client:
        client.post("/holds", json={"seats": ["A3", "A4"]})
        page = client.get("/")

    assert page.status_code == 200
    assert "10 of 12 seats available" in page.text
    assert '<div class="seat held" data-seat="A3">' in page.text
    assert '<div class="seat available" data-seat="B1">' in page.text


def test_confirm_and_cancel_report_the_new_status_and_repeat_safely():
    with TestClient(create_app()) as client:
        kept = client.post("/holds", json={"seats": ["A3", "A4"]}).json()["reservation_id"]
        dropped = client.post("/holds", json={"seats": ["B1"]}).json()["reservation_id"]
        confirmed = [client.post(f"/reservations/{kept}/confirm") for _ in range(2)]
        cancelled = [client.post(f"/reservations/{dropped}/cancel") for _ in range(2)]
        seats = statuses(client)

    assert [r.status_code for r in confirmed + cancelled] == [200, 200, 200, 200]
    assert confirmed[0].json() == confirmed[1].json()
    assert confirmed[0].json()["status"] == "confirmed"
    assert cancelled[1].json()["status"] == "cancelled"
    assert cancelled[1].json()["seats"] == ["B1"]
    assert seats["A3"] == seats["A4"] == "booked"
    assert seats["B1"] == "available"


def test_refused_and_unknown_settlements():
    with TestClient(create_app()) as client:
        booked = client.post("/holds", json={"seats": ["C1"]}).json()["reservation_id"]
        client.post(f"/reservations/{booked}/confirm")
        refused = client.post(f"/reservations/{booked}/cancel")
        missing = client.post("/reservations/does-not-exist/confirm")

    assert refused.status_code == 409
    assert refused.json() == {"detail": "This reservation is confirmed; it can't be cancelled.", "status": "confirmed"}
    assert missing.status_code == 404


def test_hold_key_replays_the_first_hold_and_finds_it():
    with TestClient(create_app()) as client:
        first = client.post("/holds", json={"seats": ["A3", "A4"]}, headers={"Idempotency-Key": "key-1"})
        retried = client.post("/holds", json={"seats": ["A4", "A3"]}, headers={"Idempotency-Key": "key-1"})
        found = client.get("/holds/key-1")
        unknown = client.get("/holds/key-2")

    assert (first.status_code, retried.status_code, found.status_code) == (201, 200, 200)
    assert retried.json() == found.json() == first.json()
    assert retried.headers["location"] == first.headers["location"]
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "No hold was recorded under this key."}


def test_hold_key_errors():
    with TestClient(create_app()) as client:
        client.post("/holds", json={"seats": ["A1"]}, headers={"Idempotency-Key": "key-1"})
        reused = client.post("/holds", json={"seats": ["A2"]}, headers={"Idempotency-Key": "key-1"})
        invalid = client.post("/holds", json={"seats": ["A2"]}, headers={"Idempotency-Key": "not valid"})
        seats = statuses(client)

    assert reused.status_code == 422
    assert reused.json() == {"detail": "This Idempotency-Key was already used for a different selection."}
    assert invalid.status_code == 422
    assert seats["A2"] == "available"


def test_hold_key_replays_after_a_new_application_on_the_same_file(database_path):
    with TestClient(create_app(database_path)) as client:
        first = client.post("/holds", json={"seats": ["B3"]}, headers={"Idempotency-Key": "key-1"}).json()

    with TestClient(create_app(database_path)) as restarted:
        found = restarted.get("/holds/key-1")
        retried = restarted.post("/holds", json={"seats": ["B3"]}, headers={"Idempotency-Key": "key-1"})

    assert found.json() == first
    assert (retried.status_code, retried.json()) == (200, first)


def test_seat_map_page_marks_booked_seats():
    with TestClient(create_app()) as client:
        reservation = client.post("/holds", json={"seats": ["C4"]}).json()["reservation_id"]
        client.post(f"/reservations/{reservation}/confirm")
        page = client.get("/")

    assert '<div class="seat booked" data-seat="C4">' in page.text
    assert "11 of 12 seats available" in page.text


def parse(timestamp):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")


def test_hold_reply_reports_when_the_hold_expires():
    with TestClient(create_app()) as client:
        body = client.post("/holds", json={"seats": ["A1"]}).json()

    assert parse(body["expires_at"]) - parse(body["created_at"]) == timedelta(seconds=600)


def test_hold_time_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(HOLD_SECONDS_ENV, "120")
    with TestClient(create_app()) as client:
        body = client.post("/holds", json={"seats": ["A1"]}).json()
        page = client.get("/")

    assert parse(body["expires_at"]) - parse(body["created_at"]) == timedelta(seconds=120)
    assert "expire 120 seconds after they are made" in page.text


@pytest.mark.parametrize("value", ["0", "-5", "ten", "1.5"])
def test_invalid_hold_time_stops_startup(monkeypatch, value):
    monkeypatch.setenv(HOLD_SECONDS_ENV, value)

    with pytest.raises(ValueError, match=HOLD_SECONDS_ENV):
        create_app()


def test_expired_hold_frees_its_seats_and_refuses_confirmation(clock):
    with TestClient(create_app(hold_seconds=60, clock=clock)) as client:
        held = client.post("/holds", json={"seats": ["A3", "A4"]}, headers={"Idempotency-Key": "key-1"}).json()
        clock.advance(60)
        found = client.get(f"/reservations/{held['reservation_id']}").json()
        seats = statuses(client)
        confirm = client.post(f"/reservations/{held['reservation_id']}/confirm")
        replay = client.post("/holds", json={"seats": ["A3", "A4"]}, headers={"Idempotency-Key": "key-1"})

    assert held["expires_at"] == "2026-11-17T12:01:00Z"
    assert (found["status"], found["expires_at"]) == ("expired", "2026-11-17T12:01:00Z")
    assert seats["A3"] == seats["A4"] == "available"
    assert confirm.status_code == 409
    assert confirm.json() == {"detail": "This reservation is expired; it can't be confirmed.", "status": "expired"}
    assert (replay.status_code, replay.json()["status"]) == (200, "expired")


def test_confirmed_booking_reports_no_deadline_and_keeps_its_seats(clock):
    with TestClient(create_app(hold_seconds=60, clock=clock)) as client:
        held = client.post("/holds", json={"seats": ["C2"]}).json()
        confirmed = client.post(f"/reservations/{held['reservation_id']}/confirm").json()
        clock.advance(3600)
        seats = statuses(client)

    assert confirmed["expires_at"] is None
    assert seats["C2"] == "booked"
