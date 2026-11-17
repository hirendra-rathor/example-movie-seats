"""Integration checks for the Movie Seats JSON API and seat map in movie_seats.app.

Exercise the real ASGI application and SQLite file through FastAPI's test
client, including a second application instance on the same database file.
"""

from fastapi.testclient import TestClient

from movie_seats.app import create_app
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
