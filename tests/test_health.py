"""Integration smoke checks for the Movie Seats starter page and health route.

Exercise the real ASGI application without opening a socket.
"""

from fastapi.testclient import TestClient

from movie_seats.app import create_app


def test_health_identifies_the_running_service(tmp_path):
    with TestClient(create_app(tmp_path / "health.sqlite3")) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "movie-seats"}


def test_starter_page_opens_and_links_to_api_documentation(tmp_path):
    with TestClient(create_app(tmp_path / "page.sqlite3")) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>Movie Seats</h1>" in response.text
    assert '<a href="/docs">' in response.text
