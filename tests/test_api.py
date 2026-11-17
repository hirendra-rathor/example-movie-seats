"""HTTP integration checks for booking contracts through FastAPI and real SQLite."""

import pytest


def test_create_read_and_screening_contract(client):
    assert len(client.get("/screening").json()["seats"]) == 12
    response = client.post("/reservations", json={"seats": ["A4", "A3"]})
    assert response.status_code == 201
    held = response.json()
    assert held["seats"] == ["A3", "A4"]
    assert held["status"] == "held"
    assert client.get(f'/reservations/{held["id"]}').json() == held
    assert client.post("/reservations", json={"seats": ["A2", "A3"]}).status_code == 409
    states = {s["id"]: s["status"] for s in client.get("/screening").json()["seats"]}
    assert states["A2"] == "available"
    assert states["A3"] == states["A4"] == "held"


@pytest.mark.parametrize("body", [{}, {"seats": []}, {"seats": ["A3", "A3"]}, {"seats": ["Z1"]}, {"seats": [7]}, {"seats": "A3"}, {"seats": ["A3"], "extra": True}])
def test_invalid_request_changes_nothing(client, body):
    response = client.post("/reservations", json=body)
    assert response.status_code == 422
    assert "code" in response.json()["error"]
    assert all(s["status"] == "available" for s in client.get("/screening").json()["seats"])


def test_missing_and_malformed_contracts(client):
    assert client.get("/reservations/missing").status_code == 404
    assert client.post("/reservations", content="{", headers={"Content-Type": "application/json"}).status_code == 422


def test_busy_response_is_retryable(client):
    store = client.app.state.store
    store.timeout = 0.01
    with store.transaction(write=True):
        response = client.post("/reservations", json={"seats": ["A1"]})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"]["code"] == "database_busy"


def test_keyed_creation_replay_and_actions(client):
    body = {"seats": ["A3", "A4"], "request_key": "party"}
    first = client.post("/reservations", json=body)
    assert first.status_code == 201
    id = first.json()["id"]
    replay = client.post("/reservations", json={**body, "seats": ["A4", "A3"]})
    assert replay.status_code == 200 and replay.json() == first.json()
    mismatch = client.post("/reservations", json={**body, "seats": ["A1"]})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "request_key_conflict"
    confirmed = client.post(f"/reservations/{id}/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    assert client.post(f"/reservations/{id}/confirm").json() == confirmed.json()
    assert client.post("/reservations", json=body).json() == confirmed.json()
    assert client.post(f"/reservations/{id}/cancel").status_code == 409


def test_cancellation_is_repeatable_and_id_remains_retrievable(client):
    held = client.post("/reservations", json={"seats": ["B1"]}).json()
    path = f'/reservations/{held["id"]}'
    cancelled = client.post(path + "/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(path + "/cancel").json() == cancelled.json()
    assert client.get(path).json() == cancelled.json()
    assert client.post(path + "/confirm").status_code == 409
    assert client.post("/reservations", json={"seats": ["B1"]}).status_code == 201


@pytest.mark.parametrize("key", ["", "contains space", "x" * 129, 123, False])
def test_invalid_request_key_is_422(client, key):
    assert client.post("/reservations", json={"seats": ["A1"], "request_key": key}).status_code == 422


@pytest.mark.parametrize("action", ["confirm", "cancel"])
def test_unknown_completion_is_404(client, action):
    assert client.post(f"/reservations/missing/{action}").status_code == 404
