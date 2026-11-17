"""Shared fixtures that keep every test's reservations in its own temporary database."""

from pathlib import Path

import pytest

from movie_seats.database import DATABASE_ENV


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "movie-seats.sqlite3"


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, database_path: Path) -> Path:
    """Point the default database at a temporary file so no test writes to instance/."""
    monkeypatch.setenv(DATABASE_ENV, str(database_path))
    return database_path
