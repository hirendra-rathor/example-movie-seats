"""Assemble the HTTP application and initialize its configured SQLite store."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .api import APIResponse, register_api
from .db import Store


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Retain the factory entry point; tests supply their own database path."""
    store = Store(database_path if database_path is not None else os.environ.get(
        "MOVIE_SEATS_DB", "instance/movie-seats.sqlite3"
    ))

    @asynccontextmanager
    async def lifespan(_app):
        store.initialize()
        yield

    app = FastAPI(title="Movie Seats", version="0.1.0", lifespan=lifespan, default_response_class=APIResponse)
    app.state.store = store
    register_api(app, store)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Movie Seats</title>
</head>
<body>
    <main>
        <h1>Movie Seats</h1>
        <p>The starter is running. Follow the three build prompts to add reservations.</p>
        <p><a href="/docs">API documentation</a></p>
    </main>
</body>
</html>
"""

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "movie-seats"}

    return app
