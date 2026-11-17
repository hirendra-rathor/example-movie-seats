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
