"""Isolate HTTP and storage integration checks with real temporary SQLite files."""

import pytest
from fastapi.testclient import TestClient

from movie_seats.app import create_app
from movie_seats.db import Store


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "seats.sqlite3")
    result.initialize()
    return result


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "http.sqlite3")) as result:
        yield result
